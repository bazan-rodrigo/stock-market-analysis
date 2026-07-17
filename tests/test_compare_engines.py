"""
Lógica de comparación del script de paridad entre motores
(scripts/compare_engines.py, fase 5 del soporte dual).
"""
from datetime import date
from pathlib import Path

import sqlalchemy as sa

from scripts import compare_engines as ce

ROOT = Path(__file__).resolve().parent.parent


# ── compare_date_aggregates ───────────────────────────────────────────────────

def test_agregados_iguales_sin_problemas():
    a = {"2026-01-02": (10, 123.456), "2026-01-03": (10, -50.0)}
    assert ce.compare_date_aggregates(a, dict(a), 1e-6) == []


def test_agregados_toleran_diferencia_de_precision():
    # FLOAT de 4 bytes (MySQL) vs double precision (PG): misma suma con
    # ruido relativo chico no es diferencia
    a = {"2026-01-02": (10, 1000.0)}
    b = {"2026-01-02": (10, 1000.0000004)}
    assert ce.compare_date_aggregates(a, b, 1e-6) == []


def test_agregados_detectan_count_suma_y_fechas():
    a = {"2026-01-02": (10, 100.0), "2026-01-03": (5, 1.0)}
    b = {"2026-01-02": (9, 100.0), "2026-01-04": (5, 1.0)}
    problems = ce.compare_date_aggregates(a, b, 1e-6)
    assert any("count 10 vs 9" in p for p in problems)
    assert any("2026-01-03 solo en" in p for p in problems)
    assert any("2026-01-04 solo en" in p for p in problems)

    b2 = {"2026-01-02": (10, 100.1), "2026-01-03": (5, 1.0)}
    assert any("sum" in p for p in ce.compare_date_aggregates(a, b2, 1e-6))


# ── compare_rankings ──────────────────────────────────────────────────────────

def test_ranking_identico_ok():
    r = [(1, 9.0), (2, 5.0), (3, None)]
    errors, warnings = ce.compare_rankings(r, list(r), 1e-6)
    assert errors == [] and warnings == []


def test_ranking_swap_por_empate_es_warning():
    # scores prácticamente iguales: el orden puede resolverse distinto por
    # precisión de almacenamiento — no es falta de paridad
    a = [(1, 5.0000001), (2, 5.0), (3, 1.0)]
    b = [(2, 5.0), (1, 5.0000001), (3, 1.0)]
    errors, warnings = ce.compare_rankings(a, b, 1e-6)
    assert errors == []
    assert len(warnings) == 2   # las dos posiciones intercambiadas


def test_ranking_desorden_real_es_error():
    a = [(1, 9.0), (2, 5.0), (3, 1.0)]
    b = [(3, 1.0), (2, 5.0), (1, 9.0)]
    errors, _ = ce.compare_rankings(a, b, 1e-6)
    assert errors and "pos 0" in errors[0]


def test_ranking_conjuntos_distintos():
    errors, _ = ce.compare_rankings([(1, 9.0)], [(2, 9.0)], 1e-6)
    assert errors == ["conjuntos de asset_id distintos"]


# ── Helpers SQL sobre sqlite ──────────────────────────────────────────────────

def _engine_con_strat():
    eng = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    t = sa.Table("strat_res_1", meta,
                 sa.Column("asset_id", sa.Integer, primary_key=True),
                 sa.Column("date", sa.Date, primary_key=True),
                 sa.Column("score", sa.Float))
    sa.Table("ind_rsi_14", meta,
             sa.Column("asset_id", sa.Integer, primary_key=True),
             sa.Column("date", sa.Date, primary_key=True),
             sa.Column("value", sa.Float))
    sa.Table("ind_asset_meta", meta,
             sa.Column("asset_id", sa.Integer, primary_key=True))
    meta.create_all(eng)
    d = date(2026, 1, 2)
    with eng.begin() as c:
        c.execute(t.insert(), [
            {"asset_id": 1, "date": d, "score": 5.0},
            {"asset_id": 2, "date": d, "score": 9.0},
            {"asset_id": 3, "date": d, "score": None},
        ])
    return eng, d


def test_ranking_sql_ordena_desc_con_nulls_al_final():
    eng, d = _engine_con_strat()
    with eng.connect() as c:
        rank = ce._ranking(c, "strat_res_1", d)
    assert [a for a, _ in rank] == [2, 1, 3]


def test_dyn_tables_excluye_ind_asset_meta():
    eng, _ = _engine_con_strat()
    assert ce._dyn_tables(eng) == ["ind_rsi_14", "strat_res_1"]


def test_value_col_y_agregados():
    eng, d = _engine_con_strat()
    assert ce._value_col(eng, "strat_res_1") == "score"
    with eng.connect() as c:
        agg = ce._date_aggregates(c, "strat_res_1", "score")
    assert agg == {str(d): (2, 14.0)}   # el NULL no cuenta ni suma
