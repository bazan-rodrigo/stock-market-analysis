import sqlalchemy as sa
from dash import Input, Output, callback, html, no_update
import dash_bootstrap_components as dbc

from app.database import get_session
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_store import get_ind_table

_CARD = {"backgroundColor": "#1f2937", "border": "1px solid #374151", "borderRadius": "8px"}

_TREND_LABELS = {
    "bullish_strong":         ("Alcista Fuerte",          "#2e7d32"),
    "bullish_nascent_strong": ("Alcista Naciente Fuerte", "#66bb6a"),
    "bullish":                ("Alcista",                 "#4caf50"),
    "bullish_nascent":        ("Alcista Naciente",        "#a5d6a7"),
    "lateral_nascent":        ("Lateral Naciente",        "#90caf9"),
    "lateral":                ("Lateral",                 "#6495ed"),
    "bearish_nascent":        ("Bajista Naciente",        "#ef9a9a"),
    "bearish_nascent_strong": ("Bajista Naciente Fuerte", "#ef5350"),
    "bearish":                ("Bajista",                 "#ef5350"),
    "bearish_strong":         ("Bajista Fuerte",          "#b71c1c"),
}

_VOL_REGIME_COLOR = {
    "extrema": "#ef5350",
    "alta":    "#ff9800",
    "normal":  "#90a4ae",
    "baja":    "#42a5f5",
}


def _fmt(defn: IndicatorDefinition, value) -> tuple[str, str]:
    """Devuelve (texto_a_mostrar, color_hex). value es el valor crudo de la columna."""

    NEUTRAL = "#dee2e6"
    MUTED   = "#6b7280"

    if defn.type == "str":
        val = value or "—"
        if "trend" in defn.code:
            label, color = _TREND_LABELS.get(val, (val.replace("_", " ").title(), MUTED))
            return label, color
        if "volatility" in defn.code:
            parts = val.split("_") if "_" in val else [val]
            vol   = parts[0]
            dur   = "_".join(parts[1:]).replace("_", " ").title() if len(parts) > 1 else ""
            color = _VOL_REGIME_COLOR.get(vol, MUTED)
            label = f"{vol.title()} | {dur}" if dur else vol.title()
            return label, color
        return str(val), NEUTRAL

    num = value
    if num is None:
        return "—", MUTED

    scale = defn.scale or ""

    if scale == "%":
        color = "#4ade80" if num > 0 else "#f87171" if num < 0 else MUTED
        return f"{num:+.2f}%", color

    if scale == "% (negative)":
        color = "#f87171" if num < -15 else "#fb923c" if num < -5 else MUTED
        return f"{num:.2f}%", color

    if scale == "0 – 100":
        color = "#4ade80" if num <= 30 else "#f87171" if num >= 70 else "#f59e0b"
        return f"{num:.1f}", color

    if scale == "σ":
        color = "#4ade80" if num > 0 else "#f87171" if num < 0 else MUTED
        return f"{num:+.2f}σ", color

    if scale == "ratio":
        return f"{num:.2f}x", NEUTRAL

    if scale == "period":
        return str(int(num)), "#93c5fd"

    if scale == "currency":
        return f"{num:.4g}", NEUTRAL

    return f"{num:.4g}", NEUTRAL


def _indicator_card(defn: IndicatorDefinition, value) -> dbc.Col:
    text, color = _fmt(defn, value)
    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.Div(
                    defn.name,
                    className="text-muted mb-1",
                    style={"fontSize": "0.7rem", "textTransform": "uppercase",
                           "letterSpacing": "0.05em"},
                ),
                html.Div(
                    text,
                    style={"fontSize": "1.3rem", "fontWeight": "700", "color": color},
                ),
            ]),
            style=_CARD,
        ),
        xs=6, sm=4, md=3, lg=2, className="mb-2",
    )


def _section(category: str, items: list) -> html.Div:
    cards = [_indicator_card(defn, value) for defn, value in items]
    return html.Div([
        html.Span(category, style={"fontWeight": "600", "fontSize": "0.85rem"}),
        html.Hr(style={"borderColor": "#374151"}),
        dbc.Row(cards, className="g-2 mb-3"),
    ])


@callback(
    Output("indicators-panel-content", "children"),
    Input("analysis-asset-select", "value"),
    Input("analysis-tabs",         "active_tab"),
)
def load_indicators_panel(asset_id, active_tab):
    if active_tab != "tab-indicators" or not asset_id:
        return no_update

    s = get_session()
    aid = int(asset_id)

    defs = (
        s.query(IndicatorDefinition)
        .filter(
            IndicatorDefinition.keep_history.is_(True),
            IndicatorDefinition.category != "Fundamental",
        )
        .order_by(IndicatorDefinition.category, IndicatorDefinition.name)
        .all()
    )

    # Para cada indicador: leer el valor más reciente de su tabla ind_{code}
    by_category: dict[str, list] = {}
    max_date = None

    for defn in defs:
        try:
            t = get_ind_table(defn.code)
        except Exception:
            continue
        row = s.execute(
            sa.select(t.c.value, t.c.date)
            .where(t.c.asset_id == aid)
            .order_by(t.c.date.desc())
            .limit(1)
        ).fetchone()
        if row is None:
            continue
        value, snap_date = row[0], row[1]
        if max_date is None or snap_date > max_date:
            max_date = snap_date
        by_category.setdefault(defn.category, []).append((defn, value))

    if not by_category:
        return dbc.Alert(
            "No hay indicadores calculados para este activo. "
            "Ejecutá la actualización de precios para generarlos.",
            color="warning",
        )

    _s = {"fontWeight": "600", "fontSize": "0.85rem"}

    return html.Div([
        html.Div([
            html.Span("Indicadores técnicos", style=_s),
            html.Span(
                f" — datos al {max_date.strftime('%d/%m/%Y')}",
                className="text-muted ms-2",
                style={"fontSize": "0.75rem"},
            ),
        ], className="mb-3"),
        *[_section(cat, items) for cat, items in by_category.items()],
    ])
