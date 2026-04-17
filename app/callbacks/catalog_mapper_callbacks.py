import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, clientside_callback, html, no_update

import app.services.reference_service as ref_svc

_TAB_TO_TYPE = {
    "tab-country":          "country",
    "tab-market":           "market",
    "tab-instrument_type":  "instrument_type",
    "tab-sector":           "sector",
    "tab-industry":         "industry",
}

# JavaScript: define la función de DnD una vez en window y la llama tras cada render
_DND_SETUP_JS = """
function(lc, rc) {
    if (!window._setupMapperDnD) {
        window._setupMapperDnD = function() {
            document.querySelectorAll('.mapper-src').forEach(function(el) {
                el.setAttribute('draggable', 'true');
                el.ondragstart = function(e) {
                    window._mapperSrc = {
                        id: el.getAttribute('data-id'),
                        name: el.getAttribute('data-name')
                    };
                    e.dataTransfer.effectAllowed = 'move';
                    e.dataTransfer.setData('text/plain', el.getAttribute('data-id'));
                };
            });
            document.querySelectorAll('.mapper-tgt').forEach(function(el) {
                el.ondragover = function(e) {
                    e.preventDefault();
                    el.style.outline = '2px solid #0dcaf0';
                    el.style.background = 'rgba(13,202,240,0.08)';
                };
                el.ondragleave = function(e) {
                    el.style.outline = '';
                    el.style.background = '';
                };
                el.ondrop = function(e) {
                    e.preventDefault();
                    el.style.outline = '';
                    el.style.background = '';
                    if (!window._mapperSrc) return;
                    var srcId = parseInt(window._mapperSrc.id);
                    var tgtId = parseInt(el.getAttribute('data-id'));
                    if (srcId === tgtId) return;
                    window._pendingMerge = {
                        source_id: srcId,
                        source_name: window._mapperSrc.name,
                        target_id: tgtId,
                        target_name: el.getAttribute('data-name')
                    };
                    window._mapperSrc = null;
                    var btn = document.getElementById('mapper-drop-trigger');
                    if (btn) btn.click();
                };
            });
        };
    }
    setTimeout(window._setupMapperDnD, 80);
    return window.dash_clientside.no_update;
}
"""

# JavaScript: lee el drop pendiente y lo pasa al Store de Dash
_CAPTURE_DROP_JS = """
function(n) {
    if (window._pendingMerge) {
        var d = window._pendingMerge;
        window._pendingMerge = null;
        return d;
    }
    return window.dash_clientside.no_update;
}
"""


def _build_columns(entity_type: str):
    entities, aliases = ref_svc.get_catalog_entities_with_aliases(entity_type)
    alias_counts: dict[int, int] = {}
    for a in aliases:
        alias_counts[a.entity_id] = alias_counts.get(a.entity_id, 0) + 1

    src_items = []
    tgt_items = []
    for e in entities:
        src_items.append(html.Div(
            [html.I(className="fas fa-grip-vertical me-2 text-muted"), html.Span(e.name)],
            className="mapper-src p-2 mb-1 border rounded",
            style={"cursor": "grab", "userSelect": "none"},
            **{"data-id": str(e.id), "data-name": e.name},
        ))
        count = alias_counts.get(e.id, 0)
        badge = dbc.Badge(str(count), color="info", pill=True, className="ms-2") if count else ""
        tgt_items.append(html.Div(
            [html.Span(e.name), badge],
            className="mapper-tgt p-2 mb-1 border rounded d-flex justify-content-between align-items-center",
            style={"minHeight": "38px"},
            **{"data-id": str(e.id), "data-name": e.name},
        ))

    empty = [html.P("Sin entidades.", className="text-muted")]
    return src_items or empty, tgt_items or empty


# Configura DnD tras cada re-render de las columnas
clientside_callback(
    _DND_SETUP_JS,
    Output("mapper-dnd-dummy", "children"),
    Input("mapper-source-col", "children"),
    Input("mapper-target-col", "children"),
)

# Captura el drop y lo escribe en el Store
clientside_callback(
    _CAPTURE_DROP_JS,
    Output("mapper-pending-merge", "data"),
    Input("mapper-drop-trigger", "n_clicks"),
    prevent_initial_call=True,
)


@callback(
    Output("mapper-source-col", "children"),
    Output("mapper-target-col", "children"),
    Input("mapper-tabs", "active_tab"),
)
def load_entities(active_tab):
    entity_type = _TAB_TO_TYPE.get(active_tab, "country")
    return _build_columns(entity_type)


@callback(
    Output("mapper-confirm-modal", "is_open"),
    Output("mapper-confirm-body", "children"),
    Input("mapper-pending-merge", "data"),
    Input("mapper-btn-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_confirm_modal(pending, _cancel):
    from dash import ctx
    if ctx.triggered_id == "mapper-btn-cancel":
        return False, no_update
    if pending and pending.get("source_id") and pending.get("target_id"):
        body = (
            f"¿Fusionar '{pending['source_name']}' en '{pending['target_name']}'? "
            f"'{pending['source_name']}' será eliminado del catálogo y sus activos "
            f"pasarán a '{pending['target_name']}'."
        )
        return True, body
    return no_update, no_update


@callback(
    Output("mapper-source-col", "children", allow_duplicate=True),
    Output("mapper-target-col", "children", allow_duplicate=True),
    Output("mapper-confirm-modal", "is_open", allow_duplicate=True),
    Output("mapper-alert", "children"),
    Output("mapper-alert", "is_open"),
    Output("mapper-alert", "color"),
    Input("mapper-btn-confirm", "n_clicks"),
    State("mapper-pending-merge", "data"),
    State("mapper-tabs", "active_tab"),
    prevent_initial_call=True,
)
def execute_merge(_, pending, active_tab):
    _nu = no_update
    if not pending:
        return _nu, _nu, _nu, _nu, False, _nu
    entity_type = _TAB_TO_TYPE.get(active_tab, "country")
    try:
        source_name = ref_svc.merge_entities(
            entity_type, pending["source_id"], pending["target_id"]
        )
        src, tgt = _build_columns(entity_type)
        msg = f"'{source_name}' fusionado en '{pending['target_name']}'."
        return src, tgt, False, msg, True, "success"
    except Exception as exc:
        return _nu, _nu, False, str(exc), True, "danger"
