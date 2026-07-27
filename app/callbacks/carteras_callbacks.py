"""Callbacks de la biblioteca de Carteras (/carteras).

Sub-paso A: listar (con visibilidad propia+pública), alta/edición/baja con el
modal ABM que NO se cierra ante error (solo el guardado exitoso lo cierra). El
detalle (equity/tenencias/operaciones) se cablea en el sub-paso B.
"""
import threading

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, ctx, dcc, html, no_update

from app.components import portfolio_views as pv
from app.services import portfolio_service as svc
from app.services.visibility import can_edit, current_viewer, publica_str

_TIPO_LBL = {"seg": "Seguimiento", "real": "Real"}
_KIND_LBL = {"buy": "Compra", "sell": "Venta", "dividend": "Dividendo",
             "split": "Split"}

# Estado del "Recalcular curva" de una cartera 'strategy' promovida: corre
# run_portfolio_backtest en un thread (pesado, todo el universo) y repunta el
# snapshot. Un recálculo a la vez (lock). Sobrevive al re-render del detalle.
_recalc_state = {"running": False, "current": 0, "total": 0, "phase": "",
                 "error": None, "pid": None}
_recalc_lock = threading.Lock()


@callback(
    Output("cart-table", "rowData"),
    Output("cart-table", "selectedRows"),
    Input("cart-reload", "data"),
    Input("cart-filter", "value"),
)
def load_table(_reload, ptype):
    # Recarga por señal monótona (cart-reload, que save/delete incrementan) +
    # filtro. Resetea selected_rows=[] en CADA recarga para no dejar la
    # selección desincronizada de las filas visibles (patrón admin_strategies);
    # eso dispara update_selected → cart-selected-id=None → detalle/ botones se
    # limpian.
    from app.database import get_session
    from app.models import User
    s = get_session()
    users = {uid: uname
             for uid, uname in s.query(User.id, User.username).all()}
    user_id, is_admin = current_viewer()
    rows = svc.list_portfolios(s, user_id, is_admin, ptype=ptype or None)
    data = [{
        "id": p.id,
        "owner_id": p.owner_id,
        "is_public": p.is_public,
        "ptype": p.ptype,
        "currency_raw": p.base_currency or "",
        "name": p.name,
        "tipo": _TIPO_LBL.get(p.ptype, p.ptype),
        "owner": users.get(p.owner_id, "—"),
        "publica": publica_str(p.is_public),
        "currency": p.base_currency or "—",
    } for p in rows]
    return data, []


@callback(
    Output("cart-selected-id", "data"),
    Input("cart-table", "selectedRows"),
    prevent_initial_call=True,
)
def update_selected(selected_rows):
    if not selected_rows:
        return None
    return selected_rows[0]["id"]


@callback(
    Output("cart-btn-edit", "disabled"),
    Output("cart-btn-delete", "disabled"),
    Input("cart-selected-id", "data"),
    State("cart-table", "rowData"),
)
def update_buttons(sel_id, data):
    if not sel_id or not data:
        return True, True
    row = next((r for r in data if r["id"] == sel_id), None)
    if row is None:
        return True, True
    user_id, is_admin = current_viewer()
    editable = can_edit(row.get("owner_id"), user_id, is_admin)
    return (not editable), (not editable)


@callback(
    Output("cart-modal", "is_open"),
    Output("cart-modal-title", "children"),
    Output("cart-f-name", "value"),
    Output("cart-f-type", "value"),
    Output("cart-f-currency", "value"),
    Output("cart-f-public", "value"),
    Output("cart-editing-id", "data"),
    Output("cart-modal-error", "is_open", allow_duplicate=True),
    Input("cart-btn-add", "n_clicks"),
    Input("cart-btn-cancel", "n_clicks"),
    Input("cart-btn-edit", "n_clicks"),
    State("cart-selected-id", "data"),
    State("cart-table", "rowData"),
    prevent_initial_call=True,
)
def toggle_modal(_add, _cancel, _edit, sel_id, data):
    trig = ctx.triggered_id
    if trig == "cart-btn-cancel":
        return (False, no_update, no_update, no_update, no_update, no_update,
                no_update, False)
    if trig == "cart-btn-add":
        return True, "Nueva cartera", "", "real", "", False, None, False
    if trig == "cart-btn-edit":
        row = next((r for r in (data or []) if r["id"] == sel_id), None)
        if row is None:
            return (no_update,) * 8
        return (True, "Editar cartera", row["name"], row["ptype"],
                row.get("currency_raw", ""), bool(row["is_public"]), sel_id,
                False)
    return (no_update,) * 8


@callback(
    Output("cart-f-strategy", "options"),
    Output("cart-f-members", "options"),
    Output("cart-f-link", "options"),
    Input("cart-modal", "is_open"),
)
def load_composition_options(is_open):
    if not is_open:
        return no_update, no_update, no_update
    from app.database import get_session
    from app.models import Asset
    from app.services.strategy_service import get_visible_strategies
    s = get_session()
    user_id, is_admin = current_viewer()
    strat = [{"label": st.name, "value": st.id}
             for st in get_visible_strategies(user_id, is_admin)]
    assets = [{"label": tk or f"#{i}", "value": i}
              for i, tk in s.query(Asset.id, Asset.ticker)
              .order_by(Asset.ticker).all()]
    segs = [{"label": pf.name, "value": pf.id}
            for pf in svc.list_portfolios(s, user_id, is_admin, ptype="seg")]
    return strat, assets, segs


@callback(
    Output("cart-alert", "children"),
    Output("cart-alert", "is_open"),
    Output("cart-modal", "is_open", allow_duplicate=True),
    Output("cart-modal-error", "children"),
    Output("cart-modal-error", "is_open"),
    Output("cart-reload", "data"),
    Input("cart-btn-save", "n_clicks"),
    State("cart-f-name", "value"),
    State("cart-f-type", "value"),
    State("cart-f-currency", "value"),
    State("cart-f-public", "value"),
    State("cart-f-method", "value"),
    State("cart-f-strategy", "value"),
    State("cart-f-topn", "value"),
    State("cart-f-members", "value"),
    State("cart-f-link", "value"),
    State("cart-editing-id", "data"),
    State("cart-reload", "data"),
    prevent_initial_call=True,
)
def save(_n, name, ptype, currency, is_public, method, strategy_id, topn,
         members, link, editing_id, reload):
    def err(msg):
        # El modal NO se cierra ante error: solo se muestra el mensaje.
        return no_update, no_update, no_update, msg, True, no_update

    name = (name or "").strip()
    if not name:
        return err("El nombre es obligatorio.")
    if ptype not in ("seg", "real"):
        return err("Elegí el tipo de cartera.")

    from app.database import get_session
    s = get_session()
    user_id, is_admin = current_viewer()
    currency = (currency or "").strip() or None
    try:
        if editing_id:
            p = svc.get_portfolio(s, editing_id)
            if p is None:
                return err("La cartera ya no existe.")
            if not can_edit(p.owner_id, user_id, is_admin):
                return err("No tenés permiso para editar esta cartera.")
            # Marcar pública una cartera derivada de una estrategia privada
            # filtraría esa estrategia: misma regla que estrategia→señal.
            ref_err = svc.public_ref_error(
                s, is_public=bool(is_public),
                composition_method=p.composition_method,
                strategy_id=p.strategy_id)
            if ref_err:
                return err(ref_err)
            p.name = name
            p.ptype = ptype
            p.base_currency = currency
            p.is_public = bool(is_public)
            s.commit()
            msg = f"Cartera «{name}» actualizada."
        else:
            comp = (method or None) if ptype == "seg" else None
            if comp == "strategy" and not strategy_id:
                return err("Elegí una estrategia para la cartera derivada.")
            if comp == "curated" and not members:
                return err("Elegí al menos un activo para la cartera curada.")
            ref_err = svc.public_ref_error(
                s, is_public=bool(is_public), composition_method=comp,
                strategy_id=(strategy_id if comp == "strategy" else None))
            if ref_err:
                return err(ref_err)
            new_p = svc.create_portfolio(
                s, name, ptype, owner_id=user_id, is_public=bool(is_public),
                base_currency=currency, composition_method=comp,
                strategy_id=(strategy_id if comp == "strategy" else None),
                top_n=(int(_num(topn))
                       if comp == "strategy" and _num(topn) else None),
                linked_portfolio_id=(link if ptype == "real" else None))
            if comp == "curated" and members:
                svc.set_members(s, new_p.id, members)
            msg = f"Cartera «{name}» creada."
    except Exception:
        s.rollback()
        return err("No se pudo guardar la cartera. Revisá los datos.")

    # Éxito: cierra el modal, avisa y recarga la lista (resetea la selección).
    return msg, True, False, no_update, False, (reload or 0) + 1


@callback(
    Output("cart-alert", "children", allow_duplicate=True),
    Output("cart-alert", "is_open", allow_duplicate=True),
    Output("cart-reload", "data", allow_duplicate=True),
    Input("cart-btn-delete", "n_clicks"),
    State("cart-selected-id", "data"),
    State("cart-reload", "data"),
    prevent_initial_call=True,
)
def delete_selected(_n, sel_id, reload):
    if not sel_id:
        return no_update, no_update, no_update
    from app.database import get_session
    s = get_session()
    user_id, is_admin = current_viewer()
    p = svc.get_portfolio(s, sel_id)
    if p is None:
        return no_update, no_update, no_update
    if not can_edit(p.owner_id, user_id, is_admin):
        return "No tenés permiso para eliminar esta cartera.", True, no_update
    name = p.name
    svc.delete_portfolio(s, sel_id)
    # La recarga (cart-reload) resetea selected_rows → cart-selected-id=None.
    return f"Cartera «{name}» eliminada.", True, (reload or 0) + 1


# ── Detalle de la cartera ─────────────────────────────────────────────────────

def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _money(x):
    return "—" if x is None else f"{x:,.0f}"


def _table(headers, rows):
    return dbc.Table(
        [html.Thead(html.Tr([html.Th(h) for h in headers])),
         html.Tbody([html.Tr([html.Td(c) for c in r]) for r in rows])],
        bordered=False, hover=True, size="sm", className="small mb-0")


def _spec_summary(spec):
    """Texto humano de las reglas del simulador guardadas en el spec."""
    if not spec:
        return "Sin reglas de entrada/salida."
    parts = []
    ent = []
    for e in spec.get("entries", []):
        if e.get("type") == "score":
            ent.append(f"score ≥ {e['th']:g}")
        elif e.get("type") == "pct":
            ent.append(f"percentil ≥ {e['th']:g}")
    if ent:
        parts.append("Entrada: " + " y ".join(ent))
    ex = [f"score < {e['x']:g}" for e in spec.get("score_exits", [])
          if e.get("type") == "absolute"]
    _CAP = {"max_bars": lambda c: f"máx {c['n']} barras",
            "stop_loss": lambda c: f"stop loss {c['pct']:g}%",
            "trailing_stop": lambda c: f"trailing {c['pct']:g}%",
            "take_profit": lambda c: f"take profit {c['pct']:g}%"}
    for c in spec.get("caps", []):
        fn = _CAP.get(c.get("type"))
        if fn:
            ex.append(fn(c))
    if ex:
        parts.append("Salida: " + ", ".join(ex))
    if spec.get("cooldown"):
        parts.append(f"cooldown {spec['cooldown']}")
    if spec.get("rearm"):
        parts.append("re-arme")
    return " · ".join(parts) if parts else "Sin reglas de entrada/salida."


def _config_badges(config):
    """Badges + resumen de la config gated de una cartera promovida."""
    spec = config.get("spec") or {}
    badges = html.Div([
        dbc.Badge(f"Top-{config.get('top_n') or '?'}", color="primary",
                  className="me-1"),
        dbc.Badge(f"Rebalanceo cada {config.get('rebalance') or 1}",
                  color="secondary", className="me-1"),
        dbc.Badge(f"Costo {config.get('cost_bps') or 0:g} bps",
                  color="secondary", className="me-1"),
    ], className="mb-1")
    return html.Div([badges, html.Small(_spec_summary(spec),
                                        className="text-muted d-block")],
                    className="mb-2")


@callback(
    Output("cart-detail", "children"),
    Input("cart-selected-id", "data"),
    Input("cart-detail-refresh", "data"),
)
def render_detail(sel_id, _refresh):
    if not sel_id:
        return None
    from app.database import get_session
    from app.models import Asset
    s = get_session()
    p = svc.get_portfolio(s, sel_id)
    if p is None:
        return None

    user_id, is_admin = current_viewer()
    editable = can_edit(p.owner_id, user_id, is_admin)
    cur = p.base_currency or ""

    header = html.Div([
        html.H5(p.name, className="d-inline me-2"),
        dbc.Badge(_TIPO_LBL.get(p.ptype, p.ptype),
                  color="info" if p.ptype == "seg" else "success",
                  className="me-1"),
        dbc.Badge("Pública" if p.is_public else "Privada", color="secondary",
                  className="me-1"),
        html.Span(cur, className="text-muted small"),
    ], className="mb-2")

    if p.ptype != "real":
        members = svc.resolve_membership(s, sel_id)
        _METHOD = {"curated": "Curada (lista manual)",
                   "strategy": "Derivada de estrategia"}
        method_lbl = _METHOD.get(p.composition_method,
                                 "Sin composición definida")
        mids = [a for a, _ in members]
        mtk = ({i: t for i, t in
                s.query(Asset.id, Asset.ticker).filter(Asset.id.in_(mids)).all()}
               if mids else {})
        if members:
            body = _table(["Activo", "Peso"],
                          [[mtk.get(a, f"#{a}"), f"{w * 100:.1f}%"]
                           for a, w in members])
        else:
            body = html.Small("Sin miembros vigentes todavía.",
                              className="text-muted")
        extra, chart = [], html.Div()
        if p.composition_method == "curated":
            from app.services.portfolio_backtest_service import (
                curated_equity_series)
            es = curated_equity_series(s, sel_id)
            if es and es["dates"]:
                tiles = pv.kpi_tiles([
                    {"label": "Retorno total",
                     "value": pv.fmt_mult(es["total_return"])},
                    {"label": "CAGR", "value": pv.fmt_pct(es["cagr"], signed=True),
                     "good": (es["cagr"] or 0) >= 0},
                    {"label": "Sharpe", "value": pv.fmt_ratio(es["sharpe"])},
                    {"label": "Máx drawdown",
                     "value": pv.fmt_pct(es["max_drawdown"]), "good": False},
                ])
                fig = pv.equity_figure(
                    [{"name": "Equity (constant-mix)",
                      "values": [v * 100 for v in es["equity"]]}], x=es["dates"])
                chart = html.Div([tiles, dcc.Graph(
                    figure=fig, config=pv.graph_config())], className="mt-2")
        elif p.composition_method == "strategy" and p.sim_spec:
            from app.services.portfolio_backtest_service import (
                strategy_gated_equity_series)
            es = strategy_gated_equity_series(s, sel_id)
            if es and es["dates"]:
                k = es["kpis"]
                tiles = pv.kpi_tiles([
                    {"label": "Retorno total",
                     "value": pv.fmt_mult(k.get("total_return"))},
                    {"label": "CAGR", "value": pv.fmt_pct(k.get("cagr"),
                                                          signed=True),
                     "good": (k.get("cagr") or 0) >= 0},
                    {"label": "Sharpe", "value": pv.fmt_ratio(k.get("sharpe"))},
                    {"label": "Máx drawdown",
                     "value": pv.fmt_pct(k.get("max_drawdown")), "good": False},
                ])
                fig = pv.equity_figure(
                    [{"name": "Con reglas (gated)",
                      "values": [v * 100 for v in es["equity"]]}], x=es["dates"])
                when = es["run_created_at"]
                chart = html.Div([
                    _config_badges(es["config"]),
                    tiles,
                    dcc.Graph(figure=fig, config=pv.graph_config()),
                    html.Small(
                        ("Curva congelada al "
                         f"{when:%Y-%m-%d %H:%M}" if when else "Curva congelada")
                        + " · «Recalcular» la actualiza con los datos de hoy.",
                        className="text-muted d-block mt-1"),
                    (dbc.Button("Recalcular curva", id="cart-btn-recalc",
                                color="secondary", size="sm", className="mt-2")
                     if editable else html.Div()),
                ], className="mt-2")
            else:
                extra.append(html.Small(
                    "El snapshot de la curva no está disponible. Volvé a promoverla "
                    "desde /backtest → Cartera.", className="text-muted d-block"))
        elif p.composition_method == "strategy":
            extra.append(html.Small(
                f"Top-{p.top_n or 20} por score (ranking puro). Para una curva con "
                "reglas, promovéla desde /backtest → Cartera.",
                className="text-muted d-block"))
        members_note = (html.Small(
            "Miembros = top-N por ranking (la selección con reglas se ve en la "
            "curva).", className="text-muted d-block")
            if p.composition_method == "strategy" and p.sim_spec else html.Div())
        return html.Div([
            header,
            html.Div([html.Span("Composición: ", className="text-muted"),
                      dbc.Badge(method_lbl, color="info")], className="mb-2"),
            *extra,
            chart,
            html.H6("Miembros vigentes", className="mt-2"),
            members_note,
            body,
        ])

    holdings = svc.resolve_holdings(s, sel_id)
    es = svc.equity_series(s, sel_id)
    txns = svc.list_transactions(s, sel_id)
    drift = svc.tracking_drift(s, sel_id)

    ids = {h["asset_id"] for h in holdings} | {t.asset_id for t in txns}
    if drift:
        ids |= {r["asset_id"] for r in drift["rows"]}
    tickers = ({i: tk for i, tk in
                s.query(Asset.id, Asset.ticker).filter(Asset.id.in_(ids)).all()}
               if ids else {})

    mv = sum(h["market_value"] for h in holdings
             if h["market_value"] is not None)
    upnl = sum(h["unrealized_pnl"] for h in holdings
               if h["unrealized_pnl"] is not None)
    # realized total incluye posiciones cerradas (resolve_holdings solo trae las
    # abiertas), si no el KPI subestima la ganancia.
    rpnl = svc.realized_pnl_total(s, sel_id)
    total_pnl = upnl + rpnl

    tiles = pv.kpi_tiles([
        {"label": f"Valor de mercado {cur}".strip(), "value": _money(mv)},
        {"label": "P&L total", "value": _money(total_pnl),
         "good": total_pnl >= 0},
        {"label": "P&L no realizado", "value": _money(upnl), "good": upnl >= 0},
        {"label": "Posiciones", "value": str(len(holdings))},
    ])

    if es["dates"]:
        fig = pv.equity_figure(
            [{"name": "Valor de tenencias", "values": es["holdings_value"]}],
            x=es["dates"])
        chart = dcc.Graph(figure=fig, config=pv.graph_config())
    else:
        chart = dbc.Alert("Sin operaciones todavía.", color="secondary",
                          className="small py-2")

    hold_rows = [[
        tickers.get(h["asset_id"], f"#{h['asset_id']}"),
        f"{h['quantity']:,.0f}",
        _money(h["avg_cost"]), _money(h["market_price"]),
        _money(h["market_value"]), _money(h["unrealized_pnl"]),
    ] for h in holdings]
    holdings_tbl = _table(
        ["Activo", "Cant.", "P. prom.", "P. mercado", "Valor", "P&L no real."],
        hold_rows) if hold_rows else html.Small(
        "Sin posiciones abiertas.", className="text-muted")

    txn_rows = [[
        tickers.get(t.asset_id, f"#{t.asset_id}"),
        _KIND_LBL.get(t.kind, t.kind), t.trade_date.isoformat(),
        "—" if t.quantity is None else f"{t.quantity:,.0f}",
        "mercado" if t.price is None else _money(t.price),
        _money(t.commission), _money(t.taxes), t.currency or "—",
    ] for t in txns]
    txns_tbl = _table(
        ["Activo", "Op.", "Fecha", "Cant.", "Precio", "Comisión", "Impuestos",
         "Moneda"], txn_rows) if txn_rows else html.Small(
        "Sin operaciones registradas.", className="text-muted")

    drift_block = html.Div()
    if drift:
        drift_rows = [[
            tickers.get(r["asset_id"], f"#{r['asset_id']}"),
            f"{r['target_w'] * 100:.1f}%", f"{r['real_w'] * 100:.1f}%",
            html.Span(f"{r['diff'] * 100:+.1f}%",
                      className="text-success" if r["diff"] >= 0
                      else "text-danger"),
        ] for r in drift["rows"]]
        drift_block = html.Div([
            html.H6(f"Desvío vs teórica objetivo «{drift['target_name']}»",
                    className="mt-3"),
            html.Small("Desvío = peso real − objetivo (negativo = faltante).",
                       className="text-muted d-block mb-1"),
            _table(["Activo", "Objetivo", "Real", "Desvío"], drift_rows),
        ])

    return html.Div([
        header,
        tiles,
        html.Hr(className="my-3"),
        chart,
        html.Hr(className="my-3"),
        dbc.Button("+ Agregar operación", id="cart-btn-add-txn", color="primary",
                   size="sm", disabled=not editable, className="mb-2"),
        html.H6("Posiciones actuales", className="mt-2"),
        holdings_tbl,
        html.H6("Registro de operaciones", className="mt-3"),
        txns_tbl,
        drift_block,
    ])


# ── Modal de operación (registro) ─────────────────────────────────────────────

@callback(
    Output("cart-txn-modal", "is_open"),
    Output("cart-txn-error", "is_open", allow_duplicate=True),
    Output("cart-txn-asset", "value"),
    Output("cart-txn-kind", "value"),
    Output("cart-txn-date", "date"),
    Output("cart-txn-qty", "value"),
    Output("cart-txn-price", "value"),
    Output("cart-txn-commission", "value"),
    Output("cart-txn-taxes", "value"),
    Output("cart-txn-currency", "value"),
    Output("cart-txn-note", "value"),
    Input("cart-btn-add-txn", "n_clicks"),
    Input("cart-btn-cancel-txn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_txn_modal(_add, _cancel):
    trig = ctx.triggered_id
    if trig == "cart-btn-cancel-txn":
        return (False, False) + (no_update,) * 9
    if trig == "cart-btn-add-txn":
        # Abre limpio (defaults) para no reenviar la operación anterior.
        return (True, False, None, "buy", None, None, None, 0, 0, "", "")
    return (no_update,) * 11


@callback(
    Output("cart-txn-asset", "options"),
    Input("cart-txn-modal", "is_open"),
)
def load_asset_options(is_open):
    if not is_open:
        return no_update
    from app.database import get_session
    from app.models import Asset
    s = get_session()
    return [{"label": tk or f"#{i}", "value": i}
            for i, tk in s.query(Asset.id, Asset.ticker)
            .order_by(Asset.ticker).all()]


@callback(
    Output("cart-txn-modal", "is_open", allow_duplicate=True),
    Output("cart-txn-error", "children"),
    Output("cart-txn-error", "is_open"),
    Output("cart-detail-refresh", "data"),
    Input("cart-btn-save-txn", "n_clicks"),
    State("cart-selected-id", "data"),
    State("cart-txn-asset", "value"),
    State("cart-txn-kind", "value"),
    State("cart-txn-date", "date"),
    State("cart-txn-qty", "value"),
    State("cart-txn-price", "value"),
    State("cart-txn-commission", "value"),
    State("cart-txn-taxes", "value"),
    State("cart-txn-currency", "value"),
    State("cart-txn-note", "value"),
    State("cart-detail-refresh", "data"),
    prevent_initial_call=True,
)
def save_txn(_n, pid, asset_id, kind, trade_date, qty, price, commission, taxes,
             currency, note, refresh):
    def err(msg):
        return no_update, msg, True, no_update

    if not pid:
        return err("Elegí una cartera primero.")
    if not asset_id:
        return err("Elegí un activo.")
    if kind not in ("buy", "sell", "dividend", "split"):
        return err("Tipo de operación inválido.")
    if not trade_date:
        return err("La fecha es obligatoria.")
    from datetime import date as _date
    try:
        d = _date.fromisoformat(str(trade_date)[:10])
    except ValueError:
        return err("Fecha inválida.")

    from app.database import get_session
    s = get_session()
    p = svc.get_portfolio(s, pid)
    if p is None:
        return err("La cartera ya no existe.")
    user_id, is_admin = current_viewer()
    if not can_edit(p.owner_id, user_id, is_admin):
        return err("No tenés permiso para operar en esta cartera.")

    try:
        svc.add_transaction(
            s, pid, asset_id, kind, d,
            quantity=_num(qty), price=_num(price),
            commission=_num(commission) or 0.0, taxes=_num(taxes) or 0.0,
            currency=(currency or "").strip() or None,
            note=(note or "").strip() or None)
    except Exception:
        s.rollback()
        return err("No se pudo registrar la operación.")

    return False, no_update, False, (refresh or 0) + 1


# ── Recalcular la curva de una cartera 'strategy' promovida ────────────────────

@callback(
    Output("cart-recalc-alert", "children"),
    Output("cart-recalc-alert", "is_open"),
    Output("cart-recalc-alert", "color"),
    Output("cart-recalc-interval", "disabled"),
    Input("cart-btn-recalc", "n_clicks"),
    State("cart-selected-id", "data"),
    prevent_initial_call=True,
)
def start_recalc(_n, pid):
    """Re-corre el motor gated con el sim_spec de la cartera (todo el universo, en
    un thread) y repunta el snapshot. Un recálculo a la vez."""
    if not pid:
        return no_update, no_update, no_update, no_update
    import json

    from app.database import get_session
    s = get_session()
    p = svc.get_portfolio(s, pid)
    if p is None or not p.sim_spec:
        return ("Esta cartera no tiene reglas para recalcular.", True, "warning",
                True)
    user_id, is_admin = current_viewer()
    if not can_edit(p.owner_id, user_id, is_admin):
        return ("No tenés permiso para recalcular esta cartera.", True, "warning",
                True)
    if not _recalc_lock.acquire(blocking=False):
        return "Ya hay un recálculo en curso.", True, "warning", no_update

    config = json.loads(p.sim_spec or "{}")
    strategy_id = p.strategy_id
    _recalc_state.update({"running": True, "current": 0, "total": 0, "phase": "",
                          "error": None, "pid": pid})

    def _run():
        from app.database import Session, get_session
        from app.services.portfolio_backtest_service import (
            run_portfolio_backtest, snapshot_strategy_portfolio)

        def _progress(cur, tot, phase):
            (_recalc_state["current"], _recalc_state["total"],
             _recalc_state["phase"]) = cur, tot, phase

        try:
            result = run_portfolio_backtest(
                strategy_id, config.get("spec") or {},
                top_n=int(config.get("top_n") or 20),
                rebalance_every=int(config.get("rebalance") or 1),
                cost_bps=float(config.get("cost_bps") or 0.0),
                progress_cb=_progress)
            snapshot_strategy_portfolio(get_session(), pid, result)
        except Exception as exc:
            _recalc_state["error"] = str(exc)
        finally:
            _recalc_state["running"] = False
            _recalc_lock.release()
            Session.remove()

    threading.Thread(target=_run, daemon=True).start()
    return "Recalculando la curva…", True, "info", False


@callback(
    Output("cart-recalc-alert", "children", allow_duplicate=True),
    Output("cart-recalc-alert", "is_open", allow_duplicate=True),
    Output("cart-recalc-alert", "color", allow_duplicate=True),
    Output("cart-recalc-interval", "disabled", allow_duplicate=True),
    Output("cart-detail-refresh", "data", allow_duplicate=True),
    Input("cart-recalc-interval", "n_intervals"),
    State("cart-detail-refresh", "data"),
    prevent_initial_call=True,
)
def poll_recalc(_n, refresh):
    if _recalc_state["running"]:
        cur, tot = _recalc_state["current"], _recalc_state["total"] or 0
        label = (f"Recalculando… {_recalc_state['phase']} {cur}/{tot}"
                 if tot else "Recalculando la curva…")
        return label, True, "info", False, no_update
    if _recalc_state["error"]:
        return (f"Error al recalcular: {_recalc_state['error']}", True, "danger",
                True, no_update)
    # Terminó bien: apaga el interval y redibuja el detalle con la curva nueva.
    return ("Curva recalculada.", True, "success", True, (refresh or 0) + 1)
