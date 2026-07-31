"""Panel de Fuerza Relativa 52W del gráfico técnico.

Es el ÚNICO indicador del gráfico que no se calcula en el browser: la serie
sale de relative_strength_52w (columna de ind_daily) porque recalcularla en JS
exigiría mandar también los precios del benchmark. Eso lo pone en un camino
distinto al del resto —Python lee, JS solo dibuja— y son esos dos extremos los
que se prueban acá.

Toca una tabla contra el sqlite stub (hermético, se crea y borra en el
fixture), por el mismo motivo que test_query_values_asof.
"""
import sys
import types
from datetime import date
from pathlib import Path

# chart_callbacks (vía asset_service -> app.sources.yahoo) importa yfinance en
# el header; esta PC y la suite no lo tienen — un stub vacío alcanza: acá nunca
# se descarga nada.
sys.modules.setdefault("yfinance", types.ModuleType("yfinance"))

import pytest
import sqlalchemy as sa
from dash import no_update

from app.callbacks.chart_callbacks import load_rs52w_overlay, update_rs52w_label
from app.database import engine

_CODE = "relative_strength_52w"
_TABLE = f"ind_{_CODE}"

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def rs_table():
    """La suite corre con USE_WIDE_IND_TABLES=0 (ver conftest), así que
    get_ind_table refleja la per-código. En producción es una columna de
    ind_daily, pero el lector es el mismo: _CodeView expone .c.value igual."""
    with engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {_TABLE}"))
        conn.execute(sa.text(
            f"CREATE TABLE {_TABLE} ("
            "  asset_id INTEGER NOT NULL,"
            "  date DATE NOT NULL,"
            "  value FLOAT,"
            "  PRIMARY KEY (asset_id, date))"
        ))
    yield
    with engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {_TABLE}"))
    from app.models import indicator_store as _mod
    if _TABLE in _mod._meta.tables:
        _mod._meta.remove(_mod._meta.tables[_TABLE])


def _insert(rows):
    from app.models.indicator_store import get_ind_table
    tbl = get_ind_table(_CODE)
    with engine.begin() as conn:
        conn.execute(tbl.insert(), [
            {"asset_id": a, "date": d, "value": v} for a, d, v in rows
        ])


# ── Lectura de la serie ──────────────────────────────────────────────────────

def test_devuelve_la_serie_del_activo_ordenada_por_fecha(rs_table):
    _insert([
        (1, date(2026, 7, 3), 12.5),
        (1, date(2026, 7, 1), -4.0),
        (1, date(2026, 7, 2),  0.0),
        (2, date(2026, 7, 1), 99.0),   # otro activo: no se mezcla
    ])
    out = load_rs52w_overlay([1], 1)

    assert out["asset_id"] == 1
    assert out["points"] == [
        ["2026-07-01", -4.0],
        ["2026-07-02",  0.0],
        ["2026-07-03", 12.5],
    ]


def test_saltea_las_filas_sin_valor(rs_table):
    """En la tabla ANCHA cada fila trae los códigos hermanos de la cadencia:
    una fecha puede tener trend_daily y NULL en fuerza relativa (el activo
    todavía no acumula 52 semanas). Esas filas no son puntos del panel."""
    _insert([
        (1, date(2026, 7, 1), None),
        (1, date(2026, 7, 2), None),
        (1, date(2026, 7, 3), 3.25),
    ])
    out = load_rs52w_overlay([1], 1)

    assert out["points"] == [["2026-07-03", 3.25]]


def test_sin_benchmark_no_hay_puntos(rs_table):
    """Sin benchmark configurado el indicador es NULL en toda la historia. El
    contrato con el JS es points vacío -> no abre el panel (en vez de abrir uno
    en blanco); la etiqueta del toggle es la que explica por qué."""
    _insert([(1, date(2026, 7, 1), None)])
    out = load_rs52w_overlay([1], 1)

    assert out["points"] == []


@pytest.mark.parametrize("enabled, asset_id", [
    ([],   1),      # toggle apagado
    (None, 1),
    ([1],  None),   # sin activo elegido
])
def test_no_consulta_si_no_corresponde(enabled, asset_id):
    """Lazy como el resto de los overlays: sin toggle no se toca la base. Sin
    el fixture la tabla no existe, así que si consultara explotaría."""
    assert load_rs52w_overlay(enabled, asset_id) is no_update


# ── Etiqueta del benchmark ───────────────────────────────────────────────────

def test_la_etiqueta_muestra_el_ticker_del_benchmark():
    texto, _ = update_rs52w_label({"benchmark": {"id": 7, "ticker": "SPY"}})
    assert texto == "(vs SPY)"


def test_la_etiqueta_avisa_cuando_no_hay_benchmark():
    """Sin esto el toggle parecería roto: se prende y no pasa nada."""
    texto, _ = update_rs52w_label({"benchmark": None})
    assert texto == "(sin benchmark)"


def test_la_etiqueta_queda_vacia_sin_datos_del_grafico():
    assert update_rs52w_label(None)[0] == ""


# ── Cableado ─────────────────────────────────────────────────────────────────

def test_los_ids_del_overlay_existen_en_el_layout():
    """Un callback que apunta a un id ausente del layout no falla al importar:
    revienta recién al abrir la pantalla. El panel usa cuatro ids nuevos y
    ninguno tiene otra red que lo cubra."""
    callbacks = (ROOT / "app" / "callbacks" / "chart_callbacks.py").read_text(encoding="utf-8")
    layout    = (ROOT / "app" / "pages" / "asset_analysis.py").read_text(encoding="utf-8")

    ids = {"chart-ind-rs52w-1-enabled", "chart-rs52w-label",
           "chart-rs52w-data", "chart-rs52w-data-dummy"}
    faltan = [i for i in sorted(ids)
              if i in callbacks and f'"{i}"' not in layout]

    assert not faltan, (
        "Ids que los callbacks usan y el layout no declara: " + ", ".join(faltan))


def test_el_slot_no_declara_parametros():
    """rs52w entra en _SLOTS solo para heredar el cableado del checkbox. Si
    alguien le agrega params habría que sumarlo a _COLLAPSIBLE y darle su div,
    o el callback de colapso apuntaría a un id inexistente."""
    from app.callbacks.chart_callbacks import _COLLAPSIBLE, _SLOTS

    n_slots, params = _SLOTS["rs52w"]
    assert (n_slots, params) == (1, [])
    assert "rs52w" not in _COLLAPSIBLE
