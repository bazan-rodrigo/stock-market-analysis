"""Ciclo de vida de las tablas dinámicas sig_{id}/strat_res_{id}: la tabla
vive y muere con su definición (save/delete de señales y estrategias), y el
reconciliador repara los dos estados que un crash puede dejar (tabla
huérfana / definición sin tabla). Sobre el sqlite stub."""
import json

import pytest
import sqlalchemy as sa

from app.database import Base, engine, get_session
from app.models import signal_store


def _table_exists(name: str) -> bool:
    return sa.inspect(engine).has_table(name)


@pytest.fixture()
def db():
    import app.models  # noqa: F401
    Base.metadata.create_all(engine)
    tables = ("strategy_component", "strategy", "`signal`",
              "signal_eval_log", "indicator_definitions")
    with engine.begin() as conn:
        for t in tables:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    sig, strat = signal_store._list_dynamic_tables()
    with engine.begin() as conn:
        for name in list(sig.values()) + list(strat.values()):
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))
        for t in tables:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    for name in list(sig.values()) + list(strat.values()):
        if name in signal_store._meta.tables:
            signal_store._meta.remove(signal_store._meta.tables[name])
    get_session().rollback()


def _mk_signal(key="lc_sig"):
    from app.models.indicator_definition import IndicatorDefinition
    from app.services import signal_service

    s = get_session()
    if not s.query(IndicatorDefinition).filter(
            IndicatorDefinition.code == "trend_daily").first():
        s.add(IndicatorDefinition(code="trend_daily", name="t", category="t",
                                  type="str", keep_history=True))
        s.commit()
    return signal_service.save_signal(
        key=key, name=key, source="asset", formula_type="discrete_map",
        params_json=json.dumps({"map": {"bullish": 100}}),
        indicator_key="trend_daily", is_public=True)


def test_alta_y_baja_de_senal_crean_y_dropean_su_tabla(db):
    from app.services import signal_service

    sig = _mk_signal()
    name = signal_store.sig_table_name(sig.id)
    assert _table_exists(name), "save_signal debe crear sig_{id}"

    # el renombre de la key NO toca la tabla (nombrada por id inmutable)
    signal_service.save_signal(
        key="lc_sig_renombrada", name="x", source="asset",
        formula_type="discrete_map",
        params_json=json.dumps({"map": {"bullish": 100}}),
        indicator_key="trend_daily", signal_id=sig.id)
    assert _table_exists(name)

    signal_service.delete_signal(sig.id)
    assert not _table_exists(name), "delete_signal debe dropear sig_{id}"


def test_alta_y_baja_de_estrategia_crean_y_dropean_su_tabla(db):
    from app.services import strategy_service

    sig = _mk_signal()
    strat = strategy_service.save_strategy(
        name="lc_estrategia",
        components=[{"signal_key": sig.key, "weight": 1.0}], is_public=True)
    name = signal_store.strat_table_name(strat.id)
    assert _table_exists(name), "save_strategy debe crear strat_res_{id}"

    strategy_service.delete_strategy(strat.id)
    assert not _table_exists(name), "delete_strategy debe dropear la tabla"


def test_reconciliador_repara_ambos_lados(db):
    s = get_session()
    sig = _mk_signal()
    sig_name = signal_store.sig_table_name(sig.id)

    # Lado 1 (crash post-commit de un delete): tabla huérfana sin definición
    orphan_sig = signal_store.ensure_sig_table(sig.id + 1000).name
    orphan_strat = signal_store.ensure_strat_table(2000).name
    # Lado 2 (crash post-commit de un alta): definición sin tabla
    with engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE {sig_name}"))
    signal_store._meta.remove(signal_store._meta.tables[sig_name])

    result = signal_store.reconcile_dynamic_tables(s)

    assert sorted(result["dropped"]) == sorted([orphan_sig, orphan_strat])
    assert result["created"] == [sig_name]
    assert _table_exists(sig_name)
    assert not _table_exists(orphan_sig)
    assert not _table_exists(orphan_strat)
