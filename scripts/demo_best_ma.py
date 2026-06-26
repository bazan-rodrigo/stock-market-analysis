"""
Demo visual: algoritmo best_sma / best_ema — comparación v1 vs v2.
Genera datos sintéticos y muestra cómo cada algoritmo elige el período ganador.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

np.random.seed(42)

# ─── Datos sintéticos ────────────────────────────────────────────────────────
N = 300
t = np.arange(N)

# Precio que respeta bien la SMA20: oscila en torno a ella sin cruzarla mucho
trend = 100 + 0.05 * t
noise_small = np.random.normal(0, 0.8, N).cumsum()
price_respects_20 = trend + noise_small

# Construimos close/high/low
close = pd.Series(price_respects_20)
high  = close + np.abs(np.random.normal(0, 0.5, N))
low   = close - np.abs(np.random.normal(0, 0.5, N))

_MA_PERIODS = [10, 20, 50, 100, 200]


# ─── Algoritmo v1 ─────────────────────────────────────────────────────────────
def find_best_ma_v1(close, high, low, kind="sma"):
    best_period, best_score = None, -1
    scores = {}
    touches = {}  # índices de rebotes detectados
    for period in _MA_PERIODS:
        if len(close) < period * 2:
            continue
        ma = close.rolling(period).mean() if kind == "sma" \
             else close.ewm(span=period, adjust=False).mean()
        score = 0
        idxs = []
        for i in range(period, len(close) - 1):
            ma_val = ma.iloc[i]
            if pd.isna(ma_val):
                continue
            if low.iloc[i] <= ma_val <= high.iloc[i]:
                prev_c = close.iloc[i - 1]
                curr_c = close.iloc[i]
                if (prev_c >= ma_val and curr_c >= ma_val) or \
                   (prev_c <= ma_val and curr_c <= ma_val):
                    score += 1
                    idxs.append(i)
        scores[period] = score
        touches[period] = idxs
        if score > best_score:
            best_score  = score
            best_period = period
    return best_period, scores, touches


# ─── Algoritmo v2 ─────────────────────────────────────────────────────────────
def find_best_ma_v2(close, high, low, kind="sma"):
    best_period, best_score = None, -1.0
    scores = {}
    crosses = {}  # índices de cruces detectados
    for period in _MA_PERIODS:
        if len(close) < period * 2:
            continue
        ma = close.rolling(period).mean() if kind == "sma" \
             else close.ewm(span=period, adjust=False).mean()
        above = (close >= ma).dropna()
        if len(above) < 2:
            continue
        cross_mask = (above != above.shift()).iloc[1:]
        n_crosses = int(cross_mask.sum())
        if n_crosses == 0:
            continue
        score = (len(above) / n_crosses) / period
        scores[period] = round(score, 4)
        crosses[period] = list(cross_mask[cross_mask].index)
        if score > best_score:
            best_score  = score
            best_period = period
    return best_period, scores, crosses


# ─── Cálculo ──────────────────────────────────────────────────────────────────
best_v1, scores_v1, touches_v1 = find_best_ma_v1(close, high, low)
best_v2, scores_v2, crosses_v2 = find_best_ma_v2(close, high, low)

mas = {p: close.rolling(p).mean() for p in _MA_PERIODS}

COLORS = {10: "#e74c3c", 20: "#e67e22", 50: "#2ecc71", 100: "#3498db", 200: "#9b59b6"}
WINDOW = slice(50, 300)  # ventana visible en el gráfico

# ─── Figura ───────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(18, 14))
fig.patch.set_facecolor("#0d1117")
gs = GridSpec(3, 2, figure=fig, hspace=0.55, wspace=0.35,
              top=0.92, bottom=0.07, left=0.07, right=0.97)

ax_v1  = fig.add_subplot(gs[0, :])   # gráfico principal v1 (ancho completo)
ax_v2  = fig.add_subplot(gs[1, :])   # gráfico principal v2
ax_sv1 = fig.add_subplot(gs[2, 0])   # barras score v1
ax_sv2 = fig.add_subplot(gs[2, 1])   # barras score v2

for ax in [ax_v1, ax_v2, ax_sv1, ax_sv2]:
    ax.set_facecolor("#161b22")
    ax.tick_params(colors="#adbac7")
    for spine in ax.spines.values():
        spine.set_edgecolor("#30363d")

idx = np.arange(N)[WINDOW]

# ── Panel V1 ──────────────────────────────────────────────────────────────────
ax_v1.set_title("Algoritmo V1 — Rebotes con contacto físico\n"
                "La MA ganadora es la que acumula más velas que la tocan (high≥MA≥low) y el cierre NO cruza",
                color="#cdd9e5", fontsize=10, loc="left", pad=8)

# precio (candlestick simplificado: línea + sombras)
ax_v1.plot(idx, close[WINDOW], color="#adbac7", lw=0.8, zorder=2, label="Close")
ax_v1.vlines(idx, low[WINDOW], high[WINDOW], color="#4d5566", lw=0.5, zorder=1)

# todas las MAs tenues
for p, ma in mas.items():
    alpha = 0.9 if p == best_v1 else 0.2
    lw    = 2.2 if p == best_v1 else 0.8
    ax_v1.plot(idx, ma[WINDOW], color=COLORS[p], lw=lw, alpha=alpha,
               label=f"SMA{p}" + (" ← GANADORA" if p == best_v1 else ""),
               zorder=3 if p == best_v1 else 2)

# marcar rebotes del período ganador
touch_idxs = [i for i in touches_v1.get(best_v1, []) if i in idx]
if touch_idxs:
    ax_v1.scatter(touch_idxs, close.iloc[touch_idxs],
                  marker="^", color="#f1c40f", s=35, zorder=5,
                  label=f"Rebote detectado ({len(touch_idxs)} eventos)")

ax_v1.legend(loc="upper left", fontsize=8, facecolor="#1c2128", labelcolor="#cdd9e5",
             edgecolor="#30363d", ncol=4)
ax_v1.set_ylabel("Precio", color="#adbac7", fontsize=9)

# ── Panel V2 ──────────────────────────────────────────────────────────────────
ax_v2.set_title("Algoritmo V2 — Ratio cruces / período  (actual)\n"
                "La MA ganadora es la que el precio cruza menos veces relativo a su longitud  "
                "→  score = (barras / cruces) / period",
                color="#cdd9e5", fontsize=10, loc="left", pad=8)

ax_v2.plot(idx, close[WINDOW], color="#adbac7", lw=0.8, zorder=2, label="Close")
ax_v2.vlines(idx, low[WINDOW], high[WINDOW], color="#4d5566", lw=0.5, zorder=1)

for p, ma in mas.items():
    alpha = 0.9 if p == best_v2 else 0.2
    lw    = 2.2 if p == best_v2 else 0.8
    ax_v2.plot(idx, ma[WINDOW], color=COLORS[p], lw=lw, alpha=alpha,
               label=f"SMA{p}" + (" ← GANADORA" if p == best_v2 else ""),
               zorder=3 if p == best_v2 else 2)

# sombrear zonas donde precio está por encima de la MA ganadora
best_ma_v2 = mas[best_v2][WINDOW]
above_mask = close[WINDOW].values >= best_ma_v2.values
x_arr = np.array(idx)
ax_v2.fill_between(x_arr, low[WINDOW].values, high[WINDOW].values,
                   where=above_mask,  alpha=0.06, color="#2ecc71", zorder=0)
ax_v2.fill_between(x_arr, low[WINDOW].values, high[WINDOW].values,
                   where=~above_mask, alpha=0.06, color="#e74c3c", zorder=0)

# marcar cruces del período ganador
cross_idxs = [i for i in crosses_v2.get(best_v2, []) if i in idx]
if cross_idxs:
    ax_v2.scatter(cross_idxs, close.iloc[cross_idxs],
                  marker="x", color="#e74c3c", s=55, lw=1.8, zorder=5,
                  label=f"Cruce detectado ({len(cross_idxs)} cruces en ventana)")

green_patch = mpatches.Patch(color="#2ecc71", alpha=0.3, label="Precio sobre MA (estable)")
red_patch   = mpatches.Patch(color="#e74c3c", alpha=0.3, label="Precio bajo MA (estable)")
handles, labels = ax_v2.get_legend_handles_labels()
ax_v2.legend(handles=handles + [green_patch, red_patch],
             loc="upper left", fontsize=8, facecolor="#1c2128",
             labelcolor="#cdd9e5", edgecolor="#30363d", ncol=4)
ax_v2.set_ylabel("Precio", color="#adbac7", fontsize=9)

# ── Barras score V1 ───────────────────────────────────────────────────────────
ax_sv1.set_title("Scores V1 (conteo absoluto de rebotes)", color="#cdd9e5", fontsize=9)
periods  = [p for p in _MA_PERIODS if p in scores_v1]
sv1_vals = [scores_v1[p] for p in periods]
bar_colors = [COLORS[p] if p == best_v1 else "#444d56" for p in periods]
bars = ax_sv1.bar([f"SMA{p}" for p in periods], sv1_vals, color=bar_colors, edgecolor="#30363d")
for bar, val in zip(bars, sv1_vals):
    ax_sv1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                str(val), ha="center", va="bottom", color="#cdd9e5", fontsize=8)
ax_sv1.set_ylabel("# rebotes", color="#adbac7", fontsize=9)
ax_sv1.annotate(f"Ganadora: SMA{best_v1}", xy=(0.98, 0.95), xycoords="axes fraction",
                ha="right", va="top", color=COLORS[best_v1], fontsize=9, fontweight="bold")

# ── Barras score V2 ───────────────────────────────────────────────────────────
ax_sv2.set_title("Scores V2  score = (barras/cruces)/period", color="#cdd9e5", fontsize=9)
periods  = [p for p in _MA_PERIODS if p in scores_v2]
sv2_vals = [scores_v2[p] for p in periods]
bar_colors2 = [COLORS[p] if p == best_v2 else "#444d56" for p in periods]
bars2 = ax_sv2.bar([f"SMA{p}" for p in periods], sv2_vals, color=bar_colors2, edgecolor="#30363d")
for bar, val in zip(bars2, sv2_vals):
    ax_sv2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.0002,
                f"{val:.3f}", ha="center", va="bottom", color="#cdd9e5", fontsize=8)
ax_sv2.set_ylabel("score", color="#adbac7", fontsize=9)
ax_sv2.annotate(f"Ganadora: SMA{best_v2}", xy=(0.98, 0.95), xycoords="axes fraction",
                ha="right", va="top", color=COLORS[best_v2], fontsize=9, fontweight="bold")

fig.suptitle("Best MA — Comparación algoritmo V1 vs V2\nDatos sintéticos · SMA · Timeframe diario",
             color="#cdd9e5", fontsize=13, fontweight="bold")

out = "scripts/demo_best_ma.png"
plt.savefig(out, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Guardado: {out}")
print(f"\nV1 → ganadora SMA{best_v1}  |  scores: {scores_v1}")
print(f"V2 → ganadora SMA{best_v2}  |  scores: {scores_v2}")
plt.show()
