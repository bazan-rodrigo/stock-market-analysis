"""Lock de corrida persistido (run_lock_service): atomicidad de la toma con
token de propiedad, heartbeat, reclamo de un lock muerto y estado para la
UI. Lógica pura sobre el stub sqlite (Base.metadata.create_all)."""
import os
from datetime import timedelta

import pytest
import sqlalchemy as sa

import app.models  # noqa: F401 — registra RunLock
from app.database import Base, Session, engine, get_session
from app.models.run_lock import RunLock
from app.services import run_lock_service as rl


@pytest.fixture(autouse=True)
def _clean_run_lock():
    Base.metadata.create_all(engine)
    s = get_session()
    s.execute(sa.delete(RunLock))
    s.commit()
    yield
    s.execute(sa.delete(RunLock))
    s.commit()
    Session.remove()


def _set_heartbeat(op, seconds_ago, pid=None, token=None):
    s = get_session()
    row = s.get(RunLock, op)
    row.heartbeat = rl._utcnow() - timedelta(seconds=seconds_ago)
    if pid is not None:
        row.pid = pid
    if token is not None:
        row.token = token
    s.commit()


def test_acquire_una_vez_y_rechaza_la_segunda():
    assert rl.acquire("indicators")                 # token truthy
    assert rl.acquire("indicators") is None         # ya hay corrida viva
    assert rl.is_running("indicators") is True


def test_release_libera():
    tok = rl.acquire("prices")
    rl.release("prices", tok)
    assert rl.is_running("prices") is False
    assert rl.acquire("prices")                     # se puede volver a tomar


def test_ops_independientes():
    assert rl.acquire("indicators")
    assert rl.acquire("signals")                    # otra op, otro lock


def test_reclama_lock_muerto_pero_no_uno_vivo():
    rl.acquire("indicators")
    _set_heartbeat("indicators", seconds_ago=1, pid=999999)          # fresco
    assert rl.acquire("indicators") is None                         # no reclamable
    _set_heartbeat("indicators", seconds_ago=rl.STALE_SECONDS + 10) # muerto
    assert rl.acquire("indicators")                                # reclamable
    assert get_session().get(RunLock, "indicators").pid == os.getpid()


def test_status_marca_stale_por_heartbeat_viejo():
    assert rl.status("indicators") is None
    rl.acquire("indicators")
    st = rl.status("indicators")
    assert st["pid"] == os.getpid() and st["stale"] is False
    _set_heartbeat("indicators", seconds_ago=rl.STALE_SECONDS + 5)
    st = rl.status("indicators")
    assert st["stale"] is True
    assert rl.is_running("indicators") is False     # stale no cuenta como vivo


def test_beat_actualiza_solo_con_el_token_propio():
    tok = rl.acquire("indicators")
    _set_heartbeat("indicators", seconds_ago=60)
    assert rl.beat("indicators", tok) is True
    assert rl.status("indicators")["age_seconds"] < 5   # el latido lo refrescó
    assert rl.beat("indicators", "token-ajeno") is False


def test_token_evita_que_release_viejo_pise_el_lock_reclamado():
    """Mismo pid, dos adquisiciones: la vieja quedó stale y otra la reclamó.
    El release de la vieja (token viejo) NO borra el lock de la nueva."""
    tok_viejo = rl.acquire("indicators")
    _set_heartbeat("indicators", seconds_ago=rl.STALE_SECONDS + 10)
    tok_nuevo = rl.acquire("indicators")            # reclama el stale
    assert tok_nuevo and tok_nuevo != tok_viejo
    rl.release("indicators", tok_viejo)             # no debe tocar el nuevo
    assert rl.is_running("indicators") is True
    rl.release("indicators", tok_nuevo)
    assert rl.status("indicators") is None


def test_beat_no_marca_perdido_ante_error_de_bd(monkeypatch):
    rl.acquire("indicators")

    class _S:
        def execute(self, *a, **k):
            raise sa.exc.OperationalError("stmt", None, Exception("1205"))

        def rollback(self):
            pass

    monkeypatch.setattr(rl, "get_session", lambda: _S())
    assert rl.beat("indicators", "tok") is True     # transitorio, no fatal


def test_clear_stale_limpia_muertos_y_deja_vivos():
    rl.acquire("indicators")
    rl.acquire("prices")
    _set_heartbeat("prices", seconds_ago=rl.STALE_SECONDS + 30)
    assert rl.clear_stale() == 1
    assert rl.is_running("indicators") is True
    assert rl.status("prices") is None


def test_heartbeating_context_libera_al_salir():
    tok = rl.acquire("indicators")
    with rl.heartbeating("indicators", tok, interval=0.05):
        assert rl.is_running("indicators") is True
    assert rl.status("indicators") is None          # liberado al salir


def test_release_con_sesion_envenenada_igual_libera():
    """Fix del hallazgo major: si la corrida dejó la sesión en
    pending-rollback, release igual borra la fila (descarta la sesión sucia
    antes del DELETE)."""
    tok = rl.acquire("indicators")
    s = get_session()
    try:
        s.execute(sa.text("SELECT * FROM tabla_inexistente_zzz"))
    except Exception:
        pass  # NO rollback: la sesión queda pending-rollback
    rl.release("indicators", tok)
    assert rl.status("indicators") is None          # se liberó igual


def test_guarded_acquire_devuelve_token_o_none():
    assert rl.guarded_acquire("indicators")         # token truthy
    assert rl.guarded_acquire("indicators") is None # ya tomado


def test_guarded_acquire_fail_open_devuelve_sentinel(monkeypatch):
    """Si acquire explota (tabla ausente pre-migración, BD caída),
    guarded_acquire NO bloquea: devuelve NO_LOCK (proceder sin lock real)."""
    def _boom(*a, **k):
        raise sa.exc.OperationalError("stmt", None,
                                      Exception("no such table: run_lock"))
    monkeypatch.setattr(rl, "acquire", _boom)
    assert rl.guarded_acquire(rl.HEAVY_WRITE) == rl.NO_LOCK
