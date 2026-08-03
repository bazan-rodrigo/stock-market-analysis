"""Carteras: ver las que existen y simular una hipotética sin crearla.

Es el terreno más barato de todo lo que la IA puede tocar. Una cartera curada
son filas planas —`portfolio` + `portfolio_member`—, sin DDL, sin backfill y
con borrado limpio por CASCADE; nada que ver con una estrategia, que son dos
`ALTER TABLE` sobre una tabla ancha compartida más una corrida en producción.

Aun así la IA **no crea ninguna**: simula a partir de una lista de tickers y
pesos. Probar diez combinaciones dejaría nueve carteras que después hay que
borrar a mano, y la única que importa es la que el usuario decida guardar.

Sobre el sobreajuste: acá el riesgo es mayor que en el backtest de señales,
porque optimizar pesos contra una curva histórica es literalmente ajustar
parámetros a datos pasados. Por eso toda simulación devuelve además los KPIs
**por tramo**: un Sharpe alto que sale de un solo año no es una cartera buena,
es un año bueno.
"""
from app.ai import prudencia
from app.ai.caller import AiCaller
from app.ai.registry import limite, tool

_TOPE_CARTERAS = 100
_TOPE_MIEMBROS = 50
_TRAMOS = 4

_KPIS = ("total_return", "cagr", "volatility", "sharpe", "sortino",
         "max_drawdown")


def _cartera_visible(caller: AiCaller, portfolio_id: int):
    """La cartera, o ValueError. Mismo mensaje exista o no, para que el error
    no sirva de oráculo para enumerar ids."""
    from app.services.portfolio_service import get_portfolio
    from app.services.visibility import can_view

    user_id, is_admin = caller.viewer()
    p = get_portfolio(_sesion(), int(portfolio_id))
    if p is None or not can_view(p.owner_id, p.is_public, user_id, is_admin):
        raise ValueError(
            f"no existe una cartera con id={portfolio_id} que puedas ver. "
            f"Usá list_portfolios para ver las disponibles.")
    return p


def _sesion():
    from app.database import get_session

    return get_session()


def _solo_kpis(datos: dict) -> dict:
    return {k: (round(v, 6) if isinstance(v, (int, float)) else v)
            for k, v in datos.items() if k in _KPIS}


def _por_tramos(datos: dict, n: int = _TRAMOS) -> list | None:
    """Los mismos KPIs recalculados sobre tramos consecutivos de la curva.

    Optimizar pesos contra una curva histórica es ajustar parámetros a datos
    pasados: el resultado global siempre se ve bien. Partirlo muestra si la
    cartera se sostuvo o si vivió de un tramo.
    """
    from app.services import portfolio_metrics as pm

    fechas, equity = datos.get("dates") or [], datos.get("equity") or []
    if len(fechas) < n * 2:
        return None

    corte = len(fechas) // n
    salida = []
    for i in range(n):
        lo = i * corte
        hi = (i + 1) * corte if i < n - 1 else len(fechas)
        eq, fe = equity[lo:hi], fechas[lo:hi]
        if len(eq) < 2:
            continue
        # Reescalado a 1 para que cada tramo se lea por sí mismo y no arrastre
        # el nivel acumulado del anterior.
        base = eq[0] or 1.0
        m = pm.summary([v / base for v in eq], dates=fe)
        salida.append({"desde": str(fe[0]), "hasta": str(fe[-1]),
                       **_solo_kpis(m)})
    return salida


@tool(
    name="list_portfolios",
    familia="carteras",
    description=(
        "Las carteras que podés ver (públicas más las tuyas; un administrador "
        "las ve todas). Hay dos tipos: 'real' (con registro de operaciones, su "
        "posición se deriva de ahí) y 'seg' (teórica o de seguimiento, sin "
        "plata real)."
    ),
    input_schema={
        "type": "object",
        "properties": {"limit": {"type": "integer", "minimum": 1}},
        "additionalProperties": False,
    },
    max_rows=_TOPE_CARTERAS,
)
def list_portfolios(caller: AiCaller, limit: int | None = None) -> dict:
    from app.services import portfolio_service

    user_id, is_admin = caller.viewer()
    tope = limite(limit, _TOPE_CARTERAS)
    filas = portfolio_service.list_portfolios(_sesion(), user_id, is_admin)
    return {
        "total": len(filas),
        "devueltas": min(len(filas), tope),
        "portfolios": [
            {"id": p.id, "name": p.name, "tipo": p.ptype,
             "publica": bool(p.is_public),
             "moneda_base": getattr(p, "base_currency", None)}
            for p in filas[:tope]
        ],
    }


@tool(
    name="get_portfolio_performance",
    familia="carteras",
    description=(
        "La composición de una cartera y cómo le fue: retorno total, CAGR, "
        "volatilidad, Sharpe, Sortino y máxima caída, más los mismos números "
        "por tramos del período. Mirá los tramos antes de sacar conclusiones: "
        "un Sharpe alto que sale de un solo tramo no es una buena cartera."
    ),
    input_schema={
        "type": "object",
        "properties": {"portfolio_id": {"type": "integer"}},
        "required": ["portfolio_id"],
        "additionalProperties": False,
    },
)
def get_portfolio_performance(caller: AiCaller, portfolio_id: int) -> dict:
    from app.models import Asset
    from app.services import portfolio_backtest_service as pbs
    from app.services.portfolio_service import resolve_membership

    p = _cartera_visible(caller, portfolio_id)
    s = _sesion()

    miembros = resolve_membership(s, p.id) or []
    tickers = {a.id: a.ticker for a in s.query(Asset).filter(
        Asset.id.in_([aid for aid, _w in miembros])).all()} if miembros else {}

    curva = pbs.curated_equity_from_members(s, miembros)
    if curva is None:
        return {"portfolio_id": p.id, "name": p.name, "tipo": p.ptype,
                "composicion": [], "kpis": None,
                "aviso": ("la cartera no tiene miembros con precios cargados, "
                          "así que no hay curva que medir")}

    return {
        "portfolio_id": p.id, "name": p.name, "tipo": p.ptype,
        "composicion": [{"ticker": tickers.get(aid), "asset_id": aid,
                         "weight": w} for aid, w in miembros],
        "desde": str(curva["dates"][0]), "hasta": str(curva["dates"][-1]),
        "kpis": _solo_kpis(curva),
        "kpis_por_tramo": _por_tramos(curva),
    }


@tool(
    name="simulate_portfolio",
    familia="carteras",
    description=(
        "Simula una cartera hipotética a partir de una lista de tickers y "
        "pesos, y devuelve cómo habría andado: retorno, CAGR, volatilidad, "
        "Sharpe, Sortino, máxima caída, y los mismos números por tramos. "
        "NO crea nada: sirve para probar combinaciones antes de decidir.\n\n"
        "Los pesos se normalizan solos (no hace falta que sumen 1). Sin pesos, "
        "es equiponderada. Se rebalancea a los pesos objetivo todos los días.\n\n"
        "Cuidado al optimizar: buscar los pesos que mejor rindieron en el "
        "pasado es ajustar parámetros a datos históricos y casi siempre "
        "produce una cartera que se ve espectacular y no se repite. Mirá "
        "`kpis_por_tramo` y desconfiá de lo que vive de un solo tramo."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "holdings": {
                "type": "array",
                "description": f"Hasta {_TOPE_MIEMBROS} posiciones.",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "weight": {"type": "number", "exclusiveMinimum": 0,
                                   "description": "Opcional. Sin pesos, "
                                                  "equiponderada."},
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["holdings"],
        "additionalProperties": False,
    },
    max_rows=_TOPE_MIEMBROS,
)
def simulate_portfolio(caller: AiCaller, holdings: list) -> dict:
    from app.models import Asset
    from app.services import db_compat
    from app.services import portfolio_backtest_service as pbs

    if not holdings:
        raise ValueError("Indicá al menos una posición.")
    if len(holdings) > _TOPE_MIEMBROS:
        raise ValueError(f"Máximo {_TOPE_MIEMBROS} posiciones por simulación.")

    s = _sesion()
    miembros, detalle, faltantes = [], [], []
    for h in holdings:
        tk = str(h.get("ticker") or "").strip()
        if not tk:
            raise ValueError("Cada posición necesita un ticker.")
        a = s.query(Asset).filter(db_compat.ci_equals(Asset.ticker, tk)).first()
        if a is None:
            faltantes.append(tk)
            continue
        try:
            w = float(h.get("weight") if h.get("weight") is not None else 1.0)
        except (TypeError, ValueError):
            raise ValueError(f"Peso inválido para {tk}: {h.get('weight')!r}")
        if w <= 0:
            raise ValueError(f"El peso de {tk} tiene que ser mayor que 0.")
        miembros.append((a.id, w))
        detalle.append({"ticker": a.ticker, "asset_id": a.id, "weight": w})

    if faltantes:
        raise ValueError(
            "No existen estos activos en la instalación: "
            + ", ".join(faltantes) + ". Verificá los tickers.")

    total = sum(w for _a, w in miembros)
    miembros = [(aid, w / total) for aid, w in miembros]
    for d, (_aid, w) in zip(detalle, miembros):
        d["weight_normalizado"] = round(w, 6)

    curva = pbs.curated_equity_from_members(s, miembros)
    if curva is None:
        raise ValueError(
            "Ninguno de esos activos tiene precios cargados en el período.")

    # Contador sí, holdout no: acá el período sale de los precios de los
    # tickers elegidos y no de la historia de señales, así que el corte
    # compartido no significaría lo mismo. Pero el riesgo de probar
    # combinaciones hasta que una brille es idéntico, y eso el contador lo
    # hace visible.
    intentos = prudencia.registrar_intento(caller)
    aviso = prudencia.aviso_intentos(intentos)

    return {
        "guardado": False,
        "simulaciones_en_esta_sesion": intentos,
        **({"aviso_sobreajuste": aviso} if aviso else {}),
        "composicion": detalle,
        "desde": str(curva["dates"][0]), "hasta": str(curva["dates"][-1]),
        "n_ruedas": len(curva["dates"]),
        "kpis": _solo_kpis(curva),
        "kpis_por_tramo": _por_tramos(curva),
        "como_leerlo": (
            "Los KPIs globales están medidos sobre el mismo período con el que "
            "elegiste los pesos, así que si probaste varias combinaciones están "
            "inflados. Compará `kpis_por_tramo` entre sí: una cartera que se "
            "sostiene se parece en todos los tramos. Si el Sharpe global es "
            "alto pero sale de un tramo y los otros son flojos, no encontraste "
            "una buena cartera — encontraste un buen período. Al informarlo, "
            "mostrá los tramos, no solo el número global."),
        "nota": ("Esto NO se guardó: no se creó ninguna cartera. Para "
                 "conservarla hay que crearla desde la pantalla de Carteras."),
    }
