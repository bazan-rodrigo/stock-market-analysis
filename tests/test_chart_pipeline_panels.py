"""Paneles del gráfico alimentados por el pipeline (ADX, Posición 52W, RVOL).

Como rs52w (ver test_chart_rs52w_overlay), estos tres NO se calculan en el
browser: la serie sale de una columna de ind_daily y el JS solo dibuja. Se
prueban los dos extremos —lo que Python lee y el cableado que el JS necesita—
porque en el medio hay un callback clientside que ningún test de Python ve.

Toca tablas contra el sqlite stub (herméticas, se crean y borran en el fixture).
"""
import re
import sys
import types
from datetime import date
from pathlib import Path

# chart_callbacks (vía asset_service -> app.sources.yahoo) importa yfinance en
# el header; esta PC y la suite no lo tienen — un stub vacío alcanza.
sys.modules.setdefault("yfinance", types.ModuleType("yfinance"))

import pytest
import sqlalchemy as sa
from dash import no_update

from app.callbacks.chart_callbacks import (
    _pipeline_points, load_adx_overlay, load_pricepos_overlay,
    load_rvol_overlay,
)
from app.database import engine

ROOT = Path(__file__).resolve().parent.parent

# (nombre del slot/toggle, código del indicador, callback)
_PANELS = [
    ("adx",      "adx_daily",          load_adx_overlay),
    ("pricepos", "price_position_52w", load_pricepos_overlay),
    ("rvol",     "rvol_daily",         load_rvol_overlay),
]


@pytest.fixture()
def ind_tables():
    """La suite corre con USE_WIDE_IND_TABLES=0 (ver conftest), así que
    get_ind_table refleja la per-código. En producción son columnas de
    ind_daily, pero el lector es el mismo: _CodeView expone .c.value igual."""
    from app.models import indicator_store as _mod
    nombres = [f"ind_{code}" for _, code, _ in _PANELS]
    with engine.begin() as conn:
        for t in nombres:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {t}"))
            conn.execute(sa.text(
                f"CREATE TABLE {t} ("
                "  asset_id INTEGER NOT NULL,"
                "  date DATE NOT NULL,"
                "  value FLOAT,"
                "  PRIMARY KEY (asset_id, date))"
            ))
    yield
    with engine.begin() as conn:
        for t in nombres:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {t}"))
    for t in nombres:
        if t in _mod._meta.tables:
            _mod._meta.remove(_mod._meta.tables[t])


def _insert(code, rows):
    from app.models.indicator_store import get_ind_table
    tbl = get_ind_table(code)
    with engine.begin() as conn:
        conn.execute(tbl.insert(), [
            {"asset_id": a, "date": d, "value": v} for a, d, v in rows
        ])


# ── Lectura de la serie ──────────────────────────────────────────────────────

@pytest.mark.parametrize("name, code, fn", _PANELS)
def test_devuelve_la_serie_del_activo_ordenada(name, code, fn, ind_tables):
    _insert(code, [
        (1, date(2026, 7, 3), 30.0),
        (1, date(2026, 7, 1), 10.0),
        (1, date(2026, 7, 2), 20.0),
        (2, date(2026, 7, 1), 99.0),   # otro activo: no se mezcla
    ])
    out = fn([1], 1)

    assert out["asset_id"] == 1
    assert out["points"] == [
        ["2026-07-01", 10.0], ["2026-07-02", 20.0], ["2026-07-03", 30.0],
    ]


@pytest.mark.parametrize("name, code, fn", _PANELS)
def test_saltea_las_filas_sin_valor(name, code, fn, ind_tables):
    """En la tabla ANCHA cada fila trae los códigos hermanos de la cadencia:
    una fecha puede tener rsi_daily y NULL en esta columna (warm-up de la
    ventana). Esas filas no son puntos del panel."""
    _insert(code, [
        (1, date(2026, 7, 1), None),
        (1, date(2026, 7, 2), 42.0),
    ])
    assert fn([1], 1)["points"] == [["2026-07-02", 42.0]]


@pytest.mark.parametrize("name, code, fn", _PANELS)
@pytest.mark.parametrize("enabled, asset_id", [
    ([],   1),      # toggle apagado
    (None, 1),
    ([1],  None),   # sin activo elegido
])
def test_no_consulta_si_no_corresponde(name, code, fn, enabled, asset_id):
    """Lazy como el resto de los overlays: sin toggle no se toca la base. Sin
    el fixture la tabla no existe, así que si consultara explotaría."""
    assert fn(enabled, asset_id) is no_update


def test_activo_sin_valores_no_abre_el_panel(ind_tables):
    """Contrato con el JS: sin puntos NO se abre el panel (mejor que abrir uno
    en blanco). Pasa de verdad — historia menor a la ventana del indicador, y
    en rvol_daily los sintéticos y las conversiones de moneda, que no tienen
    volumen propio."""
    _insert("rvol_daily", [(1, date(2026, 7, 1), None)])
    assert load_rvol_overlay([1], 1)["points"] == []


def test_tabla_ausente_no_rompe_la_pantalla():
    """Base sin migrar todavía: la columna no existe. El panel tiene que
    quedarse sin datos, no tirar la pantalla de Análisis de Activo abajo."""
    assert _pipeline_points("codigo_que_no_existe", 1) is None


# ── Cableado ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name, code, fn", _PANELS)
def test_los_ids_del_panel_existen_en_el_layout(name, code, fn):
    """Un callback que apunta a un id ausente del layout no falla al importar:
    revienta recién al abrir la pantalla."""
    callbacks = (ROOT / "app" / "callbacks" / "chart_callbacks.py").read_text(encoding="utf-8")
    layout    = (ROOT / "app" / "pages" / "asset_analysis.py").read_text(encoding="utf-8")

    ids = {f"chart-ind-{name}-1-enabled", f"chart-{name}-data",
           f"chart-{name}-data-dummy"}
    faltan = [i for i in sorted(ids)
              if i in callbacks and f'"{i}"' not in layout]

    assert not faltan, (
        "Ids que los callbacks usan y el layout no declara: " + ", ".join(faltan))


@pytest.mark.parametrize("name, code, fn", _PANELS)
def test_el_slot_no_declara_parametros(name, code, fn):
    """Entran en _SLOTS solo para heredar el cableado del checkbox. Si alguien
    les agrega params habría que sumarlos a _COLLAPSIBLE y darles su div, o el
    callback de colapso apuntaría a un id inexistente."""
    from app.callbacks.chart_callbacks import _COLLAPSIBLE, _SLOTS

    assert _SLOTS[name] == (1, [])
    assert name not in _COLLAPSIBLE


def test_el_orden_de_los_stores_coincide_con_la_firma_del_js():
    """EL trinquete que importa. El render clientside recibe los stores como
    argumentos POSICIONALES: si el orden de los State(...) y el de los
    parámetros de la función JS se desalinean, cada panel dibuja la serie de
    otro — sin error, en silencio. Ningún otro test lo ve, porque el JS no lo
    ejecuta nadie en la suite.
    """
    src = (ROOT / "app" / "callbacks" / "chart_callbacks.py").read_text(encoding="utf-8")

    # Orden en que se declaran los State("chart-*-data") del render principal.
    stores = re.findall(r'State\("chart-([a-z0-9]+)-data", "data"\)', src)

    # Orden en que la firma del JS los recibe (…, xxxData, yyyData, …).
    # chartData queda afuera: es el Input principal del render, no un State.
    firma = re.search(r"function\(chartData,(.*?)\)", src, re.S).group(1)
    args  = [a.strip()[:-4].lower()
             for a in firma.split(",") if a.strip().endswith("Data")]

    # Que no pase en vacío: si un cambio de formato rompe los dos regex a la
    # vez, [] == [] daría verde sin haber comprobado nada.
    assert set(stores) >= {"rs52w", "adx", "pricepos", "rvol"}

    assert stores == args, (
        f"Stores {stores} vs argumentos del JS {args}: el render los recibe "
        "por posición, desalinearlos cruza las series entre paneles.")
