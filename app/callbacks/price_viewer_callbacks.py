from dash import Input, Output, callback, no_update

from app.services.asset_service import get_assets
from app.services.price_service import get_prices_df, get_latest_prices_all

# Topes de la VISTA (no del cálculo): la DataTable manda todas las filas al
# navegador aunque pagine de a 50, así que sin tope el catálogo entero o una
# historia larga lo clavan.
_MAX_HISTORY_ROWS = 2000   # ≈ 8 años de rueda diaria
_MAX_LATEST_ROWS  = 1000


def _miles(n: int) -> str:
    """10000 → '10.000' (separador de miles rioplatense)."""
    return f"{n:,}".replace(",", ".")


_OHLC = ("open", "high", "low", "close")


def _redondear(filas: list[dict], campos=_OHLC) -> list[dict]:
    """Redondea los precios a 2 decimales dejándolos NUMÉRICOS.

    La tabla anterior formateaba en el cliente; la grilla muestra el valor tal
    cual, y un float de la base puede venir con una cola larga de decimales.
    Se redondea acá y no se convierte a texto: como string, ordenar la columna
    ordenaría alfabéticamente ("9" después de "10").
    """
    for f in filas:
        for c in campos:
            v = f.get(c)
            if isinstance(v, (int, float)):
                f[c] = round(v, 2)
    return filas


def _tail(rows: list, max_rows: int) -> tuple[list, bool]:
    """Últimas `max_rows` filas + si hubo corte. En una serie ordenada por
    fecha lo que interesa es la cola, no el arranque."""
    if len(rows) <= max_rows:
        return rows, False
    return rows[-max_rows:], True


def _history_info(total: int, first_date: str, last_date: str, shown: int) -> str:
    info = f"{_miles(total)} registros — {first_date} → {last_date}"
    if shown < total:
        info += f" (mostrando los últimos {_miles(shown)})"
    return info


@callback(
    Output("pv-asset-select", "options"),
    Input("pv-asset-select", "id"),
)
def load_pv_assets(_):
    assets = get_assets()
    return [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]


@callback(
    Output("pv-history-controls", "style"),
    Output("pv-history-table-container", "style"),
    Output("pv-latest-table-container", "style"),
    Output("pv-latest-table", "rowData"),
    Output("pv-result-info", "children"),
    Input("pv-mode", "value"),
)
def switch_mode(mode):
    if mode == "latest":
        # +1 para saber si hay más sin pagar un COUNT sobre todo el catálogo
        rows = _redondear(get_latest_prices_all(limit=_MAX_LATEST_ROWS + 1))
        if len(rows) > _MAX_LATEST_ROWS:
            rows = rows[:_MAX_LATEST_ROWS]
            info = (f"Mostrando los primeros {_miles(_MAX_LATEST_ROWS)} "
                    f"instrumentos por ticker (hay más).")
        else:
            info = f"{_miles(len(rows))} instrumentos con precio disponible."
        return (
            {"display": "none"},
            {"display": "none"},
            {"display": "block"},
            rows,
            info,
        )
    return (
        {"display": "block"},
        {"display": "block"},
        {"display": "none"},
        [],
        "",
    )


@callback(
    Output("pv-history-table", "rowData"),
    Output("pv-alert", "children"),
    Output("pv-alert", "is_open"),
    Output("pv-result-info", "children", allow_duplicate=True),
    Input("pv-asset-select", "value"),
    prevent_initial_call=True,
)
def query_history(asset_id):
    if not asset_id:
        return no_update, "Seleccioná un instrumento.", True, no_update

    df = get_prices_df(int(asset_id))
    if df.empty:
        return [], "No hay precios descargados para este instrumento.", True, ""

    rows = _redondear(df.assign(date=df["date"].astype(str)).to_dict("records"))
    info = _history_info(len(rows), rows[0]["date"], rows[-1]["date"],
                         min(len(rows), _MAX_HISTORY_ROWS))
    shown, _capped = _tail(rows, _MAX_HISTORY_ROWS)
    return shown, "", False, info
