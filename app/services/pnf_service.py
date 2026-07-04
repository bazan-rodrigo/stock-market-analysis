"""
Servicio de Punto y Figura (P&F).

Calcula las columnas X/O a partir de precios diarios según la configuración
persistida en pnf_config, y construye la figura Plotly del P&F clásico.

Conceptos:
  - caja (box): tamaño del escalón de precio. Cada columna se compone de cajas.
  - reversión: cantidad de cajas en contra necesarias para abrir columna opuesta.
  - fuente: 'close' usa solo cierres; 'hl' usa máximos para X y mínimos para O.
El eje horizontal NO es tiempo: cada columna dura lo que tarde en revertirse.
"""
import logging
import math

from app.database import get_session

logger = logging.getLogger(__name__)


def get_pnf_config():
    from app.models import PnfConfig
    s = get_session()
    cfg = s.query(PnfConfig).filter(PnfConfig.id == 1).first()
    if cfg is None:
        cfg = PnfConfig(id=1)
        s.add(cfg)
        s.commit()
    return cfg


def compute_box_size(df, cfg) -> float:
    """Tamaño de caja efectivo para un activo según el método configurado."""
    closes = df["close"].dropna()
    if closes.empty:
        return 0.0
    last_close = float(closes.iloc[-1])

    if cfg.box_method == "fixed":
        box = float(cfg.box_fixed)
    elif cfg.box_method == "percent":
        box = last_close * float(cfg.box_pct) / 100.0
    else:  # atr
        import pandas as pd
        period = int(cfg.box_atr_period)
        prev_close = df["close"].shift(1)
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"]  - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        atr_valid = atr.dropna()
        if atr_valid.empty:
            box = last_close * 0.01   # fallback: 1 %
        else:
            box = float(atr_valid.iloc[-1])

    return box if box > 0 else last_close * 0.01


def compute_pnf_columns(df, box: float, reversal: int, source: str = "close") -> list[dict]:
    """
    Construye las columnas P&F.

    Retorna [{"type": "X"|"O", "top": int, "bot": int, "start": date, "end": date}]
    donde top/bot son índices de caja (precio de la caja i = i * box).
    Regla por barra: primero se intenta extender la columna; si no extiende y el
    movimiento en contra alcanza `reversal` cajas, se abre la columna opuesta.
    """
    if box <= 0 or df.empty:
        return []

    use_hl = source == "hl"
    cols: list[dict] = []
    cur: dict | None = None
    ref_hi = ref_lo = None
    ref_date = None

    def _fl(p) -> int:
        return math.floor(float(p) / box)

    for row in df.itertuples(index=False):
        if row.close is None:
            continue
        hi = row.high if (use_hl and row.high is not None) else row.close
        lo = row.low  if (use_hl and row.low  is not None) else row.close
        hb, lb = _fl(hi), _fl(lo)

        if cur is None:
            # Sin columna todavía: esperar el primer movimiento de >= 1 caja
            if ref_hi is None:
                ref_hi, ref_lo, ref_date = hb, lb, row.date
                continue
            if hb > ref_hi:
                cur = {"type": "X", "top": hb, "bot": ref_lo, "start": ref_date, "end": row.date}
            elif lb < ref_lo:
                cur = {"type": "O", "top": ref_hi, "bot": lb, "start": ref_date, "end": row.date}
            else:
                ref_hi, ref_lo = max(ref_hi, hb), min(ref_lo, lb)
            continue

        if cur["type"] == "X":
            if hb > cur["top"]:                      # extender
                cur["top"], cur["end"] = hb, row.date
            elif cur["top"] - lb >= reversal:        # revertir a O
                cols.append(cur)
                cur = {"type": "O", "top": cur["top"] - 1, "bot": lb,
                       "start": row.date, "end": row.date}
        else:
            if lb < cur["bot"]:
                cur["bot"], cur["end"] = lb, row.date
            elif hb - cur["bot"] >= reversal:
                cols.append(cur)
                cur = {"type": "X", "top": hb, "bot": cur["bot"] + 1,
                       "start": row.date, "end": row.date}

    if cur is not None:
        cols.append(cur)
    return cols


def build_pnf_figure(df, cfg=None):
    """Figura Plotly del P&F clásico: X verdes y O rojas en grilla de cajas."""
    import plotly.graph_objects as go
    from app.components.ui_constants import (
        COLOR_NEGATIVE, COLOR_POSITIVE, PLOTLY_AXIS, PLOTLY_DARK,
    )

    if cfg is None:
        cfg = get_pnf_config()
    box  = compute_box_size(df, cfg)
    cols = compute_pnf_columns(df, box, int(cfg.reversal), cfg.source)

    fig = go.Figure()
    if not cols:
        fig.add_annotation(text="Sin datos suficientes para el P&F",
                           showarrow=False, font=dict(color="#9ca3af"))
        fig.update_layout(**PLOTLY_DARK)
        return fig

    # Precisión de display según magnitud de la caja
    dec = 2 if box >= 0.01 else 4

    def _pts(kind):
        xs, ys, texts = [], [], []
        for i, c in enumerate(cols):
            if c["type"] != kind:
                continue
            rng = f"{c['start']} → {c['end']}"
            for b in range(c["bot"], c["top"] + 1):
                xs.append(i)
                ys.append((b + 0.5) * box)   # centro de la caja
                texts.append(f"Caja {b * box:.{dec}f} – {(b + 1) * box:.{dec}f}"
                             f"<br>Columna {kind}: {rng}")
        return xs, ys, texts

    for kind, symbol, color in (("X", "X", COLOR_POSITIVE), ("O", "O", COLOR_NEGATIVE)):
        xs, ys, texts = _pts(kind)
        if not xs:
            continue
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="text", text=[symbol] * len(xs),
            textfont=dict(color=color, size=13, family="monospace"),
            hovertext=texts, hoverinfo="text", name=kind,
        ))

    # Etiquetas del eje X: fecha de inicio de columna, cada ~n columnas
    step = max(1, len(cols) // 12)
    tickvals = list(range(0, len(cols), step))
    ticktext = [str(cols[i]["start"]) for i in tickvals]

    _method_label = {"percent": f"{cfg.box_pct}%", "atr": f"ATR{cfg.box_atr_period}",
                     "fixed": "fijo"}
    fig.update_layout(
        **PLOTLY_DARK,
        title=dict(
            text=(f"Punto y Figura — caja {box:.{dec}f} "
                  f"({_method_label.get(cfg.box_method, cfg.box_method)})"
                  f" · reversión {cfg.reversal} · fuente {cfg.source}"),
            font=dict(size=13),
        ),
        showlegend=False,
        margin=dict(l=10, r=60, t=40, b=30),
        xaxis=dict(**PLOTLY_AXIS, tickvals=tickvals, ticktext=ticktext,
                   tickfont=dict(size=10), title=""),
        yaxis=dict(**PLOTLY_AXIS, side="right", tickformat=f".{dec}f"),
    )
    return fig
