"""Las dos defensas contra el sobreajuste, compartidas por toda herramienta que
simule: el **holdout reservado** y el **contador de intentos**.

Por qué existe este módulo. Medir una estrategia sin crearla salió barato, y eso
es justamente el problema: probar cincuenta combinaciones y quedarse con la
mejor no encuentra la mejor estrategia, encuentra la que mejor se ajustó al
ruido de esta historia en particular. Con suficientes intentos siempre aparece
una que parece excelente por casualidad, y la casualidad no se repite con plata
de verdad.

El párrafo de advertencia que ya viajaba en las respuestas ayuda pero no
alcanza: es un pedido, y quien lo lee decide si hacerle caso. Acá hay dos cosas
que no se pueden ignorar leyendo.

**1. El holdout se EXCLUYE, no se oculta.** Tapar el número del último tramo no
serviría de nada mientras el IC medio global lo siga teniendo adentro: se lo
estaría mirando igual, promediado. Así que el período de exploración
directamente termina en el corte, y el tramo reservado no entra en el IC, ni en
los cuantiles, ni en la curva de equity. Verlo es una acción aparte y explícita
(`revelar_holdout`).

**2. El corte es del CALENDARIO, no del pedido.** Si el holdout fuera "el último
cuarto de lo que pediste", correr `date_to` hacia atrás entre intentos iría
descubriendo el tramo reservado de a pedazos sin pedirlo nunca. Por eso el corte
sale de la historia disponible de la instalación y es el mismo para todas las
llamadas y todas las herramientas: dos mediciones de exploración siempre hablan
del mismo período.

Ninguna de las dos es una barrera infranqueable —se puede pedir la revelación en
la primera llamada— y no pretenden serlo. Lo que hacen es que mirar el holdout
sea un acto deliberado y contado, en vez de algo que ya pasó sin que nadie lo
note.
"""
from datetime import timedelta

# Qué proporción de la historia queda reservada. Un cuarto es el equilibrio
# habitual: suficiente para que el tramo tenga cross-sections de sobra y no
# tanto como para dejar la exploración sin régimen de mercado variado.
FRACCION_HOLDOUT = 0.25


def rango_disponible(session) -> tuple:
    """(primera, última) fecha con dato de señales en la instalación.

    Sale de TODAS las señales definidas y no de las que use el pedido: si el
    corte dependiera de los componentes elegidos, cambiar un componente movería
    el borde del holdout y dos mediciones dejarían de ser comparables.

    Son unas pocas decenas de min/max con índice, y contra el costo de un
    backtest es ruido — por eso no hay caché, que además envejecería mal cuando
    el pipeline sumara historia nueva.
    """
    from app.models import SignalDefinition
    from app.services.backtest_service import rango_de_senales

    ids = [r.id for r in session.query(SignalDefinition.id).all()]
    if not ids:
        return None, None
    return rango_de_senales(session, ids)


def ventana(session, date_from=None, date_to=None,
            revelar_holdout: bool = False, anios_default: int = 5) -> dict:
    """El período efectivo de una corrida, ya con el holdout aplicado.

    Devuelve {'date_from', 'date_to', 'corte', 'modo', 'nota'} en ISO. `modo` es
    'exploracion' (hasta el corte) u 'holdout' (solo el tramo reservado).

    Sin `date_from`, la exploración arranca `anios_default` años antes del
    corte en vez de al principio de la historia. No es una opinión sobre qué
    período es el correcto: es que barrer cincuenta años de precios para
    contestar "¿esto ordena bien?" cuesta minutos, y quien quiera todo el
    período lo pide explícitamente.
    """
    d0, d1 = rango_disponible(session)
    if d0 is None or d1 is None or d1 <= d0:
        return {"date_from": date_from, "date_to": date_to, "corte": None,
                "modo": "sin_holdout",
                "nota": ("No hay suficiente historia de señales para reservar "
                         "un holdout: esta corrida usa todo lo que hay.")}

    corte = d0 + timedelta(days=int((d1 - d0).days * (1 - FRACCION_HOLDOUT)))

    if revelar_holdout:
        desde = max(_a_fecha(date_from), corte + timedelta(days=1)) \
            if date_from else corte + timedelta(days=1)
        return {
            "date_from": desde.isoformat(),
            "date_to": (_a_fecha(date_to) or d1).isoformat(),
            "corte": corte.isoformat(), "modo": "holdout",
            "nota": ("Este resultado es el TRAMO RESERVADO, el que no entró en "
                     "ninguna de las corridas de exploración. Es lo más "
                     "parecido a una prueba honesta que hay acá, y vale una "
                     "sola vez: a partir de ahora ya lo viste, así que "
                     "cualquier ajuste que hagas mirándolo vuelve a ser "
                     "ajuste a datos pasados. Si se parece a lo que veías "
                     "antes, la idea es creíble; si se derrumba, era ruido."),
        }

    hasta = min(_a_fecha(date_to), corte) if date_to else corte
    desde = (_a_fecha(date_from) if date_from
             else max(d0, hasta - timedelta(days=365 * int(anios_default))))
    return {
        "date_from": desde.isoformat(),
        "date_to": hasta.isoformat(),
        "corte": corte.isoformat(), "modo": "exploracion",
        "nota": (f"La historia posterior al {corte.isoformat()} quedó "
                 f"RESERVADA y no entró en este resultado — ni en el IC, ni en "
                 f"los cuantiles, ni en la curva. Explorá todo lo que quieras "
                 f"acá; cuando ya te hayas decidido por una configuración, "
                 f"pedila de nuevo con revelar_holdout para ver cómo le fue en "
                 f"el tramo que no miraste. Mirarlo antes de decidir lo "
                 f"desperdicia: deja de ser una prueba independiente."),
    }


def _a_fecha(valor):
    from app.services.backtest_service import a_fecha

    return a_fecha(valor)


# ── Contador de intentos ─────────────────────────────────────────────────────
#
# En memoria del proceso y a propósito: persistirlo sería la primera escritura
# de la IA sobre la base, y no vale una migración. Las dos limitaciones que eso
# trae están dichas en la respuesta al usuario, no escondidas — se reinicia con
# el servicio, y cuenta por usuario y no por conversación.

_INTENTOS: dict = {}


def registrar_intento(caller) -> int:
    """Suma uno a las simulaciones de este usuario y devuelve el total."""
    user_id, _admin = caller.viewer()
    _INTENTOS[user_id] = _INTENTOS.get(user_id, 0) + 1
    return _INTENTOS[user_id]


def aviso_intentos(n: int) -> str | None:
    """El texto que acompaña al número, o None si todavía no hay nada que decir.

    Aparece recién a partir de la cuarta simulación: antes es exploración
    normal y un cartel en cada respuesta se vuelve ruido que se ignora.
    """
    if n < 4:
        return None
    return (
        f"Van {n} simulaciones tuyas en esta sesión. Cuantas más combinaciones "
        f"pruebes sobre el mismo período, más probable es que la mejor lo sea "
        f"por casualidad y no por mérito: con una docena de intentos, que "
        f"alguna se destaque es lo ESPERABLE aunque ninguna sirva. Al "
        f"informarle un resultado a la persona, decile cuántas probaste antes "
        f"de llegar a él — es un dato tan importante como el número.")


def reiniciar_contador() -> None:
    """Solo para los tests: el estado de módulo no se comparte entre casos."""
    _INTENTOS.clear()
