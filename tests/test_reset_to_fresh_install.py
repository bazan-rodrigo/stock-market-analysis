"""reset_to_fresh_install deja la base COMO RECIÉN INSTALADA: vacía TODO
—incluido lo que clean_data preserva (activos, definiciones, usuarios)—,
resiembra los datos integrados y recrea admin/admin123. Además dropea las
tablas dinámicas sig_/strat_res_ que quedan sin definición. Sobre el sqlite
stub. No hay alembic_version en el stub: el reset debe funcionar igual (y no
tocarla en producción, donde la versión de migraciones queda intacta)."""
import json

import pytest
import sqlalchemy as sa

from app.database import Base, Session, engine, get_session
from app.models import signal_store


@pytest.fixture()
def db():
    import app.models  # noqa: F401 — registra los modelos en Base.metadata
    Session.remove()
    Base.metadata.create_all(engine)
    yield
    # Teardown: dropear las dinámicas y dejar las tablas core vacías, para no
    # contaminar otros tests con los datos integrados que resiembra el reset.
    sig, strat = signal_store._list_dynamic_tables()
    with engine.begin() as conn:
        for name in list(sig.values()) + list(strat.values()):
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))
    for name in list(sig.values()) + list(strat.values()):
        if name in signal_store._meta.tables:
            signal_store._meta.remove(signal_store._meta.tables[name])
    from app.services import cleanup_service
    with engine.begin() as conn:
        cleanup_service._fresh_install_wipe(conn)
    Session.remove()


def _seed_extra():
    """Carga datos 'a mano' que clean_data preservaría pero el reset borra:
    un usuario, una fuente propia, un activo, una señal (con su tabla) y una
    estrategia (con su tabla)."""
    from app.models import Asset, PriceSource, User
    from app.models.signal_definition import SignalDefinition
    from app.models.strategy import Strategy

    s = get_session()
    u = User(username="alice", role="analyst", active=True)
    u.set_password("secreta")
    s.add(u)

    src = PriceSource(name="Custom", description="fuente propia")
    s.add(src)
    s.flush()
    s.add(Asset(ticker="TEST", name="Prueba", price_source_id=src.id))

    sig = SignalDefinition(key="k_custom", name="Custom", formula_type="range",
                           params=json.dumps({"min": 0, "max": 100}))
    s.add(sig)
    strat = Strategy(name="EstrategiaCustom", is_public=True)
    s.add(strat)
    s.commit()
    sig_id, strat_id = sig.id, strat.id
    # Soltar la conexión antes del DDL: sqlite admite un solo escritor y la tx
    # abierta de la sesión trabaría el CREATE TABLE ("database is locked").
    Session.remove()
    signal_store.ensure_sig_table(sig_id)
    signal_store.ensure_strat_table(strat_id)
    return sig_id, strat_id


def test_reset_deja_base_como_recien_instalada(db):
    from app.models import Asset, PriceSource, User
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.signal_definition import SignalDefinition
    from app.models.strategy import Strategy
    from app.services import cleanup_service
    from app.services.startup_service import _BUILTIN_INDICATORS

    sig_id, strat_id = _seed_extra()
    # Precondición: las tablas dinámicas propias existen.
    assert sa.inspect(engine).has_table(signal_store.sig_table_name(sig_id))
    assert sa.inspect(engine).has_table(signal_store.strat_table_name(strat_id))

    cleanup_service.reset_to_fresh_install()
    Session.remove()  # ver estado fresco, sin identity map viejo
    s = get_session()

    # Usuarios: solo admin/admin123.
    users = s.query(User).all()
    assert [u.username for u in users] == ["admin"]
    admin = users[0]
    assert admin.role == "admin" and admin.is_admin
    assert admin.check_password("admin123")

    # Fuentes de precio: solo las integradas, sin la propia.
    assert {r.name for r in s.query(PriceSource).all()} == {
        "Yahoo Finance", "Ambito", "Calculado"}

    # Activos: solo el integrado (el 'TEST' se borró).
    assert [a.ticker for a in s.query(Asset).all()] == ["RIESGO_PAIS_AR"]

    # Definiciones de señal/estrategia: borradas (no se resiembran).
    assert s.query(SignalDefinition).count() == 0
    assert s.query(Strategy).count() == 0

    # Indicadores: exactamente los integrados.
    assert s.query(IndicatorDefinition).count() == len(_BUILTIN_INDICATORS)

    # Tablas dinámicas propias: dropeadas por el reconciliador (ya sin
    # definición que las respalde).
    sig_tabs, strat_tabs = signal_store._list_dynamic_tables()
    assert sig_tabs == {} and strat_tabs == {}
    assert not sa.inspect(engine).has_table(signal_store.sig_table_name(sig_id))
    assert not sa.inspect(engine).has_table(
        signal_store.strat_table_name(strat_id))


def test_reset_devuelve_las_tablas_vaciadas(db):
    """El dict de retorno lista las tablas vaciadas (para el mensaje de la UI y
    del script), incluidas las que clean_data no toca (assets, users…)."""
    from app.services import cleanup_service

    _seed_extra()
    res = cleanup_service.reset_to_fresh_install()

    assert "tables" in res and len(res["tables"]) > 0
    assert "assets" in res["tables"]
    assert "users" in res["tables"]
