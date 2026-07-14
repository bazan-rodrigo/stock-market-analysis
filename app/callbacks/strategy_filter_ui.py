"""
Constructor visual del filtro de elegibilidad de estrategias.

Estado en dcc.Store (str-filter-store) como árbol aplanado:
  {"nodes": {"0": {"kind": "group", "op": "AND", "children": [1, 2]},
             "1": {"kind": "cond", "left": "ind:rsi_daily", "op": ">",
                   "val": 70, "vs": None}},
   "root": 0, "counter": 3}

Operandos codificados como "ind:<code>" | "sig:<key>" | "attr:<key>" para
viajar en un solo dropdown. El render es declarativo desde el store; los
cambios de campo (left/op/vs) son Inputs del callback estructural — que
captura TODOS los estados antes de mutar, así nada se pierde al re-render.
Los valores (número / dropdown de valor) NO disparan re-render: se capturan
al guardar o ante el próximo cambio estructural (mismo patrón que
update_comp_store en admin_strategies_callbacks).

La conversión store ↔ JSON del árbol (formato de strategy_filter.py) vive
acá: _store_to_tree se usa al guardar, _tree_to_store al editar.
"""
import json

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_bootstrap_components as dbc

_NUM_OPS = [{"label": o, "value": o} for o in ("=", "!=", ">", ">=", "<", "<=")]
_CAT_OPS = [{"label": "=", "value": "="}, {"label": "!=", "value": "!="},
            {"label": "in", "value": "in"}, {"label": "not in", "value": "not_in"}]

_ATTR_LABELS = {
    "sector": "Sector", "market": "Mercado", "industry": "Industria",
    "country": "País", "instrument_type": "Tipo de instrumento",
}

_EMPTY_STORE = {"nodes": {"0": {"kind": "group", "op": "AND", "children": []}},
                "root": 0, "counter": 1}

_FS = {"fontSize": "0.80rem"}


def empty_filter_store() -> dict:
    return json.loads(json.dumps(_EMPTY_STORE))  # copia profunda


# ── Opciones (catálogos) ──────────────────────────────────────────────────────

def build_filter_opts() -> dict:
    """Catálogos para los dropdowns del constructor. Se cachean en
    str-filter-opts al abrir el modal."""
    from app.database import get_session
    from app.models import (Country, Industry, InstrumentType, Market,
                            Sector, SignalDefinition)
    from app.models.indicator_definition import IndicatorDefinition
    from app.services import strategy_filter as sf
    from app.services.indicator_catalog import CATEGORICAL_VALUES

    from app.services.visibility import current_viewer, visible_filter

    s = get_session()

    indicators = s.query(
        IndicatorDefinition.code, IndicatorDefinition.name,
        IndicatorDefinition.type,
    ).order_by(IndicatorDefinition.name).all()
    signals = (s.query(SignalDefinition.key, SignalDefinition.name)
               .filter(visible_filter(SignalDefinition, *current_viewer()))
               .order_by(SignalDefinition.key).all())

    operands = (
        [{"label": f"[Atributo] {_ATTR_LABELS[k]}", "value": f"attr:{k}"}
         for k in ("instrument_type", "sector", "industry", "market", "country")]
        + [{"label": f"[Ind] {name} ({code})", "value": f"ind:{code}"}
           for code, name, _ in indicators]
        + [{"label": f"[Señal] {key} — {name}", "value": f"sig:{key}"}
           for key, name in signals]
    )
    numeric = ({f"ind:{code}" for code, _, t in indicators if t == "num"}
               | {f"sig:{key}" for key, _ in signals})

    cat_values: dict[str, list] = {
        f"ind:{code}": [{"label": v, "value": v} for v in sorted(vals)]
        for code, vals in CATEGORICAL_VALUES.items()
    }
    for key, model in (("sector", Sector), ("market", Market),
                       ("industry", Industry), ("country", Country),
                       ("instrument_type", InstrumentType)):
        cat_values[f"attr:{key}"] = [
            {"label": r.name, "value": r.id}
            for r in s.query(model.id, model.name).order_by(model.name).all()
        ]

    no_hist = ({f"ind:{c}" for c in sf.non_history_indicator_codes(s)}
               | {f"sig:{k}" for k in sf.non_history_signal_keys(s)})

    return {"operands": operands, "numeric": sorted(numeric),
            "cat_values": cat_values, "no_hist": sorted(no_hist)}


# ── store → árbol JSON (guardar) ─────────────────────────────────────────────

def _decode_operand(encoded: str) -> dict | None:
    if not encoded or ":" not in encoded:
        return None
    kind, key = encoded.split(":", 1)
    t = {"ind": "indicator", "sig": "signal", "attr": "attribute"}.get(kind)
    return {"type": t, "key": key} if t else None


def store_to_tree(store: dict, no_hist: set[str]) -> tuple[str | None, list[str]]:
    """(filter_conditions JSON | None, errores). Grupos vacíos se omiten;
    árbol sin ninguna condición = None (sin filtro)."""
    errors: list[str] = []
    nodes = (store or {}).get("nodes", {})
    if not nodes:
        return None, []

    def _ser(uid):
        node = nodes.get(str(uid))
        if node is None:
            return None
        if node["kind"] == "group":
            children = [c for c in (_ser(cid) for cid in node.get("children", []))
                        if c is not None]
            if not children:
                return None
            return {"op": node.get("op", "AND"), "children": children}

        left_enc = node.get("left")
        operator = node.get("op")
        if not left_enc or not operator:
            errors.append("Hay una condición del filtro sin completar.")
            return None
        left = _decode_operand(left_enc)

        vs, val = node.get("vs"), node.get("val")
        if vs:
            right = _decode_operand(vs)
        elif val is None or (isinstance(val, list) and not val):
            errors.append("Hay una condición del filtro sin valor.")
            return None
        else:
            if operator in ("in", "not_in") and not isinstance(val, list):
                val = [val]
            right = {"type": "const", "value": val}

        cond = {"left": left, "operator": operator, "right": right}
        if left_enc in no_hist or (vs and vs in no_hist):
            # Operando sin historia: a fecha pasada solo existe el valor
            # vigente — sesgo de anticipación deliberado (ver strategy_filter)
            cond["resolution"] = "current"
        return {"cond": cond}

    tree = _ser((store or {}).get("root", 0))
    if errors:
        return None, errors
    return (json.dumps(tree) if tree else None), []


# ── store → texto legible (previsualización de la fórmula) ───────────────────

_OP_TEXT = {"not_in": "not in"}


def _operand_text(encoded: str | None) -> str:
    """Etiqueta corta del operando para la fórmula. ind/señal → code/key crudo;
    atributo → nombre en español."""
    if not encoded or ":" not in encoded:
        return "‹?›"
    kind, key = encoded.split(":", 1)
    if kind == "attr":
        return _ATTR_LABELS.get(key, key)
    return key


def _value_text(left_enc: str | None, val, opts: dict) -> str:
    """Valor del lado derecho, traduciendo ids categóricos a su nombre."""
    cat = {str(o["value"]): o["label"]
           for o in (opts.get("cat_values", {}) or {}).get(left_enc, [])}

    def _one(v):
        return cat.get(str(v), str(v))

    if isinstance(val, list):
        return "[" + ", ".join(_one(v) for v in val) + "]"
    return _one(val)


def _cond_text(node: dict, opts: dict) -> str:
    left_enc, op = node.get("left"), node.get("op")
    if not left_enc or not op:
        return "‹condición incompleta›"
    left = _operand_text(left_enc)
    op_txt = _OP_TEXT.get(op, op)
    vs = node.get("vs")
    if vs:
        return f"{left} {op_txt} {_operand_text(vs)}"
    val = node.get("val")
    if val is None or (isinstance(val, list) and not val):
        return f"{left} {op_txt} ‹sin valor›"
    return f"{left} {op_txt} {_value_text(left_enc, val, opts)}"


def _node_lines(uid, nodes: dict, opts: dict, wrap: bool) -> list[str]:
    node = nodes.get(str(uid))
    if node is None:
        return []
    if node["kind"] == "cond":
        return [_cond_text(node, opts)]

    conj = "Y " if node.get("op", "AND") == "AND" else "O "
    blocks = []
    for cid in node.get("children", []):
        child = nodes.get(str(cid))
        cwrap = child is not None and child.get("kind") == "group"
        block = _node_lines(cid, nodes, opts, cwrap)
        if block:
            blocks.append(block)
    if not blocks:
        return []

    lines: list[str] = []
    for i, block in enumerate(blocks):
        if i == 0:
            lines.extend(block)
        else:
            lines.append(conj + block[0])
            lines.extend("  " + ln for ln in block[1:])

    if wrap:
        if len(lines) == 1:
            lines = ["(" + lines[0] + ")"]
        else:
            lines = (["(" + lines[0]]
                     + ["   " + ln for ln in lines[1:-1]]
                     + ["   " + lines[-1] + ")"])
    return lines


def store_to_text(store: dict | None, opts: dict | None) -> str:
    """Serializa el árbol del filtro (tal como está en el store, con los
    valores vivos ya volcados por _capture_fields) a un texto legible para
    revalidar la lógica. No valida ni omite grupos vacíos como store_to_tree:
    refleja lo que el usuario ve."""
    opts = opts or {}
    nodes = (store or {}).get("nodes", {})
    if not nodes:
        return "(sin filtro: todos los activos)"
    lines = _node_lines((store or {}).get("root", 0), nodes, opts, wrap=False)
    if not lines:
        return "(sin filtro: todos los activos)"
    return "\n".join(lines)


# ── árbol JSON → store (editar) ──────────────────────────────────────────────

def _encode_operand(side: dict) -> str | None:
    prefix = {"indicator": "ind", "signal": "sig", "attribute": "attr"}.get(
        side.get("type"))
    return f"{prefix}:{side.get('key')}" if prefix else None


def tree_to_store(filter_conditions: str | None) -> dict:
    if not filter_conditions:
        return empty_filter_store()
    try:
        tree = json.loads(filter_conditions)
    except (json.JSONDecodeError, TypeError):
        return empty_filter_store()
    if not tree:
        return empty_filter_store()

    nodes: dict[str, dict] = {}
    counter = 0

    def _add(node) -> int:
        nonlocal counter
        uid = counter
        counter += 1
        if "cond" in node:
            cond = node["cond"]
            right = cond.get("right", {})
            is_const = right.get("type") == "const"
            nodes[str(uid)] = {
                "kind": "cond",
                "left": _encode_operand(cond.get("left", {})),
                "op":   cond.get("operator"),
                "val":  right.get("value") if is_const else None,
                "vs":   None if is_const else _encode_operand(right),
            }
        else:
            nodes[str(uid)] = {"kind": "group", "op": node.get("op", "AND"),
                               "children": []}
            nodes[str(uid)]["children"] = [
                _add(c) for c in node.get("children", [])
            ]
        return uid

    # El árbol guardado puede tener una condición suelta como raíz
    # (validate_tree lo permite); el store siempre usa un grupo raíz.
    if "cond" in tree:
        root = counter
        nodes[str(root)] = {"kind": "group", "op": "AND", "children": []}
        counter += 1
        nodes[str(root)]["children"] = [_add(tree)]
    else:
        root = _add(tree)
    return {"nodes": nodes, "root": root, "counter": counter}


# ── Render ────────────────────────────────────────────────────────────────────

def _warn_no_hist(encoded: str | None, vs: str | None, no_hist: set[str]):
    bad = [e for e in (encoded, vs) if e and e in no_hist]
    if not bad:
        return None
    return html.Small(
        "⚠ sin historia — en fechas pasadas usará el valor vigente "
        "(sesgo de anticipación, diagnóstico in-sample)",
        className="d-block", style={"color": "#ffb74d", "fontSize": "0.72rem"},
    )


def _value_cell(uid, node, opts):
    """Controles del lado derecho. Siempre crea strf-val y strf-vs (vs oculto
    cuando no aplica) para que las colecciones ALL queden alineadas."""
    left, op, val, vs = (node.get("left"), node.get("op"),
                         node.get("val"), node.get("vs"))
    numeric = set(opts.get("numeric", []))
    cat_values = opts.get("cat_values", {})

    is_numeric = left in numeric
    multi = op in ("in", "not_in")
    vs_style = dict(_FS)
    if not is_numeric:
        vs_style["display"] = "none"

    if is_numeric or not left:
        val_ctl = dbc.Input(
            id={"type": "strf-val", "index": uid},
            type="number",
            value=val if isinstance(val, (int, float)) else None,
            placeholder="valor", disabled=not left, style=_FS,
        )
    else:
        options = cat_values.get(left, [])
        allowed = {str(o["value"]) for o in options}
        if multi:
            vals = val if isinstance(val, list) else ([val] if val is not None else [])
            value = [v for v in vals if str(v) in allowed]
        else:
            value = val if (val is not None and str(val) in allowed
                            and not isinstance(val, list)) else None
        val_ctl = dcc.Dropdown(
            id={"type": "strf-val", "index": uid},
            options=options, value=value, multi=multi,
            placeholder="valor...", style=_FS,
        )

    vs_ctl = dcc.Dropdown(
        id={"type": "strf-vs", "index": uid},
        options=[o for o in opts.get("operands", []) if o["value"] in numeric],
        value=vs if is_numeric else None,
        placeholder="…o vs indicador/señal", style=vs_style,
    )
    return val_ctl, vs_ctl


def _render_cond(uid, node, opts):
    left = node.get("left")
    numeric = set(opts.get("numeric", []))
    op_opts = _NUM_OPS if (left in numeric or not left) else _CAT_OPS
    val_ctl, vs_ctl = _value_cell(uid, node, opts)
    warn = _warn_no_hist(left, node.get("vs"), set(opts.get("no_hist", [])))

    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Dropdown(
                id={"type": "strf-left", "index": uid},
                options=opts.get("operands", []), value=left,
                placeholder="Indicador / señal / atributo...", style=_FS,
            ), md=4),
            dbc.Col(dcc.Dropdown(
                id={"type": "strf-op", "index": uid},
                options=op_opts, value=node.get("op"),
                placeholder="op", clearable=False, style=_FS,
            ), md=2),
            dbc.Col(val_ctl, md=3),
            dbc.Col(vs_ctl,  md=2),
            dbc.Col(
                dbc.Button("×", id={"type": "strf-remove", "index": uid},
                           color="link", size="sm",
                           style={"color": "#ef5350", "padding": "0 6px",
                                  "lineHeight": 1, "fontSize": "1rem"}),
                style={"width": "32px"},
            ),
        ], className="g-1 align-items-center"),
        warn,
    ], className="mb-1")


def _render_group(uid, nodes, opts, is_root):
    node = nodes[str(uid)]
    children = [
        _render_group(cid, nodes, opts, False)
        if nodes[str(cid)]["kind"] == "group"
        else _render_cond(cid, nodes[str(cid)], opts)
        for cid in node.get("children", [])
    ]
    header = dbc.Row([
        dbc.Col(dcc.Dropdown(
            id={"type": "strf-groupop", "index": uid},
            options=[{"label": "AND (todas)", "value": "AND"},
                     {"label": "OR (alguna)", "value": "OR"}],
            value=node.get("op", "AND"), clearable=False,
            style={**_FS, "width": "130px"},
        ), width="auto"),
        dbc.Col(dbc.Button("+ condición",
                           id={"type": "strf-add-cond", "index": uid},
                           color="link", size="sm",
                           style={"fontSize": "0.78rem", "padding": "0 4px"}),
                width="auto"),
        dbc.Col(dbc.Button("+ grupo",
                           id={"type": "strf-add-group", "index": uid},
                           color="link", size="sm",
                           style={"fontSize": "0.78rem", "padding": "0 4px"}),
                width="auto"),
        dbc.Col(
            dbc.Button("×", id={"type": "strf-remove", "index": uid},
                       color="link", size="sm",
                       style={"color": "#ef5350", "padding": "0 6px",
                              "lineHeight": 1, "fontSize": "1rem",
                              "visibility": "hidden" if is_root else "visible"}),
            width="auto",
        ),
    ], className="g-1 mb-1 align-items-center")

    return html.Div(
        [header] + children,
        style={"borderLeft": "2px solid #555", "paddingLeft": "10px",
               "marginBottom": "6px"} if not is_root else {},
    )


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("str-filter-opts", "data"),
    Input("str-modal", "is_open"),
)
def cache_filter_opts(is_open):
    if not is_open:
        return no_update
    return build_filter_opts()


@callback(
    Output("str-filter-tree", "children"),
    Input("str-filter-store", "data"),
    Input("str-filter-opts",  "data"),
)
def render_filter_tree(store, opts):
    if not store or not opts:
        return html.Div()
    return _render_group(store.get("root", 0), store.get("nodes", {}),
                         opts, is_root=True)


def _capture_fields(store, ids_left, lefts, ids_op, ops, ids_val, vals,
                    ids_vs, vss):
    """Vuelca los valores actuales de los controles al store (por uid).
    Devuelve (store_nuevo, uid→left_anterior) para detectar cambios de
    operando."""
    nodes = store.get("nodes", {})
    prev_left = {}
    by_uid = {}
    for id_, v in zip(ids_left or [], lefts or []):
        by_uid.setdefault(id_["index"], {})["left"] = v
    for id_, v in zip(ids_op or [], ops or []):
        by_uid.setdefault(id_["index"], {})["op"] = v
    for id_, v in zip(ids_val or [], vals or []):
        by_uid.setdefault(id_["index"], {})["val"] = v
    for id_, v in zip(ids_vs or [], vss or []):
        by_uid.setdefault(id_["index"], {})["vs"] = v

    for uid, fields in by_uid.items():
        node = nodes.get(str(uid))
        if node is None or node.get("kind") != "cond":
            continue
        prev_left[uid] = node.get("left")
        node.update(fields)
    return store, prev_left


@callback(
    Output("str-filter-store", "data", allow_duplicate=True),
    Input({"type": "strf-add-cond",  "index": ALL}, "n_clicks"),
    Input({"type": "strf-add-group", "index": ALL}, "n_clicks"),
    Input({"type": "strf-remove",    "index": ALL}, "n_clicks"),
    Input({"type": "strf-groupop",   "index": ALL}, "value"),
    Input({"type": "strf-left",      "index": ALL}, "value"),
    Input({"type": "strf-op",        "index": ALL}, "value"),
    Input({"type": "strf-vs",        "index": ALL}, "value"),
    State({"type": "strf-left",      "index": ALL}, "id"),
    State({"type": "strf-op",        "index": ALL}, "id"),
    State({"type": "strf-val",       "index": ALL}, "value"),
    State({"type": "strf-val",       "index": ALL}, "id"),
    State({"type": "strf-vs",        "index": ALL}, "id"),
    State({"type": "strf-groupop",   "index": ALL}, "id"),
    State("str-filter-store", "data"),
    State("str-filter-opts",  "data"),
    prevent_initial_call=True,
)
def update_filter_store(add_cond_ns, add_group_ns, remove_ns, group_ops,
                        lefts, ops, vss,
                        ids_left, ids_op, vals, ids_val, ids_vs, ids_groupop,
                        store, opts):
    if not store:
        return no_update
    before = json.dumps(store, sort_keys=True)
    trigger = ctx.triggered_id

    store, prev_left = _capture_fields(
        store, ids_left, lefts, ids_op, ops, ids_val, vals, ids_vs, vss)
    nodes = store.get("nodes", {})

    # op de grupos (AND/OR)
    for id_, v in zip(ids_groupop or [], group_ops or []):
        node = nodes.get(str(id_["index"]))
        if node is not None and node.get("kind") == "group" and v:
            node["op"] = v

    # Cambio de operando izquierdo: si cambió, el tipo de dato (y el catálogo
    # de valores) puede haber cambiado — resetear operador/valor/vs
    if isinstance(trigger, dict) and trigger.get("type") == "strf-left":
        uid = trigger["index"]
        node = nodes.get(str(uid))
        if node is not None and node.get("left") != prev_left.get(uid):
            numeric = set((opts or {}).get("numeric", []))
            node["op"]  = "=" if node.get("left") not in numeric else ">"
            node["val"] = None
            node["vs"]  = None

    # Cambio de operador: si cambia entre multi (in/not_in) y escalar, el
    # control de valor cambia de forma — descartar el valor
    if isinstance(trigger, dict) and trigger.get("type") == "strf-op":
        uid = trigger["index"]
        node = nodes.get(str(uid))
        if node is not None:
            multi = node.get("op") in ("in", "not_in")
            if multi != isinstance(node.get("val"), list):
                node["val"] = None

    def _clicked(ns):
        return any(n for n in (ns or []) if n)

    if isinstance(trigger, dict) and trigger.get("type") == "strf-add-cond":
        if _clicked(add_cond_ns):
            uid = store["counter"]
            store["counter"] += 1
            nodes[str(uid)] = {"kind": "cond", "left": None, "op": None,
                               "val": None, "vs": None}
            nodes[str(trigger["index"])]["children"].append(uid)

    elif isinstance(trigger, dict) and trigger.get("type") == "strf-add-group":
        if _clicked(add_group_ns):
            uid = store["counter"]
            store["counter"] += 1
            nodes[str(uid)] = {"kind": "group", "op": "AND", "children": []}
            nodes[str(trigger["index"])]["children"].append(uid)

    elif isinstance(trigger, dict) and trigger.get("type") == "strf-remove":
        if _clicked(remove_ns):
            rem = trigger["index"]
            if rem != store.get("root"):
                def _drop(uid):
                    node = nodes.pop(str(uid), None)
                    if node and node.get("kind") == "group":
                        for cid in node.get("children", []):
                            _drop(cid)
                for node in nodes.values():
                    if node.get("kind") == "group" and rem in node.get("children", []):
                        node["children"] = [c for c in node["children"] if c != rem]
                _drop(rem)

    # Los ALL-Inputs también disparan cuando el render recrea los controles
    # con los mismos valores: si nada cambió, no reescribir el store (evita
    # el loop render → captura → render)
    if json.dumps(store, sort_keys=True) == before:
        return no_update
    return store
