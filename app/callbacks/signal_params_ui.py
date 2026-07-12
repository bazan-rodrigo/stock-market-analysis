"""
Editor estructurado de parámetros de señales (reemplaza el textarea JSON
para el usuario inversor; el JSON queda como "modo avanzado").

Un editor por tipo de fórmula:
  discrete_map  filas categoría → score (pre-cargadas del catálogo de
                valores del indicador elegido, ver indicator_catalog)
  threshold     filas ordenadas "si valor > X → score" + "en otro caso"
  range         Min / Max / recortar a ±100
  composite     filas señal × peso

Estado en dcc.Store (sig-pb-store), una sección por tipo — se conservan
todas al cambiar de tipo, así no se pierde lo cargado si el usuario va y
vuelve:
  {"map":        {"uids": [...], "counter": N, "rows": {uid: {"cat", "score"}}},
   "thresholds": {"uids": [...], "counter": N, "rows": {uid: {"limit", "score"}},
                  "default": score|None},
   "range":      {"min": ..., "max": ..., "clamp": bool},
   "components": {"uids": [...], "counter": N, "rows": {uid: {"signal_key", "weight"}}}}

Mismo patrón que strategy_filter_ui: render declarativo desde el store,
captura de todos los estados antes de mutar, y no_update si nada cambió
(corta el ciclo render → captura → render).

Las funciones puras params_from_builder / builder_from_params hacen la
conversión con el JSON que consume signal_engine — testeables sin Dash.
"""
import json

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_bootstrap_components as dbc

_FS = {"fontSize": "0.80rem"}

_EMPTY_STORE = {
    "map":        {"uids": [], "counter": 0, "rows": {}},
    "thresholds": {"uids": [], "counter": 0, "rows": {}, "default": None},
    "range":      {"min": None, "max": None, "clamp": True},
    "components": {"uids": [], "counter": 0, "rows": {}},
}


def empty_params_store() -> dict:
    return json.loads(json.dumps(_EMPTY_STORE))


# ── Conversión builder → params JSON (guardar) ───────────────────────────────

def params_from_builder(ftype: str, store: dict) -> tuple[str | None, str | None]:
    """(params_json, error). El store ya debe tener los valores capturados."""
    store = store or empty_params_store()

    if ftype == "discrete_map":
        sec = store.get("map", {})
        rows = [sec["rows"][str(u)] for u in sec.get("uids", [])
                if str(u) in sec.get("rows", {})]
        mapping = {}
        for r in rows:
            cat, score = r.get("cat"), r.get("score")
            if not cat or score is None:
                continue  # categoría sin score asignado: no mapea (válido)
            if cat in mapping:
                return None, f"La categoría '{cat}' está repetida."
            mapping[cat] = score
        if not mapping:
            return None, "Asigná un score a al menos una categoría."
        return json.dumps({"map": mapping}), None

    if ftype == "threshold":
        sec = store.get("thresholds", {})
        rows = [sec["rows"][str(u)] for u in sec.get("uids", [])
                if str(u) in sec.get("rows", {})]
        pairs = [(r.get("limit"), r.get("score")) for r in rows]
        if any((l is None) != (s is None) for l, s in pairs):
            return None, "Cada umbral necesita límite y score (o borrá la fila)."
        pairs = [(l, s) for l, s in pairs if l is not None]
        if not pairs:
            return None, "Agregá al menos un umbral."
        if len({l for l, _ in pairs}) != len(pairs):
            return None, "Hay límites de umbral repetidos."
        pairs.sort(key=lambda p: p[0], reverse=True)  # el motor evalúa en orden
        thresholds = [[l, s] for l, s in pairs]
        if sec.get("default") is not None:
            thresholds.append([None, sec["default"]])
        return json.dumps({"thresholds": thresholds}), None

    if ftype == "range":
        sec = store.get("range", {})
        vmin, vmax = sec.get("min"), sec.get("max")
        if vmin is None or vmax is None:
            return None, "Completá Min y Max."
        if vmin == vmax:
            return None, "Min y Max no pueden ser iguales."
        return json.dumps({"min": vmin, "max": vmax,
                           "clamp": bool(sec.get("clamp", True))}), None

    if ftype == "composite":
        sec = store.get("components", {})
        rows = [sec["rows"][str(u)] for u in sec.get("uids", [])
                if str(u) in sec.get("rows", {})]
        comps, seen = [], set()
        for r in rows:
            key = r.get("signal_key")
            if not key:
                return None, "Hay un componente sin señal elegida."
            if key in seen:
                return None, f"La señal '{key}' está repetida."
            seen.add(key)
            comps.append({"signal_key": key,
                          "weight": r.get("weight") if r.get("weight") is not None else 1.0})
        if not comps:
            return None, "Agregá al menos una señal componente."
        return json.dumps({"components": comps}), None

    return None, f"Tipo de fórmula desconocido: {ftype!r}"


# ── Conversión params JSON → builder (editar) ────────────────────────────────

def builder_from_params(ftype: str, params_json: str | None) -> dict | None:
    """Store del builder desde un params guardado, o None si el JSON no es
    representable en el editor (→ modo avanzado)."""
    store = empty_params_store()
    if not params_json or not params_json.strip():
        return store
    try:
        params = json.loads(params_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(params, dict):
        return None
    if not params:
        return store

    try:
        if ftype == "discrete_map":
            mapping = params.get("map", {})
            if not isinstance(mapping, dict):
                return None
            sec = store["map"]
            for i, (cat, score) in enumerate(mapping.items()):
                sec["rows"][str(i)] = {"cat": str(cat), "score": float(score)}
                sec["uids"].append(i)
            sec["counter"] = len(mapping)
            return store

        if ftype == "threshold":
            thresholds = params.get("thresholds", [])
            sec = store["thresholds"]
            i = 0
            for limit, score in thresholds:
                if limit is None:
                    sec["default"] = float(score)
                    continue
                sec["rows"][str(i)] = {"limit": float(limit), "score": float(score)}
                sec["uids"].append(i)
                i += 1
            sec["counter"] = i
            return store

        if ftype == "range":
            store["range"] = {"min": float(params["min"]), "max": float(params["max"]),
                              "clamp": bool(params.get("clamp", True))}
            return store

        if ftype == "composite":
            comps = params.get("components", [])
            sec = store["components"]
            for i, c in enumerate(comps):
                sec["rows"][str(i)] = {
                    "signal_key": c.get("signal_key"),
                    "weight": float(c.get("weight", 1.0)),
                }
                sec["uids"].append(i)
            sec["counter"] = len(comps)
            return store
    except (KeyError, TypeError, ValueError):
        return None

    return None


# ── Opciones ──────────────────────────────────────────────────────────────────

def build_pb_opts() -> dict:
    from app.database import get_session
    from app.models import SignalDefinition
    from app.services.indicator_catalog import CATEGORICAL_VALUES

    s = get_session()
    signals = s.query(SignalDefinition.key, SignalDefinition.name).order_by(
        SignalDefinition.key).all()
    return {
        "signal_opts": [{"label": f"{k} — {n}", "value": k} for k, n in signals],
        "cat_values": {code: sorted(vals) for code, vals in CATEGORICAL_VALUES.items()},
    }


# ── Render ────────────────────────────────────────────────────────────────────

def _del_btn(type_, uid):
    return dbc.Button("×", id={"type": type_, "index": uid},
                      color="link", size="sm",
                      style={"color": "#ef5350", "padding": "0 6px",
                             "lineHeight": 1, "fontSize": "1rem"})


def _render_map(store, indicator_key, opts):
    sec = store.get("map", {})
    catalog = (opts or {}).get("cat_values", {}).get(indicator_key)
    rows = []
    for uid in sec.get("uids", []):
        r = sec.get("rows", {}).get(str(uid), {})
        if catalog:
            cat_ctl = dcc.Dropdown(
                id={"type": "sigpb-map-cat", "index": uid},
                options=[{"label": v, "value": v} for v in catalog],
                value=r.get("cat"), placeholder="categoría...", style=_FS)
        else:
            cat_ctl = dbc.Input(
                id={"type": "sigpb-map-cat", "index": uid},
                value=r.get("cat"), placeholder="categoría", style=_FS)
        rows.append(dbc.Row([
            dbc.Col(cat_ctl, md=6),
            dbc.Col(dbc.Input(id={"type": "sigpb-map-score", "index": uid},
                              type="number", value=r.get("score"), min=-100, max=100,
                              placeholder="score (−100 a 100)", style=_FS), md=4),
            dbc.Col(_del_btn("sigpb-map-del", uid), style={"width": "32px"}),
        ], className="g-1 mb-1 align-items-center"))

    hint = None
    if catalog is None and indicator_key:
        hint = html.Small(
            "Este indicador no tiene catálogo de categorías — escribí el valor "
            "exacto que produce el indicador.",
            className="text-muted d-block mb-1")
    elif not indicator_key:
        hint = html.Small("Elegí primero la clave de indicador para pre-cargar "
                          "sus categorías.", className="text-muted d-block mb-1")
    return html.Div([
        hint,
        dbc.Row([
            dbc.Col(html.Small("Categoría", className="text-muted"), md=6),
            dbc.Col(html.Small("Score", className="text-muted"), md=4),
            dbc.Col(style={"width": "32px"}),
        ], className="g-1"),
        html.Div(rows),
        dbc.Button("+ categoría", id={"type": "sigpb-map-add", "index": 0},
                   color="link", size="sm",
                   style={"fontSize": "0.78rem", "paddingLeft": 0}),
    ])


def _render_thresholds(store):
    sec = store.get("thresholds", {})
    rows = []
    for uid in sec.get("uids", []):
        r = sec.get("rows", {}).get(str(uid), {})
        rows.append(dbc.Row([
            dbc.Col(html.Small("si valor >", className="text-muted",
                               style={"whiteSpace": "nowrap"}),
                    width="auto", className="d-flex align-items-center"),
            dbc.Col(dbc.Input(id={"type": "sigpb-th-limit", "index": uid},
                              type="number", value=r.get("limit"),
                              placeholder="límite", style=_FS), md=3),
            dbc.Col(html.Small("→ score", className="text-muted"),
                    width="auto", className="d-flex align-items-center"),
            dbc.Col(dbc.Input(id={"type": "sigpb-th-score", "index": uid},
                              type="number", value=r.get("score"), min=-100, max=100,
                              placeholder="score", style=_FS), md=3),
            dbc.Col(_del_btn("sigpb-th-del", uid), style={"width": "32px"}),
        ], className="g-1 mb-1 align-items-center"))

    return html.Div([
        html.Small("Se evalúa de arriba hacia abajo (los límites se ordenan "
                   "solos de mayor a menor al guardar).",
                   className="text-muted d-block mb-1"),
        html.Div(rows),
        dbc.Row([
            dbc.Col(html.Small("en otro caso → score", className="text-muted",
                               style={"whiteSpace": "nowrap"}),
                    width="auto", className="d-flex align-items-center"),
            dbc.Col(dbc.Input(id={"type": "sigpb-th-default", "index": 0},
                              type="number", value=sec.get("default"),
                              min=-100, max=100,
                              placeholder="(opcional: sin score)", style=_FS), md=3),
        ], className="g-1 mb-1 align-items-center"),
        dbc.Button("+ umbral", id={"type": "sigpb-th-add", "index": 0},
                   color="link", size="sm",
                   style={"fontSize": "0.78rem", "paddingLeft": 0}),
    ])


def _render_range(store):
    sec = store.get("range", {})
    vmin, vmax = sec.get("min"), sec.get("max")
    legend = None
    if vmin is not None and vmax is not None and vmin != vmax:
        legend = html.Small(
            f"Un valor de {vmin:g} da score −100; {(vmin + vmax) / 2:g} da 0; "
            f"{vmax:g} da +100.",
            className="text-muted d-block mt-1")
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Label("Min (score −100)", style={"fontSize": "0.78rem"}),
                dbc.Input(id={"type": "sigpb-range-min", "index": 0},
                          type="number", value=vmin, style=_FS),
            ], md=3),
            dbc.Col([
                dbc.Label("Max (score +100)", style={"fontSize": "0.78rem"}),
                dbc.Input(id={"type": "sigpb-range-max", "index": 0},
                          type="number", value=vmax, style=_FS),
            ], md=3),
            dbc.Col(
                dbc.Checkbox(id={"type": "sigpb-range-clamp", "index": 0},
                             label="Recortar a ±100 los valores fuera del rango",
                             value=bool(sec.get("clamp", True)),
                             style={"fontSize": "0.78rem"}),
                md=6, className="d-flex align-items-end pb-1",
            ),
        ], className="g-2"),
        legend,
    ])


def _render_components(store, opts):
    sec = store.get("components", {})
    signal_opts = (opts or {}).get("signal_opts", [])
    rows = []
    for uid in sec.get("uids", []):
        r = sec.get("rows", {}).get(str(uid), {})
        rows.append(dbc.Row([
            dbc.Col(dcc.Dropdown(id={"type": "sigpb-comp-signal", "index": uid},
                                 options=signal_opts, value=r.get("signal_key"),
                                 placeholder="Señal...", style=_FS), md=7),
            dbc.Col(dbc.Input(id={"type": "sigpb-comp-weight", "index": uid},
                              type="number", value=r.get("weight", 1.0),
                              min=0, step=0.01, placeholder="peso", style=_FS), md=3),
            dbc.Col(_del_btn("sigpb-comp-del", uid), style={"width": "32px"}),
        ], className="g-1 mb-1 align-items-center"))

    return html.Div([
        dbc.Row([
            dbc.Col(html.Small("Señal", className="text-muted"), md=7),
            dbc.Col(html.Small("Peso", className="text-muted"), md=3),
            dbc.Col(style={"width": "32px"}),
        ], className="g-1"),
        html.Div(rows),
        dbc.Button("+ señal componente", id={"type": "sigpb-comp-add", "index": 0},
                   color="link", size="sm",
                   style={"fontSize": "0.78rem", "paddingLeft": 0}),
    ])


@callback(
    Output("sig-params-builder",  "children"),
    Output("sig-params-json-wrap", "style"),
    Input("sig-pb-store",          "data"),
    Input("sig-pb-opts",           "data"),
    Input("sig-f-formula-type",    "value"),
    Input("sig-f-indicator-key",   "value"),
    Input("sig-params-advanced",   "value"),
)
def render_builder(store, opts, ftype, indicator_key, advanced):
    if advanced:
        return html.Div(), {}
    if not ftype:
        return html.Small("Elegí el tipo de fórmula para configurarla.",
                          className="text-muted"), {"display": "none"}
    store = store or empty_params_store()
    if ftype == "discrete_map":
        body = _render_map(store, indicator_key, opts)
    elif ftype == "threshold":
        body = _render_thresholds(store)
    elif ftype == "range":
        body = _render_range(store)
    elif ftype == "composite":
        body = _render_components(store, opts)
    else:
        return html.Div(), {}
    return body, {"display": "none"}


# ── Captura de estados + cambios estructurales ────────────────────────────────

def capture_pb_fields(store, ids_vals: list[tuple[list, list, str, str]]) -> dict:
    """ids_vals: [(ids, values, sección, campo)] — vuelca los controles al
    store. Se usa acá y en el save de admin_signals_callbacks."""
    store = store or empty_params_store()
    for ids, values, section, field in ids_vals:
        sec = store.setdefault(section, {})
        for id_, v in zip(ids or [], values or []):
            uid = str(id_["index"])
            if section == "range":
                sec[field] = v
            elif section == "thresholds" and field == "default":
                sec["default"] = v
            else:
                sec.setdefault("rows", {}).setdefault(uid, {})[field] = v
    return store


def _pb_ids_vals(map_cats, ids_map_cat, map_scores, ids_map_score,
                 th_limits, ids_th_limit, th_scores, ids_th_score,
                 th_defaults, ids_th_default,
                 range_mins, ids_range_min, range_maxs, ids_range_max,
                 range_clamps, ids_range_clamp,
                 comp_signals, ids_comp_signal, comp_weights, ids_comp_weight):
    return [
        (ids_map_cat,     map_cats,    "map",        "cat"),
        (ids_map_score,   map_scores,  "map",        "score"),
        (ids_th_limit,    th_limits,   "thresholds", "limit"),
        (ids_th_score,    th_scores,   "thresholds", "score"),
        (ids_th_default,  th_defaults, "thresholds", "default"),
        (ids_range_min,   range_mins,  "range",      "min"),
        (ids_range_max,   range_maxs,  "range",      "max"),
        (ids_range_clamp, range_clamps, "range",     "clamp"),
        (ids_comp_signal, comp_signals, "components", "signal_key"),
        (ids_comp_weight, comp_weights, "components", "weight"),
    ]


# Los States de todos los controles del builder, en el orden de _pb_ids_vals —
# compartidos entre update_pb_store y el save de admin_signals_callbacks.
PB_FIELD_STATES = [
    State({"type": "sigpb-map-cat",     "index": ALL}, "value"),
    State({"type": "sigpb-map-cat",     "index": ALL}, "id"),
    State({"type": "sigpb-map-score",   "index": ALL}, "value"),
    State({"type": "sigpb-map-score",   "index": ALL}, "id"),
    State({"type": "sigpb-th-limit",    "index": ALL}, "value"),
    State({"type": "sigpb-th-limit",    "index": ALL}, "id"),
    State({"type": "sigpb-th-score",    "index": ALL}, "value"),
    State({"type": "sigpb-th-score",    "index": ALL}, "id"),
    State({"type": "sigpb-th-default",  "index": ALL}, "value"),
    State({"type": "sigpb-th-default",  "index": ALL}, "id"),
    State({"type": "sigpb-range-min",   "index": ALL}, "value"),
    State({"type": "sigpb-range-min",   "index": ALL}, "id"),
    State({"type": "sigpb-range-max",   "index": ALL}, "value"),
    State({"type": "sigpb-range-max",   "index": ALL}, "id"),
    State({"type": "sigpb-range-clamp", "index": ALL}, "value"),
    State({"type": "sigpb-range-clamp", "index": ALL}, "id"),
    State({"type": "sigpb-comp-signal", "index": ALL}, "value"),
    State({"type": "sigpb-comp-signal", "index": ALL}, "id"),
    State({"type": "sigpb-comp-weight", "index": ALL}, "value"),
    State({"type": "sigpb-comp-weight", "index": ALL}, "id"),
]


def pb_capture_from_args(store, args: tuple) -> dict:
    """args: los 20 valores posicionales que producen PB_FIELD_STATES
    (value, id alternados). Devuelve el store con todo capturado."""
    (map_cats, ids_map_cat, map_scores, ids_map_score,
     th_limits, ids_th_limit, th_scores, ids_th_score,
     th_defaults, ids_th_default,
     range_mins, ids_range_min, range_maxs, ids_range_max,
     range_clamps, ids_range_clamp,
     comp_signals, ids_comp_signal, comp_weights, ids_comp_weight) = args
    return capture_pb_fields(store, _pb_ids_vals(
        map_cats, ids_map_cat, map_scores, ids_map_score,
        th_limits, ids_th_limit, th_scores, ids_th_score,
        th_defaults, ids_th_default,
        range_mins, ids_range_min, range_maxs, ids_range_max,
        range_clamps, ids_range_clamp,
        comp_signals, ids_comp_signal, comp_weights, ids_comp_weight))


def _add_row(sec: dict, fields: dict) -> None:
    uid = sec.get("counter", 0)
    sec["counter"] = uid + 1
    sec.setdefault("rows", {})[str(uid)] = fields
    sec.setdefault("uids", []).append(uid)


def _del_row(sec: dict, uid) -> None:
    sec["uids"] = [u for u in sec.get("uids", []) if u != uid]
    sec.get("rows", {}).pop(str(uid), None)


@callback(
    Output("sig-pb-store", "data", allow_duplicate=True),
    Input({"type": "sigpb-map-add",  "index": ALL}, "n_clicks"),
    Input({"type": "sigpb-map-del",  "index": ALL}, "n_clicks"),
    Input({"type": "sigpb-th-add",   "index": ALL}, "n_clicks"),
    Input({"type": "sigpb-th-del",   "index": ALL}, "n_clicks"),
    Input({"type": "sigpb-comp-add", "index": ALL}, "n_clicks"),
    Input({"type": "sigpb-comp-del", "index": ALL}, "n_clicks"),
    Input("sig-f-formula-type",  "value"),
    Input("sig-f-indicator-key", "value"),
    *PB_FIELD_STATES,
    State("sig-pb-store", "data"),
    State("sig-pb-opts",  "data"),
    prevent_initial_call=True,
)
def update_pb_store(map_add, map_del, th_add, th_del, comp_add, comp_del,
                    ftype, indicator_key, *rest):
    field_args, (store, opts) = rest[:-2], rest[-2:]
    store = store or empty_params_store()
    before = json.dumps(store, sort_keys=True)
    trigger = ctx.triggered_id

    # Capturar SOLO cuando el trigger es un botón de fila (mismo render que
    # el store). Si el trigger es el cambio de tipo/indicador, los controles
    # en pantalla pueden ser de la señal ANTERIOR (al abrir el modal el
    # store nuevo llega antes que el re-render) — capturarlos pisaría el
    # store recién cargado con valores ajenos.
    if isinstance(trigger, dict):
        store = pb_capture_from_args(store, field_args)

    def _clicked(ns):
        return any(n for n in (ns or []) if n)

    if isinstance(trigger, dict):
        t = trigger.get("type")
        if t == "sigpb-map-add" and _clicked(map_add):
            _add_row(store["map"], {"cat": None, "score": None})
        elif t == "sigpb-map-del" and _clicked(map_del):
            _del_row(store["map"], trigger["index"])
        elif t == "sigpb-th-add" and _clicked(th_add):
            _add_row(store["thresholds"], {"limit": None, "score": None})
        elif t == "sigpb-th-del" and _clicked(th_del):
            _del_row(store["thresholds"], trigger["index"])
        elif t == "sigpb-comp-add" and _clicked(comp_add):
            _add_row(store["components"], {"signal_key": None, "weight": 1.0})
        elif t == "sigpb-comp-del" and _clicked(comp_del):
            _del_row(store["components"], trigger["index"])

    # discrete_map + indicador con catálogo + sin filas → pre-cargar todas
    # las categorías (el usuario solo completa scores)
    if ftype == "discrete_map" and indicator_key and not store["map"]["uids"]:
        catalog = (opts or {}).get("cat_values", {}).get(indicator_key)
        if catalog:
            for cat in catalog:
                _add_row(store["map"], {"cat": cat, "score": None})

    if json.dumps(store, sort_keys=True) == before:
        return no_update
    return store


@callback(
    Output("sig-pb-opts", "data"),
    Input("sig-modal", "is_open"),
)
def cache_pb_opts(is_open):
    if not is_open:
        return no_update
    return build_pb_opts()


# ── Modo avanzado: sincronizar builder → textarea al activarlo ───────────────

@callback(
    Output("sig-f-params",  "value", allow_duplicate=True),
    Output("sig-pb-store",  "data",  allow_duplicate=True),
    Output("sig-modal-error", "children", allow_duplicate=True),
    Output("sig-modal-error", "is_open",  allow_duplicate=True),
    Input("sig-params-advanced", "value"),
    State("sig-f-formula-type",  "value"),
    State("sig-f-params",        "value"),
    *PB_FIELD_STATES,
    State("sig-pb-store", "data"),
    prevent_initial_call=True,
)
def toggle_advanced(advanced, ftype, params_text, *rest):
    field_args, (store,) = rest[:-1], rest[-1:]

    if advanced:
        # Volcar lo armado en el builder al textarea (si es serializable);
        # si el builder está vacío/incompleto, dejar el textarea como está
        # (puede tener el JSON original que el builder no supo representar)
        store = pb_capture_from_args(store or empty_params_store(), field_args)
        params_json, error = params_from_builder(ftype, store) if ftype else (None, "x")
        if error:
            return no_update, store, no_update, no_update
        return params_json, store, no_update, no_update

    # Volver al builder: intentar reflejar lo editado a mano en el textarea
    parsed = builder_from_params(ftype, params_text) if ftype else None
    if parsed is None:
        return (no_update, no_update,
                "El JSON no es representable en el editor — se muestran los "
                "últimos valores válidos del editor.", True)
    return no_update, parsed, "", False
