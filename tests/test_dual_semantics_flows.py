"""
Tests funcionales de los caminos duales (fases 1 y 3 del soporte dual,
ver docs/notes/design_postgresql_dual.md): ejercitan DE VERDAD, sobre el
stub sqlite de la suite, flujos que antes solo estaban cubiertos a nivel
helper de db_compat. sqlite comparte con PostgreSQL las dos propiedades
que importan acá: '=' case-sensitive y soporte de ON CONFLICT — antes de
la capa dual estos tests no podían ni ejecutarse (el SQL era MySQL-only).
"""
import json
from datetime import date

import pytest
import sqlalchemy as sa

from app.database import Base, Session, engine, get_session


# ── _write_ind_series: el camino caliente de escritura de ind_{code} ─────────

def test_write_ind_series_inserta_y_upsertea_de_verdad():
    import app.models  # noqa: F401
    from app.models.indicator_store import ensure_ind_table, get_ind_table
    from app.services.technical_service import _write_ind_series

    # assets primero: el autoload de ind_* sigue su FK hacia assets
    Base.metadata.create_all(engine)
    ensure_ind_table("dual_flow_num", "num")
    s = get_session()
    d1, d2 = date(2026, 1, 2), date(2026, 1, 5)
    try:
        # alta: existing=set() vacío → escribe todas las fechas (INSERT)
        n = _write_ind_series(s, "dual_flow_num", 1, [d1, d2], [1.5, 2.5], set())
        s.commit()
        assert n == 2

        # segunda pasada sobre las MISMAS fechas con valores nuevos: las PK
        # ya existen → acá dispara la rama UPDATE del upsert crudo
        # (ON DUPLICATE KEY en MySQL / ON CONFLICT en PG y sqlite)
        n = _write_ind_series(s, "dual_flow_num", 1, [d1, d2], [9.0, 7.5], set())
        s.commit()
        assert n == 2

        t = get_ind_table("dual_flow_num")
        rows = dict(s.execute(sa.select(t.c.date, t.c.value)).fetchall())
        assert rows == {d1: 9.0, d2: 7.5}
    finally:
        s.rollback()
        with engine.begin() as conn:
            conn.execute(sa.text("DROP TABLE IF EXISTS ind_dual_flow_num"))
        from app.models import indicator_store
        tbl = indicator_store._meta.tables.get("ind_dual_flow_num")
        if tbl is not None:
            indicator_store._meta.remove(tbl)
        Session.remove()


# ── Ranking de estrategia: un score NULL nunca encabeza el ranking ────────────

def test_ranking_de_estrategia_pone_nulls_al_final():
    import app.models  # noqa: F401
    from app.models import Asset, signal_store
    from app.services.strategy_service import get_strategy_results

    Base.metadata.create_all(engine)
    s = get_session()
    d = date(2026, 1, 2)
    try:
        # FKs colgantes: sqlite no las aplica (patrón de la suite)
        for aid, tk in ((90901, "DUALT1"), (90902, "DUALT2"), (90903, "DUALT3")):
            if s.get(Asset, aid) is None:
                s.add(Asset(id=aid, ticker=tk, name=tk, country_id=1,
                            market_id=1, instrument_type_id=1, currency_id=1,
                            price_source_id=1))
        s.commit()

        rt = signal_store.ensure_strat_table(99901)
        s.execute(rt.insert(), [
            {"asset_id": 90901, "date": d, "score": 5.0, "pct": None},
            {"asset_id": 90902, "date": d, "score": None, "pct": None},
            {"asset_id": 90903, "date": d, "score": 9.0, "pct": None},
        ])
        s.commit()

        res = get_strategy_results(99901, d)
        # score DESC con el NULL al FINAL — en PG un DESC puro lo pondría
        # primero y encabezaría el ranking (order_desc_nulls_last)
        assert [r["asset_id"] for r in res] == [90903, 90901, 90902]
        assert res[-1]["score"] is None
    finally:
        s.rollback()
        with engine.begin() as conn:
            conn.execute(sa.text("DROP TABLE IF EXISTS strat_res_99901"))
            conn.execute(sa.text(
                "DELETE FROM assets WHERE id IN (90901, 90902, 90903)"))
        tbl = signal_store._meta.tables.get("strat_res_99901")
        if tbl is not None:
            signal_store._meta.remove(tbl)
        Session.remove()


# ── Alta de señal: una key repetida con otro CASO es duplicado ────────────────

def test_alta_de_senal_con_key_en_otro_caso_es_duplicado():
    import app.models  # noqa: F401
    from app.models.indicator_definition import IndicatorDefinition
    from app.services import signal_service

    Base.metadata.create_all(engine)
    s = get_session()
    if not s.query(IndicatorDefinition).filter(
            IndicatorDefinition.code == "trend_daily").first():
        s.add(IndicatorDefinition(code="trend_daily", name="t", category="t",
                                  type="str", keep_history=True))
        s.commit()

    sig = signal_service.save_signal(
        key="dual_ci_senal", name="ci", source="asset",
        formula_type="discrete_map",
        params_json=json.dumps({"map": {"bullish": 100}}),
        indicator_key="trend_daily", is_public=True)
    try:
        # En MySQL la collation ya hacía este match; sqlite (como PG)
        # compara '=' case-sensitive: sin ci_equals esto crearía una
        # señal duplicada en vez de rechazarla
        with pytest.raises(ValueError, match="Ya existe una señal"):
            signal_service.save_signal(
                key="DUAL_CI_SENAL", name="ci2", source="asset",
                formula_type="discrete_map",
                params_json=json.dumps({"map": {"bullish": 100}}),
                indicator_key="trend_daily", is_public=True)
    finally:
        signal_service.delete_signal(sig.id)
        Session.remove()
