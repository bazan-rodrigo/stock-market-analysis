"""Configuración común de las grillas ag-grid.

Por qué existe: la app venía con `dash_table.DataTable`, que manda TODAS las
filas al navegador aunque pagine de a 30 — con miles de activos se traba. Las
grillas de ag-grid virtualizan (dibujan solo lo visible), pero traen su propia
configuración larga: si cada pantalla la copia y pega, en tres pantallas ya hay
tres criterios distintos. Acá vive una sola vez.

El tema visual va por `assets/ag_grid.css` (variables CSS) y los renderers de
celda por `assets/dashAgGridComponentFunctions.js`. Los colores salen siempre de
`ui_constants` y viajan al renderer como parámetros: el JavaScript no decide
nada, solo pinta.
"""
from app.components.ui_constants import (
    BG_CARD, COLOR_LINK, COLOR_NEGATIVE, COLOR_NEUTRAL, COLOR_POSITIVE,
    COLOR_WARNING, TEXT_DIM, TEXT_FAINT, TEXT_MUTED,
)

# ── Tema ─────────────────────────────────────────────────────────────────────
# ag-grid 35 arranca con la Theming API nueva, que se configura desde
# JavaScript. "legacy" vuelve a los temas por hoja de estilos, que es lo que
# permite alinearlo con la app desde assets/ag_grid.css sin escribir JS.
THEME_CLASS = "ag-theme-quartz-dark"

DEFAULT_COL_DEF = {
    "sortable": True,
    "resizable": True,
    "filter": True,
    # Casillero de filtro visible debajo de cada encabezado. Por default
    # ag-grid lo esconde en el menú de la columna, pero las DataTable que estas
    # grillas reemplazan lo tenían siempre a la vista y es como se usa la app:
    # esconderlo sería perder un acceso que ya estaba.
    "floatingFilter": True,
    "suppressMovable": True,
}


def multi_selection() -> dict:
    """Selección múltiple por checkbox, en la API de selección vigente desde
    ag-grid 33 (la forma vieja `rowSelection="multiple"` quedó deprecada).

    `enableClickSelection` en False a propósito: clickear una fila NO la
    selecciona. En estas pantallas la selección dispara operaciones pesadas
    —incluida la redescarga completa, que borra la historia de precios—, así
    que tiene que ser un acto deliberado sobre el checkbox.
    """
    return {
        "mode": "multiRow",
        "checkboxes": True,
        "headerCheckbox": True,
        "enableClickSelection": False,
    }


def single_selection(*, click_selects: bool = True) -> dict:
    """Selección de una sola fila. Acá sí conviene que el click seleccione: es
    "elegí de qué cartera querés ver el detalle", no una acción destructiva."""
    return {
        "mode": "singleRow",
        "checkboxes": False,
        "enableClickSelection": click_selects,
    }


def grid_options(*, page_size: int | None = None, **overrides) -> dict:
    """dashGridOptions base. `page_size` prende la paginación (las pantallas
    que venían de DataTable la conservan); sin él, scroll virtualizado."""
    opts = {
        "theme": "legacy",
        "animateRows": False,
        "suppressCellFocus": True,
        "rowHeight": 30,
        "headerHeight": 34,
    }
    if page_size:
        opts["pagination"] = True
        opts["paginationPageSize"] = page_size
    opts.update(overrides)
    return opts


# ── Columnas con formato propio ──────────────────────────────────────────────

def score_col(field: str, header: str, *, max_abs: float | None,
              pos_th: float = 20, neg_th: float = -20,
              plus_sign: bool = False, width: int = 110,
              header_tooltip: str | None = None) -> dict:
    """Columna de score: número coloreado y —si `max_abs` viene— barra
    proporcional.

    Los umbrales y los colores viajan al renderer como parámetros: son reglas
    de negocio (verde desde +20, rojo desde −20) y viven en Python. `max_abs`
    es el mayor valor absoluto del conjunto que se está mostrando, así la barra
    queda relativa a la pantalla — igual que antes de la grilla.
    """
    col = {
        "field": field,
        "headerName": header,
        "width": width,
        "cellRenderer": "ScoreCell",
        "type": "numericColumn",
        "cellRendererParams": {
            "barMax": max_abs or 0,
            "posTh": pos_th,
            "negTh": neg_th,
            "posColor": COLOR_POSITIVE,
            "negColor": COLOR_NEGATIVE,
            "neutralColor": COLOR_NEUTRAL,
            "emptyColor": TEXT_FAINT,
            "barBg": BG_CARD,
            "plusSign": plus_sign,
        },
    }
    if header_tooltip:
        col["headerTooltip"] = header_tooltip
    return col


def ticker_col(analysis_href: str, history_href: str | None = None,
               *, width: int = 120) -> dict:
    """Columna de ticker con enlace al análisis del activo (y opcionalmente al
    historial). Los href llevan `{id}`, que el renderer reemplaza con el
    asset_id de la fila."""
    return {
        "field": "ticker",
        "headerName": "Ticker",
        "width": width,
        "pinned": "left",
        "cellRenderer": "TickerLinks",
        "cellRendererParams": {
            "analysisHref": analysis_href,
            "historyHref": history_href or analysis_href,
            "linkColor": COLOR_LINK,
            "dimColor": TEXT_DIM,
        },
    }


def status_conditions(field: str, *, dim_placeholder: bool = False) -> list[dict]:
    """Reglas de color para una columna de resultado (Éxito / Error).

    `styleConditions` es la conditional formatting propia de dash-ag-grid: la
    condición se evalúa del lado del cliente, así que sigue funcionando después
    de ordenar o filtrar — a diferencia del `filter_query` de la DataTable, que
    había que repetir por columna.

    `dim_placeholder` apaga las filas con "—" (nunca se intentó), para que no
    compitan visualmente con las que sí tienen resultado.
    """
    conds = [
        {"condition": f"params.data.{field} == 'Éxito'",
         "style": {"color": COLOR_POSITIVE}},
        {"condition": f"params.data.{field} == 'Error'",
         "style": {"color": COLOR_NEGATIVE}},
    ]
    if dim_placeholder:
        conds.append({"condition": f"params.data.{field} == '—'",
                      "style": {"color": TEXT_DIM}})
    return conds


def import_status_conditions(field: str = "status") -> list[dict]:
    """Los tres estados de un import: importado, con error, omitido.

    "Omitido" va en amarillo de advertencia y no en el naranja suelto que usaba
    la tabla anterior: es el color que el sistema de diseño ya tiene para "mirá
    esto, no es un error pero tampoco salió".
    """
    return [
        {"condition": f"params.data.{field} == 'imported'",
         "style": {"color": COLOR_POSITIVE}},
        {"condition": f"params.data.{field} == 'error'",
         "style": {"color": COLOR_NEGATIVE}},
        {"condition": f"params.data.{field} == 'skipped'",
         "style": {"color": COLOR_WARNING}},
    ]


def status_col(field: str, header: str, *, width: int = 110) -> dict:
    """Columna de resultado, coloreada por su propio valor."""
    return {
        "field": field,
        "headerName": header,
        "width": width,
        "cellStyle": {"styleConditions": status_conditions(field)},
    }


def text_col(field: str, header: str, *, width: int = 180,
             muted: bool = False, **extra) -> dict:
    col = {"field": field, "headerName": header, "width": width}
    if muted:
        col["cellStyle"] = {"color": TEXT_MUTED}
    col.update(extra)
    return col


def to_column_defs(columns: list[dict]) -> list[dict]:
    """Traduce el formato de columnas de `dash_table.DataTable` (`{"name",
    "id"}`) al de ag-grid (`{"headerName", "field"}`).

    Existe para las pantallas que arman las columnas en un solo lugar y las
    reparten —el ABM genérico, el explorador de datos, la consola SQL—, donde
    reescribir cada llamador sería mucho ruido para el mismo resultado. Lo que
    ya viene en formato ag-grid pasa intacto, así una pantalla puede migrar sus
    columnas de a poco.
    """
    out = []
    for c in columns:
        if "field" in c:
            out.append(c)
            continue
        col = {k: v for k, v in c.items() if k not in ("name", "id")}
        col["field"] = c["id"]
        col["headerName"] = c.get("name", c["id"])
        out.append(col)
    return out
