from datetime import date

import pandas as pd

from app.database import get_session
from app.models import Asset, MarketEvent, Price


def get_all_assets_options() -> list[dict]:
    s = get_session()
    assets = s.query(Asset).order_by(Asset.ticker).all()
    return [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]


def get_asset_label(asset_id: int) -> str:
    s = get_session()
    a = s.query(Asset).filter(Asset.id == asset_id).first()
    return f"{a.ticker} — {a.name}" if a else str(asset_id)


def get_paired_prices(asset1_id: int, asset2_id: int,
                      date_from=None, date_to=None) -> list[dict]:
    """Cierres de ambos activos en sus fechas en común, opcionalmente
    acotados al rango.

    El rango es opt-in: sin fechas devuelve la historia completa (es lo que
    espera /scatter, que no tiene selector de fechas). Análisis de Pares sí
    las pasa — antes no, y su solapa Correlación ignoraba en silencio el
    rango que el usuario había elegido para las otras dos solapas.
    """
    s = get_session()
    q1 = s.query(Price.date, Price.close).filter(Price.asset_id == asset1_id)
    q2 = s.query(Price.date, Price.close).filter(Price.asset_id == asset2_id)
    if date_from:
        q1 = q1.filter(Price.date >= date_from)
        q2 = q2.filter(Price.date >= date_from)
    if date_to:
        q1 = q1.filter(Price.date <= date_to)
        q2 = q2.filter(Price.date <= date_to)

    df1 = pd.DataFrame(q1.all(), columns=["date", "p1"]).set_index("date")
    df2 = pd.DataFrame(q2.all(), columns=["date", "p2"]).set_index("date")

    df = df1.join(df2, how="inner").dropna().sort_index()
    return [
        {"date": str(row.Index), "p1": float(row.p1), "p2": float(row.p2)}
        for row in df.itertuples()
    ]


def returns_correlation(xs: list[float], ys: list[float]) -> float | None:
    """Correlación de Pearson sobre las VARIACIONES, no sobre los niveles.

    Correlacionar precios mide recorrido compartido: dos activos que
    simplemente subieron con el mercado dan coeficientes altísimos aunque sus
    movimientos diarios no tengan nada que ver. Sobre retornos se mide lo que
    la palabra "correlación" promete — si se mueven juntos.

    Devuelve None si no hay suficientes puntos o si alguna serie es constante
    (correlación indefinida: numpy devolvería nan con un warning).
    """
    import numpy as np

    if not xs or not ys or len(xs) != len(ys) or len(xs) < 3:
        return None
    a = np.asarray(xs, dtype=float)
    b = np.asarray(ys, dtype=float)
    # Retorno simple entre cierres consecutivos; se descartan los pasos con
    # precio previo cero o no positivo (un cero en la serie daría inf).
    validos = (a[:-1] > 0) & (b[:-1] > 0)
    if validos.sum() < 3:
        return None
    ra = (a[1:] / a[:-1] - 1.0)[validos]
    rb = (b[1:] / b[:-1] - 1.0)[validos]
    if ra.std() == 0 or rb.std() == 0:
        return None
    corr = float(np.corrcoef(ra, rb)[0, 1])
    return None if corr != corr else corr        # descarta nan


def get_events_with_coords(asset1_id: int, asset2_id: int,
                           pairs: list[dict]) -> list[dict]:
    """
    Retorna eventos relevantes (global o de alguno de los dos activos)
    con las coordenadas (p1, p2) del día más cercano al centro del evento.
    """
    if not pairs:
        return []

    s = get_session()
    events = s.query(MarketEvent).filter(
        (MarketEvent.scope == "global") |
        (
            (MarketEvent.scope == "asset") &
            MarketEvent.asset_id.in_([asset1_id, asset2_id])
        )
    ).all()

    date_map = {p["date"]: p for p in pairs}
    all_dates = [p["date"] for p in pairs]

    result = []
    for ev in events:
        try:
            mid = ev.start_date + (ev.end_date - ev.start_date) / 2
            mid_str = str(mid)
        except Exception:
            continue

        if mid_str in date_map:
            pair = date_map[mid_str]
        else:
            closest = min(all_dates,
                          key=lambda d: abs((date.fromisoformat(d) - mid).days))
            pair = date_map[closest]

        result.append({
            "name":       ev.name,
            "start_date": str(ev.start_date),
            "end_date":   str(ev.end_date),
            "color":      ev.color or "#ff9800",
            "p1":         pair["p1"],
            "p2":         pair["p2"],
        })

    return result
