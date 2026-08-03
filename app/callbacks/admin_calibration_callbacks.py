"""Callbacks de la pantalla de Calibración.

Toda la cuenta vive en `indicator_stats_service` — el mismo que responde a la
IA, así que las dos caras dan el mismo número por construcción. Acá solo se
arman los gráficos y las tablas.
"""
import logging

import plotly.graph_objects as go
from dash import Input, Output, State, callback, no_update

from app.components.ui_constants import (
    BG_CHART, COLOR_INFO, COLOR_NEGATIVE, COLOR_NEUTRAL, COLOR_POSITIVE,
    COLOR_RANGE, TEXT_MUTED,
)

logger = logging.getLogger(__name__)


def _parse_fechas(texto: str | None) -> list:
    """Texto libre → lista de fechas. Vacío = [None] (la fecha por defecto del
    pipeline). Se aceptan comas y saltos de línea porque pegar una columna de
    fechas es lo natural."""
    if not texto or not texto.strip():
        return [None]
    crudas = [t.strip() for t in texto.replace("\n", ",").split(",")]
    return [c for c in crudas if c] or [None]


def _senal_de(code: str):
    """La señal definida sobre ese indicador, o None.

    El catálogo es curado y tiene UNA señal por indicador, así que buscarla por
    indicador alcanza. Si hubiera varias se toma la primera y se avisa.
    """
    from app.database import get_session
    from app.models import SignalDefinition

    s = get_session()
    filas = (s.query(SignalDefinition)
             .filter(SignalDefinition.indicator_key == code)
             .order_by(SignalDefinition.key).all())
    return filas[0] if filas else None


def _fig_vacia(mensaje: str):
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=BG_CHART, plot_bgcolor=BG_CHART,
        margin=dict(l=10, r=10, t=30, b=10),
        annotations=[dict(text=mensaje, showarrow=False,
                          font=dict(color=TEXT_MUTED, size=12))],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def _base(fig, titulo: str):
    fig.update_layout(
        paper_bgcolor=BG_CHART, plot_bgcolor=BG_CHART,
        margin=dict(l=45, r=45, t=34, b=34),
        title=dict(text=titulo, font=dict(size=12, color=TEXT_MUTED)),
        showlegend=False,
        font=dict(size=10, color=TEXT_MUTED),
    )
    fig.update_xaxes(gridcolor="#2b3444", zeroline=False)
    fig.update_yaxes(gridcolor="#2b3444", zeroline=False)
    return fig


def _fig_indicador(datos, vmin, vmax):
    """Histograma del indicador + la curva de la señal en el mismo eje x.

    Las dos cosas en el mismo eje es el punto entero de la pantalla: se ve de
    una si los cortes caen donde hay activos o donde no hay nadie.
    """
    if datos.get("type") == "str":
        cats = (datos.get("fechas") or [{}])[0].get("categorias") or []
        if not cats:
            return _fig_vacia("sin datos para esa fecha")
        fig = go.Figure()
        fig.add_bar(x=[c["valor"] for c in cats], y=[c["n"] for c in cats],
                    marker_color=COLOR_INFO,
                    hovertemplate="%{x}: %{y} activos<extra></extra>")
        return _base(fig, "Activos por categoría")

    h = datos.get("histograma") or {}
    bordes, conteos = h.get("bins") or [], h.get("conteos") or []
    if not conteos:
        return _fig_vacia("sin datos para esa fecha")

    centros = [(bordes[i] + bordes[i + 1]) / 2 for i in range(len(conteos))]
    ancho = (bordes[1] - bordes[0]) if len(bordes) > 1 else 1

    fig = go.Figure()
    fig.add_bar(x=centros, y=conteos, width=ancho, marker_color=COLOR_NEUTRAL,
                opacity=0.55, name="activos",
                hovertemplate="valor %{x:.4g}<br>%{y} activos<extra></extra>")

    # La curva de la señal sobre un eje derecho de −100 a 100.
    if vmin is not None and vmax is not None and vmin != vmax:
        pad = abs(vmax - vmin) * 0.35
        lo_x, hi_x = min(vmin, vmax) - pad, max(vmin, vmax) + pad
        xs = [lo_x, vmin, vmax, hi_x]
        ys = [-100, -100, 100, 100]
        fig.add_scatter(x=xs, y=ys, mode="lines", yaxis="y2",
                        line=dict(color=COLOR_RANGE, width=2), name="score",
                        hovertemplate="valor %{x:.4g} → score %{y:.0f}<extra></extra>")
        for x, color in ((vmin, COLOR_NEGATIVE), (vmax, COLOR_POSITIVE)):
            fig.add_vline(x=x, line_width=1, line_dash="dot", line_color=color)

    fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[-105, 105],
                                  showgrid=False, tickfont=dict(size=9)))
    sufijo = ""
    if h.get("fuera_izq") or h.get("fuera_der"):
        sufijo = (f"  ·  fuera del dibujo: {h.get('fuera_izq', 0)} abajo / "
                  f"{h.get('fuera_der', 0)} arriba")
    return _base(fig, f"Distribución del indicador{sufijo}")


def _fig_scores(datos):
    """Histograma del PUNTAJE. Los picos en ±100 son la saturación."""
    sc = datos.get("scores") or {}
    h = sc.get("histograma") or {}
    bordes, conteos = h.get("bins") or [], h.get("conteos") or []
    if not conteos:
        return _fig_vacia("elegí un indicador que tenga señal definida")

    centros = [(bordes[i] + bordes[i + 1]) / 2 for i in range(len(conteos))]
    ancho = (bordes[1] - bordes[0]) if len(bordes) > 1 else 1
    colores = [COLOR_POSITIVE if c > 0 else COLOR_NEGATIVE if c < 0
               else COLOR_NEUTRAL for c in centros]
    fig = go.Figure()
    fig.add_bar(x=centros, y=conteos, width=ancho, marker_color=colores,
                hovertemplate="score %{x:.0f}<br>%{y} activos<extra></extra>")
    fig.update_xaxes(range=[-105, 105])
    return _base(fig, "Distribución del puntaje resultante")


def _filas_fechas(datos) -> list[dict]:
    filas = []
    for f in datos.get("fechas") or []:
        p = f.get("percentiles") or {}
        sat = f.get("escala_propuesta") or {}
        filas.append({
            "fecha": f.get("fecha_efectiva"),
            "n": f.get("n"),
            "cobertura": f.get("cobertura_pct"),
            **{k: p.get(k) for k in ("p5", "p25", "p50", "p75", "p95")},
            "satura": sat.get("pct_saturado"),
            "sat_abajo": sat.get("pct_debajo_del_rango"),
            "sat_arriba": sat.get("pct_encima_del_rango"),
        })
    return filas


def _filas_grupos(datos) -> list[dict]:
    filas = []
    for g in datos.get("grupos") or []:
        p = g.get("percentiles") or {}
        sat = g.get("escala_propuesta") or {}
        filas.append({
            "grupo": g.get("grupo"), "activos": g.get("activos"),
            "n": g.get("n"), "cobertura": g.get("cobertura_pct"),
            **{k: p.get(k) for k in ("p25", "p50", "p75")},
            "satura": sat.get("pct_saturado"),
        })
    return filas


def _resumen(datos, senal) -> str:
    primera = (datos.get("fechas") or [{}])[0]
    partes = [f"{datos.get('name')} ({datos.get('code')})"]
    if senal is not None:
        partes.append(f"señal «{senal.name}» · fórmula {senal.formula_type}")
    else:
        partes.append("sin señal definida sobre este indicador")
    partes.append(f"{primera.get('n', 0)} de {datos.get('total_activos', 0)} "
                  f"activos con dato ({primera.get('cobertura_pct', 0)}%)")
    sc = datos.get("scores") or {}
    if sc.get("n"):
        partes.append(f"puntajes distintos: {sc.get('puntajes_distintos')} "
                      f"({sc.get('pct_distintos')}%)")
        if sc.get("sin_puntaje"):
            partes.append(f"{sc['sin_puntaje']} activos que la fórmula NO puntúa")
    return "  ·  ".join(str(p) for p in partes)


@callback(
    Output("cal-min", "value"),
    Output("cal-max", "value"),
    Input("cal-btn-cargar", "n_clicks"),
    State("cal-indicador", "value"),
    prevent_initial_call=True,
)
def cargar_escala(_n, code):
    """Trae el min/max de la señal que ya usa ese indicador, para partir de lo
    que hay en vez de escribirlo de nuevo."""
    import json

    if not code:
        return no_update, no_update
    senal = _senal_de(code)
    if senal is None or senal.formula_type != "range":
        return None, None
    try:
        params = json.loads(senal.params or "{}")
    except (ValueError, TypeError):
        return None, None
    return params.get("min"), params.get("max")


@callback(
    Output("cal-graf-indicador", "figure"),
    Output("cal-graf-scores", "figure"),
    Output("cal-tabla-fechas", "rowData"),
    Output("cal-tabla-grupos", "rowData"),
    Output("cal-bloque-grupos", "style"),
    Output("cal-resumen", "children"),
    Output("cal-aviso", "children"),
    Output("cal-aviso", "is_open"),
    Input("cal-btn", "n_clicks"),
    State("cal-indicador", "value"),
    State("cal-fechas", "value"),
    State("cal-agrupar", "value"),
    State("cal-min", "value"),
    State("cal-max", "value"),
    prevent_initial_call=True,
)
def analizar(_n, code, fechas_txt, agrupar, vmin, vmax):
    from app.services import indicator_stats_service as stats

    oculto = {"display": "none"}
    if not code:
        return (_fig_vacia("elegí un indicador"), _fig_vacia(""), [], [],
                oculto, "", "Elegí un indicador.", True)

    escala = None
    if vmin is not None and vmax is not None:
        escala = {"min": vmin, "max": vmax}

    senal = _senal_de(code)
    try:
        datos = stats.analisis_indicador(
            code, fechas=_parse_fechas(fechas_txt), escala=escala, por=agrupar,
            formula_type=(senal.formula_type if senal else None),
            params=(senal.params if senal else None))
    except ValueError as exc:
        return (_fig_vacia("—"), _fig_vacia("—"), [], [], oculto, "",
                str(exc), True)
    except Exception:
        logger.exception("calibración: falló el análisis de %s", code)
        return (_fig_vacia("—"), _fig_vacia("—"), [], [], oculto, "",
                "No se pudo calcular la distribución. Revisá el log.", True)

    avisos = []
    if not datos.get("keep_history"):
        avisos.append("Este indicador no guarda historia: solo existe el valor "
                      "vigente, así que la fecha no aplica y no sirve para "
                      "backtestear.")
    sc = datos.get("scores") or {}
    if sc.get("n") and (sc.get("pct_en_tope", 0) + sc.get("pct_en_piso", 0)) > 20:
        avisos.append(
            f"La señal deja {sc['pct_en_tope'] + sc['pct_en_piso']:.1f}% de los "
            f"activos pegados en ±100: ahí deja de ordenar.")
    if sc.get("sin_puntaje"):
        avisos.append(
            f"{sc['sin_puntaje']} activos quedan SIN puntaje. Un activo sin "
            f"puntaje no se castiga: se saltea y los pesos se reparten entre "
            f"las demás señales, así que sube en el ranking por no tener dato.")

    estilo_grupos = {} if datos.get("grupos") else oculto
    return (_fig_indicador(datos, vmin, vmax), _fig_scores(datos),
            _filas_fechas(datos), _filas_grupos(datos), estilo_grupos,
            _resumen(datos, senal), " ".join(avisos), bool(avisos))


@callback(
    Output("url", "href", allow_duplicate=True),
    Input("cal-btn-editor", "n_clicks"),
    State("cal-indicador", "value"),
    State("cal-min", "value"),
    State("cal-max", "value"),
    prevent_initial_call=True,
)
def llevar_al_editor(_n, code, vmin, vmax):
    """Abre el editor de Señales con esta escala cargada.

    La pantalla no escribe: que la definición se guarde en un solo lugar es lo
    que evita que dos caminos de escritura se separen. Esto es solo el puente.
    """
    if not code:
        return no_update
    senal = _senal_de(code)
    if senal is None:
        return no_update
    partes = [f"editar={senal.key}"]
    if vmin is not None:
        partes.append(f"min={vmin}")
    if vmax is not None:
        partes.append(f"max={vmax}")
    return "/admin/signals?" + "&".join(partes)
