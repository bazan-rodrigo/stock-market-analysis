from sqlalchemy import and_, func
from dash import Input, Output, callback, html, no_update
import dash_bootstrap_components as dbc

from app.database import get_session
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_value import IndicatorValue

_BG   = "#111827"
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


def _fmt_value(defn: IndicatorDefinition, iv: IndicatorValue) -> html.Span:
    """Formatea el valor con color semántico según tipo y escala."""

    _s = {"fontSize": "0.82rem", "fontWeight": "600"}

    if defn.type == "str":
        val = iv.value_str or "—"
        if "trend" in defn.code:
            label, color = _TREND_LABELS.get(val, (val.replace("_", " ").title(), "#9ca3af"))
            return html.Span(label, style={**_s, "color": color})
        if "volatility" in defn.code:
            parts = val.split("_") if "_" in val else [val]
            vol   = parts[0]
            dur   = "_".join(parts[1:]) if len(parts) > 1 else ""
            color = _VOL_REGIME_COLOR.get(vol, "#9ca3af")
            label = f"{vol.title()} | {dur.replace('_',' ').title()}" if dur else vol.title()
            return html.Span(label, style={**_s, "color": color})
        return html.Span(val, style={"fontSize": "0.82rem", "color": "#dee2e6"})

    num = iv.value_num
    if num is None:
        return html.Span("—", style={"color": "#4b5563", "fontSize": "0.82rem"})

    scale = defn.scale or ""

    if scale == "%":
        color = "#4ade80" if num > 0 else "#f87171" if num < 0 else "#9ca3af"
        return html.Span(f"{num:+.2f}%", style={**_s, "color": color})

    if scale == "% (negative)":
        color = "#f87171" if num < -15 else "#fb923c" if num < -5 else "#9ca3af"
        return html.Span(f"{num:.2f}%", style={**_s, "color": color})

    if scale == "0 – 100":
        color = "#4ade80" if num <= 30 else "#f87171" if num >= 70 else "#f59e0b"
        return html.Span(f"{num:.1f}", style={**_s, "color": color})

    if scale == "σ":
        color = "#4ade80" if num > 0 else "#f87171" if num < 0 else "#9ca3af"
        return html.Span(f"{num:+.2f}σ", style={**_s, "color": color})

    if scale == "ratio":
        return html.Span(f"{num:.2f}x", style={"fontSize": "0.82rem"})

    if scale == "period":
        return html.Span(str(int(num)), style={"fontSize": "0.82rem", "color": "#93c5fd"})

    if scale == "currency":
        return html.Span(f"{num:.4g}", style={**_s, "color": "#dee2e6"})

    return html.Span(f"{num:.4g}", style={"fontSize": "0.82rem"})


def _category_card(category: str, items: list) -> dbc.Col:
    rows = []
    for defn, iv in items:
        rows.append(html.Tr([
            html.Td(
                defn.name,
                style={"color": "#9ca3af", "fontSize": "0.78rem",
                       "paddingRight": "12px", "paddingBottom": "3px",
                       "whiteSpace": "nowrap"},
            ),
            html.Td(
                _fmt_value(defn, iv),
                style={"paddingBottom": "3px"},
            ),
            html.Td(
                iv.date.strftime("%d/%m/%y") if iv.date else "—",
                style={"color": "#4b5563", "fontSize": "0.7rem",
                       "paddingLeft": "10px", "paddingBottom": "3px",
                       "whiteSpace": "nowrap"},
            ),
        ]))

    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.Div(
                    category,
                    style={
                        "fontWeight": "600", "fontSize": "0.72rem",
                        "color": "#60a5fa", "textTransform": "uppercase",
                        "letterSpacing": "0.06em", "marginBottom": "6px",
                    },
                ),
                html.Table(
                    html.Tbody(rows),
                    style={"width": "100%", "borderCollapse": "collapse"},
                ),
            ], style={"padding": "10px 14px"}),
            style=_CARD,
        ),
        xs=12, md=6, xl=4, className="mb-3",
    )


@callback(
    Output("indicators-panel-content", "children"),
    Input("analysis-asset-select", "value"),
    Input("analysis-tabs",         "active_tab"),
)
def load_indicators_panel(asset_id, active_tab):
    if active_tab != "tab-indicators" or not asset_id:
        return no_update

    s = get_session()

    latest_sq = (
        s.query(
            IndicatorValue.indicator_id,
            func.max(IndicatorValue.date).label("max_date"),
        )
        .filter(IndicatorValue.asset_id == int(asset_id))
        .group_by(IndicatorValue.indicator_id)
        .subquery()
    )

    rows = (
        s.query(IndicatorDefinition, IndicatorValue)
        .join(IndicatorValue, IndicatorValue.indicator_id == IndicatorDefinition.id)
        .join(
            latest_sq,
            and_(
                IndicatorValue.indicator_id == latest_sq.c.indicator_id,
                IndicatorValue.date         == latest_sq.c.max_date,
                IndicatorValue.asset_id     == int(asset_id),
            ),
        )
        .order_by(IndicatorDefinition.category, IndicatorDefinition.name)
        .all()
    )

    if not rows:
        return dbc.Alert(
            "No hay indicadores calculados para este activo. "
            "Ejecutá la actualización de precios para generarlos.",
            color="warning",
        )

    by_category: dict[str, list] = {}
    for defn, iv in rows:
        by_category.setdefault(defn.category, []).append((defn, iv))

    cards = [_category_card(cat, items) for cat, items in by_category.items()]

    return dbc.Row(cards, className="g-3")
