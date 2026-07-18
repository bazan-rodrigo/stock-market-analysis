"""query_values_asof: semántica as-of (última fila <= target_date por
activo, con tope de antigüedad). Única prueba de la suite que toca una
tabla — contra el sqlite stub local (hermético, se crea y borra acá),
nunca contra MySQL. Se justifica porque esta semántica ya causó dos bugs
reales (señales semanales/mensuales en 0, filtro descartando todo)."""
from datetime import date

import pytest
import sqlalchemy as sa

from app.database import engine, get_session
from app.models.indicator_store import (
    ASOF_MAX_LOOKBACK_DAYS,
    get_ind_table,
    query_values_asof,
)

_CODE = "zz_test_asof"  # prefijo zz: no colisiona con indicadores reales


@pytest.fixture()
def asof_table():
    with engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS ind_{_CODE}"))
        conn.execute(sa.text(
            f"CREATE TABLE ind_{_CODE} ("
            "  asset_id INTEGER NOT NULL,"
            "  date DATE NOT NULL,"
            "  value VARCHAR(30),"
            "  PRIMARY KEY (asset_id, date))"
        ))
    yield
    with engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS ind_{_CODE}"))
    # limpiar el caché de reflexión de MetaData para futuras corridas
    from app.models import indicator_store as _mod
    _mod._meta.remove(_mod._meta.tables[f"ind_{_CODE}"])


def _insert(rows):
    tbl = get_ind_table(_CODE)
    with engine.begin() as conn:
        conn.execute(tbl.insert(), [
            {"asset_id": a, "date": d, "value": v} for a, d, v in rows
        ])


def test_asof_toma_la_ultima_fila_menor_o_igual(asof_table):
    _insert([
        (1, date(2026, 7, 5), "vieja"),
        (1, date(2026, 7, 8), "exacta"),
        (2, date(2026, 7, 6), "domingo"),   # etiqueta semanal previa
        (3, date(2026, 7, 9), "futura"),    # posterior al target: no cuenta
    ])
    out = query_values_asof(get_session(), _CODE, date(2026, 7, 8))
    assert out == {1: "exacta", 2: "domingo"}


def test_asof_respeta_el_tope_de_antiguedad(asof_table):
    from datetime import timedelta
    target = date(2026, 7, 8)
    dentro = target - timedelta(days=ASOF_MAX_LOOKBACK_DAYS)
    fuera  = target - timedelta(days=ASOF_MAX_LOOKBACK_DAYS + 1)
    _insert([
        (1, dentro, "al_limite"),
        (2, fuera,  "zombie"),  # activo que dejó de cotizar: no debe aparecer
    ])
    out = query_values_asof(get_session(), _CODE, target)
    assert out == {1: "al_limite"}


def test_asof_columna_null_en_la_cola_arrastra_la_ultima_valida(asof_table):
    """As-of POR COLUMNA (fiel, ver design_ind_wide_tables.md): si la fila más
    reciente tiene value NULL se salta y se arrastra el último valor válido
    dentro del tope. En las ind_{code} per-código no ocurre (no guardan value
    NULL), pero en las tablas anchas una columna queda NULL en fechas que otro
    código escribió — la semántica debe ser idéntica en ambos caminos de as-of
    (query_values_asof y el _Sweep del backfill de rango)."""
    _insert([
        (1, date(2026, 7, 7), "buena"),
        (1, date(2026, 7, 8), None),  # la más reciente es NULL → se salta
    ])
    out = query_values_asof(get_session(), _CODE, date(2026, 7, 8))
    assert out == {1: "buena"}


def test_asof_tabla_vacia(asof_table):
    assert query_values_asof(get_session(), _CODE, date(2026, 7, 8)) == {}
