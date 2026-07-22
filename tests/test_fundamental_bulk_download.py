"""Camino batch de descarga de fundamentales (_run_fund_batch).

Espejo del invariante que test_price_bulk_download.py fija para precios: el
runner NO puede quedarse con la transacción abierta mientras el pool sale a la
red. Los dos servicios tienen el mismo problema y el mismo arreglo, así que
también tienen que tener la misma red — sin este archivo, la mitad
fundamental del arreglo (commit 00e61da) quedaba sin ningún test que la
sostenga.
"""
import sys
import types

import pytest
import sqlalchemy as sa

# fundamental_service (vía app.sources.yahoo) importa yfinance en el header;
# esta PC y la suite no lo tienen — acá nunca se descarga nada.
sys.modules.setdefault("yfinance", types.ModuleType("yfinance"))

import app.services.fundamental_service as fs
from app.database import Base, engine, get_session
from app.models import Asset, PriceSource


@pytest.fixture()
def db():
    import app.models  # noqa: F401 — registra los modelos en Base.metadata
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM assets"))
    yield
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM assets"))
    get_session().rollback()


def _seed(n=2):
    s = get_session()
    src = s.query(PriceSource).filter_by(name="Yahoo Finance").first()
    if src is None:
        src = PriceSource(name="Yahoo Finance")
        s.add(src)
        s.commit()
    pares = []
    for i in range(n):
        a = Asset(ticker=f"FUND{i}", name=f"FUND{i}", price_source_id=src.id)
        s.add(a)
        s.flush()
        pares.append((a.id, a.ticker))
    s.commit()
    return pares


# ── La transacción se cierra ANTES del pool ──────────────────────────────────

def test_sesion_cerrada_antes_de_lanzar_los_workers(db, monkeypatch):
    """Los tres puntos de entrada (update_new_fundamentals /
    update_all_fundamentals / redownload_all_fundamentals) arman su lista de
    activos con la sesión de este thread y no la sueltan. Si _run_fund_batch
    no la cierra, SQLAlchemy sostiene esa transacción los minutos que dura la
    descarga contra Yahoo: en PostgreSQL queda 'idle in transaction' y FIJA EL
    XMIN HORIZON — autovacuum no reclama ninguna tupla muerta mientras tanto,
    justo cuando los workers están borrando y reescribiendo trimestrales.

    Igual que en precios, el invariante se observa con el registry de la
    scoped_session: después del remove() no hay sesión viva para este thread.
    """
    pares = _seed(2)
    visto = {}

    def fake_worker(asset_id, ticker, clear=False, skip_ratios=False):
        visto.setdefault("sesiones_vivas", []).append(
            fs._ScopedSession.registry.has())
        visto.setdefault("procesados", []).append(ticker)
        return True, None

    monkeypatch.setattr(fs, "_fund_worker", fake_worker)

    # la sesión del "llamador" está abierta al entrar (como en producción)
    get_session().query(Asset).all()
    out = fs._run_fund_batch(pares)

    assert visto["sesiones_vivas"] == [False, False]
    assert sorted(visto["procesados"]) == sorted(t for _, t in pares)
    assert out == {"total": 2, "success": 2, "errors": []}


def test_al_pool_solo_viajan_datos_planos(db, monkeypatch):
    """Del otro lado del remove() no hay sesión de la que recargar, y los
    workers corren en otros threads (la Session no es thread-safe): lo que
    cruza tiene que ser (asset_id, ticker), nunca instancias del ORM."""
    pares = _seed(1)
    recibido = []

    def fake_worker(*args, **kwargs):
        recibido.extend(list(args) + list(kwargs.values()))
        return True, None

    monkeypatch.setattr(fs, "_fund_worker", fake_worker)
    fs._run_fund_batch(pares)

    assert recibido
    for arg in recibido:
        try:
            mapeado = sa.inspect(arg).mapper is not None
        except Exception:
            mapeado = False           # no es una instancia ORM: bien
        assert not mapeado, f"objeto ORM cruzando al pool: {arg!r}"


def test_sin_pares_no_toca_la_sesion_del_llamador(db, monkeypatch):
    """El corto de 'nada para descargar' devuelve antes del remove(): no hay
    fase larga que proteger y el llamador sigue usando su sesión (el resumen
    de vigentes ya viene contado en presuccess/total)."""
    monkeypatch.setattr(fs, "_fund_worker",
                        lambda *a, **k: pytest.fail("no debía correr"))

    s = get_session()
    s.query(Asset).all()
    out = fs._run_fund_batch([], presuccess=7, total=7)

    assert out == {"total": 7, "success": 7, "errors": []}
    assert fs._ScopedSession.registry.has() is True
