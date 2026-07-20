import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html

from app.components.help import help_link

from app.components.table_styles import CELL, DATA, FILTER, HEADER, SELECTED_ROW

_TYPE_OPTS = [
    {"label": "Seguimiento (teórica)", "value": "seg"},
    {"label": "Real", "value": "real"},
]
_FILTER_OPTS = [
    {"label": "Todas", "value": ""},
    {"label": "Seguimiento", "value": "seg"},
    {"label": "Reales", "value": "real"},
]


def layout(**kwargs):
    from flask_login import current_user
    # Abierto a analistas: ven las propias + públicas, editan solo las propias
    # (misma convención que Estrategias, ver app/services/visibility.py).
    if not current_user.is_authenticated:
        return html.Div()

    modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(id="cart-modal-title")),
        dbc.ModalBody([
            dbc.Row([dbc.Col([
                dbc.Label("Nombre", style={"fontSize": "0.82rem"}),
                dbc.Input(id="cart-f-name", placeholder="Nombre de la cartera",
                          style={"fontSize": "0.85rem"}),
            ])], className="mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Tipo", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="cart-f-type", options=_TYPE_OPTS,
                                 value="real", clearable=False,
                                 style={"fontSize": "0.85rem"}),
                ], md=6),
                dbc.Col([
                    dbc.Label("Moneda base", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="cart-f-currency", placeholder="ARS",
                              style={"fontSize": "0.85rem"}),
                ], md=6),
            ], className="mb-2 g-2"),
            dbc.Switch(id="cart-f-public",
                       label="Pública (visible para todos los usuarios)",
                       value=False, style={"fontSize": "0.82rem"}),
            html.Small("Privada: solo vos (y el admin) la ven.",
                       className="text-muted d-block mb-2"),

            html.Hr(className="my-2"),
            html.Small("Composición (sólo carteras de Seguimiento):",
                       className="text-muted d-block mb-1"),
            dbc.Row([
                dbc.Col([dbc.Label("Método", style={"fontSize": "0.82rem"}),
                         dcc.Dropdown(id="cart-f-method", options=[
                             {"label": "Curada (lista manual)", "value": "curated"},
                             {"label": "Derivada de estrategia",
                              "value": "strategy"},
                         ], placeholder="—", style={"fontSize": "0.85rem"})], md=6),
                dbc.Col([dbc.Label("Top-N (si derivada)",
                                   style={"fontSize": "0.82rem"}),
                         dbc.Input(id="cart-f-topn", type="number", value=20,
                                   min=1, style={"fontSize": "0.85rem"})], md=6),
            ], className="mb-2 g-2"),
            dbc.Row([dbc.Col([
                dbc.Label("Estrategia (si derivada)",
                          style={"fontSize": "0.82rem"}),
                dcc.Dropdown(id="cart-f-strategy", placeholder="Estrategia…",
                             style={"fontSize": "0.85rem"})])], className="mb-2"),
            dbc.Row([dbc.Col([
                dbc.Label("Activos (si curada)", style={"fontSize": "0.82rem"}),
                dcc.Dropdown(id="cart-f-members", multi=True,
                             placeholder="Elegí activos…",
                             style={"fontSize": "0.85rem"})])], className="mb-2"),
            dbc.Row([dbc.Col([
                dbc.Label("Teórica objetivo (opcional, para las reales)",
                          style={"fontSize": "0.82rem"}),
                dcc.Dropdown(id="cart-f-link", clearable=True,
                             placeholder="Vincular a una teórica…",
                             style={"fontSize": "0.85rem"})])], className="mb-2"),

            dbc.Alert(id="cart-modal-error", is_open=False, color="danger",
                      className="mt-2 mb-0 small py-1"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Guardar", id="cart-btn-save", color="primary"),
            dbc.Button("Cancelar", id="cart-btn-cancel", color="secondary",
                       className="ms-2"),
        ]),
    ], id="cart-modal", is_open=False)

    _num_style = {"fontSize": "0.85rem"}
    txn_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Nueva operación")),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Activo", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="cart-txn-asset", placeholder="Activo...",
                                 style=_num_style),
                ], md=6),
                dbc.Col([
                    dbc.Label("Operación", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="cart-txn-kind", clearable=False, value="buy",
                                 options=[
                                     {"label": "Compra",    "value": "buy"},
                                     {"label": "Venta",     "value": "sell"},
                                     {"label": "Dividendo", "value": "dividend"},
                                     {"label": "Split",     "value": "split"},
                                 ], style=_num_style),
                ], md=3),
                dbc.Col([
                    dbc.Label("Fecha", style={"fontSize": "0.82rem"}),
                    dcc.DatePickerSingle(id="cart-txn-date",
                                         display_format="YYYY-MM-DD"),
                ], md=3, className="d-flex flex-column"),
            ], className="mb-2 g-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Cantidad", style={"fontSize": "0.82rem"}),
                         dbc.Input(id="cart-txn-qty", type="number",
                                   style=_num_style)], md=3),
                dbc.Col([dbc.Label("Precio", style={"fontSize": "0.82rem"}),
                         dbc.Input(id="cart-txn-price", type="number",
                                   placeholder="mercado", style=_num_style)], md=3),
                dbc.Col([dbc.Label("Comisión", style={"fontSize": "0.82rem"}),
                         dbc.Input(id="cart-txn-commission", type="number",
                                   value=0, style=_num_style)], md=3),
                dbc.Col([dbc.Label("Impuestos", style={"fontSize": "0.82rem"}),
                         dbc.Input(id="cart-txn-taxes", type="number",
                                   value=0, style=_num_style)], md=3),
            ], className="mb-2 g-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Moneda", style={"fontSize": "0.82rem"}),
                         dbc.Input(id="cart-txn-currency", placeholder="ARS",
                                   style=_num_style)], md=4),
                dbc.Col([dbc.Label("Nota", style={"fontSize": "0.82rem"}),
                         dbc.Input(id="cart-txn-note", style=_num_style)], md=8),
            ], className="mb-2 g-2"),
            html.Small("Precio vacío → se toma el cierre de mercado de la fecha.",
                       className="text-muted d-block mb-1"),
            dbc.Alert(id="cart-txn-error", is_open=False, color="danger",
                      className="mt-2 mb-0 small py-1"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Guardar", id="cart-btn-save-txn", color="primary"),
            dbc.Button("Cancelar", id="cart-btn-cancel-txn", color="secondary",
                       className="ms-2"),
        ]),
    ], id="cart-txn-modal", is_open=False, size="lg")

    return html.Div([
        dcc.Store(id="cart-editing-id", data=None),
        dcc.Store(id="cart-selected-id", data=None),
        dcc.Store(id="cart-detail-refresh", data=0),
        dcc.Store(id="cart-reload", data=0),

        dbc.Row([
            dbc.Col(html.H4(["Carteras ", help_link("carteras")], className="mb-0"), width="auto"),
            dbc.Col(dbc.Button("+ Nueva cartera", id="cart-btn-add",
                               color="primary", size="sm"),
                    className="d-flex align-items-center"),
        ], className="mb-2 align-items-center g-2"),

        dbc.RadioItems(id="cart-filter", options=_FILTER_OPTS, value="",
                       inline=True, className="mb-2 small"),

        html.Div([
            dbc.Button("Editar", id="cart-btn-edit", color="secondary",
                       size="sm", disabled=True, className="me-1"),
            dbc.Button("Eliminar", id="cart-btn-delete", color="danger",
                       size="sm", disabled=True),
        ], className="mb-2"),

        dbc.Alert(id="cart-alert", is_open=False, dismissable=True,
                  className="mb-3"),

        dash_table.DataTable(
            id="cart-table",
            columns=[
                {"name": "Nombre",  "id": "name"},
                {"name": "Tipo",    "id": "tipo"},
                {"name": "Dueño",   "id": "owner"},
                {"name": "Pública", "id": "publica"},
                {"name": "Moneda",  "id": "currency"},
            ],
            data=[],
            row_selectable="single",
            selected_rows=[],
            style_table={"overflowX": "auto"},
            style_header=HEADER,
            style_data=DATA,
            style_cell=CELL,
            style_filter=FILTER,
            style_data_conditional=SELECTED_ROW,
            page_size=30,
            sort_action="native",
            filter_action="native",
        ),

        # Detalle de la cartera seleccionada (equity/tenencias)
        html.Div(id="cart-detail", className="mt-3"),

        modal,
        txn_modal,
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/carteras", title="Carteras", layout=layout)
