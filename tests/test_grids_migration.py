"""Reglas de las grillas ag-grid y red contra una migración a medias.

Las pantallas que pasaron de `dash_table.DataTable` a `dag.AgGrid` cambiaron el
nombre de sus props: `data` → `rowData` y `selected_rows` (índices) →
`selectedRows` (las filas enteras). Un callback que quede con el nombre viejo
NO rompe ningún import: Dash lo registra igual y la pantalla falla recién en el
navegador, en silencio. Por eso el chequeo es sobre el texto de los módulos.
"""
import re
from pathlib import Path

import pytest

from app.components.grids import (
    DEFAULT_COL_DEF, grid_options, import_status_conditions, multi_selection,
    score_col, status_col, status_conditions, text_col,
)

ROOT = Path(__file__).resolve().parent.parent

# (módulo de callbacks, id de la grilla) de cada pantalla migrada
MIGRADAS = [
    ("app/callbacks/screener_signals_callbacks.py",       "ss-grid"),
    ("app/callbacks/asset_callbacks.py",                  "assets-table"),
    ("app/callbacks/price_callbacks.py",                  "prices-log-table"),
    ("app/callbacks/admin_fundamental_update_callbacks.py", "fund-upd-table"),
    ("app/callbacks/import_callbacks.py",                 "import-log-table"),
    ("app/callbacks/events_import_callbacks.py",          "ev-import-log-table"),
]


@pytest.mark.parametrize("rel,grid_id", MIGRADAS)
def test_ningun_callback_quedo_con_las_props_de_la_datatable(rel, grid_id):
    src = (ROOT / rel).read_text(encoding="utf-8")

    viejas = re.findall(
        rf'(?:Output|Input|State)\(\s*"{re.escape(grid_id)}"\s*,\s*'
        r'"(data|selected_rows|derived_virtual_data|active_cell)"', src)

    assert not viejas, (
        f"{rel} todavía usa props de DataTable sobre '{grid_id}': "
        f"{sorted(set(viejas))}. En ag-grid son rowData / selectedRows.")


@pytest.mark.parametrize("rel,grid_id", MIGRADAS)
def test_nadie_indexa_las_filas_por_posicion(rel, grid_id):
    """`data[i] for i in sel_rows` era el patrón de la DataTable, donde la
    selección eran índices. Con la grilla, `sel_rows` YA son las filas: si
    quedara ese patrón, indexaría una fila con un número y explotaría —o peor,
    devolvería la fila equivocada— justo en pantallas que borran datos."""
    src = (ROOT / rel).read_text(encoding="utf-8")

    assert "data[i]" not in src, f"{rel} indexa filas por posición"
    assert "data[sel_rows" not in src, f"{rel} indexa filas por posición"


# ── Configuración compartida ─────────────────────────────────────────────────

def test_el_tema_es_legacy_para_que_aplique_la_hoja_de_estilos():
    """ag-grid 35 arranca con la Theming API (clara) y ahí assets/ag_grid.css
    no se aplica: la grilla se vería blanca sobre una app oscura."""
    assert grid_options()["theme"] == "legacy"


def test_la_paginacion_se_prende_solo_si_se_pide():
    assert "pagination" not in grid_options()
    assert grid_options(page_size=30)["paginationPageSize"] == 30


def test_clickear_la_fila_nunca_selecciona():
    """Estas selecciones disparan borrados y redescargas completas: marcar
    tiene que ser un acto deliberado sobre el checkbox."""
    sel = multi_selection()

    assert sel["mode"] == "multiRow"
    assert sel["checkboxes"] is True
    assert sel["enableClickSelection"] is False


def test_el_filtro_por_columna_queda_a_la_vista():
    """La DataTable mostraba el casillero de filtro siempre; ag-grid lo
    esconde en el menú salvo que se pida explícitamente."""
    assert DEFAULT_COL_DEF["floatingFilter"] is True
    assert DEFAULT_COL_DEF["sortable"] is True


# ── Colores de estado ────────────────────────────────────────────────────────

def test_las_condiciones_de_estado_apuntan_al_campo_declarado():
    conds = status_conditions("indicator_result")

    assert all("params.data.indicator_result" in c["condition"] for c in conds)
    assert len(conds) == 2


def test_el_placeholder_solo_se_apaga_si_se_pide():
    assert len(status_conditions("result")) == 2
    assert len(status_conditions("result", dim_placeholder=True)) == 3


def test_el_import_colorea_los_tres_estados():
    valores = [c["condition"] for c in import_status_conditions()]

    assert any("imported" in c for c in valores)
    assert any("error" in c for c in valores)
    assert any("skipped" in c for c in valores)


# ── Constructores de columna ─────────────────────────────────────────────────

def test_toda_columna_declara_su_field():
    """Sin `field` la columna queda vacía en pantalla."""
    cols = [text_col("x", "X"), status_col("result", "Resultado"),
            score_col("score", "Score", max_abs=10)]

    assert all("field" in c for c in cols)


def test_el_score_sin_maximo_no_dibuja_barra():
    assert score_col("d", "Δ", max_abs=None)["cellRendererParams"]["barMax"] == 0
