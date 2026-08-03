"""Escribir un pack: el formato publicado y el ensayo contra ESTA base.

Las demás herramientas responden preguntas sobre datos que ya existen. Estas dos
son para lo otro que la aplicación espera de una IA —que proponga señales y
estrategias armadas, ver el `nota` de get_catalog— y existen porque sin ellas ese
trabajo se hacía a ciegas.

`get_catalog` ya entregaba la mitad VARIABLE del estándar: qué indicadores hay en
esta instalación, qué categorías devuelve cada uno, qué sectores están cargados.
Faltaba la mitad FIJA, que es la forma del archivo. Vive en
`strategy_packs/SPEC.md`, viaja con la aplicación y hasta ahora salía por un solo
camino: el botón de descarga de la pantalla de packs, que no existe para quien
conversa por MCP. El modelo llegaba a la sección del manual que dice "la
especificación completa se descarga desde esta misma pantalla" y ahí se quedaba,
enterado de que hay un documento de 600 líneas que no puede abrir.

La segunda cierra el ciclo. El validador offline ya reproduce lo que el import
verifica, pero lo tiene que correr una persona en una consola, y sin pasarle el
catálogo a mano valida a medias (lo dice en `skipped`, en vez de dar un OK que no
significa nada). Del lado del servidor el catálogo está ahí, así que el ensayo
sale completo — y además cruza contra la base para decir qué crearía y qué
PISARÍA, que es el riesgo real de un archivo escrito afuera: reusar una `key` que
ya existe y sobreescribir en silencio una señal del catálogo curado.

Ninguna de las dos escribe nada. Aplicar el pack sigue siendo un acto humano en
`/admin/packs`.
"""
import json
import re

from app.ai.caller import AiCaller
from app.ai.registry import tool

# Tope de lo que puede llegar EN los argumentos. Es la primera herramienta que
# recibe un documento en vez de devolverlo, así que el límite va explícito: un
# pack de catálogo completo (50 señales con sus fórmulas) ronda los 40 KB, y
# cualquier cosa mucho mayor que esto es un error de quien llama, no un pack.
MAX_PACK_BYTES = 256 * 1024


def _secciones(texto: str) -> list[tuple[str, str]]:
    """(título, cuerpo) de cada capítulo `## ` del documento.

    El preámbulo queda afuera a propósito: no es un capítulo pedible, y quien
    quiera leerlo pide el documento entero, que es el default.
    """
    partes = re.split(r"(?m)^## ", texto)[1:]
    salida = []
    for parte in partes:
        titulo, _, cuerpo = parte.partition("\n")
        salida.append((titulo.strip(), f"## {titulo.strip()}\n{cuerpo}".rstrip()))
    return salida


def _elegir(secciones: list[tuple[str, str]], pedida: str) -> tuple[str, str]:
    """Resuelve el capítulo por número ("6", "6.") o por parte de su título.

    Las dos formas porque el documento numera sus capítulos y el modelo los va a
    citar de las dos maneras: tal como aparecen en la lista que devolvemos, o
    por el número que leyó en una referencia interna del propio SPEC (`§7`).
    """
    q = str(pedida or "").strip().lower().lstrip("§").rstrip(".")
    for titulo, cuerpo in secciones:
        numero = titulo.split(".", 1)[0].strip()
        if q and (q == numero.lower() or q in titulo.lower()):
            return titulo, cuerpo
    raise ValueError(
        f"no hay una sección '{pedida}' en la especificación. Las secciones "
        f"son: {'; '.join(t for t, _ in secciones)}. También podés pedirla sin "
        f"argumentos y te devuelvo el documento completo.")


@tool(
    name="get_pack_spec",
    familia="packs",
    description=(
        "La especificación del formato de packs: el contrato publicado que hay "
        "que seguir para escribir señales y estrategias afuera del sistema y "
        "que la aplicación las pueda importar. Pedila ANTES de proponer una "
        "señal o una estrategia — la forma del archivo, los parámetros de cada "
        "fórmula y la gramática del filtro de elegibilidad están definidos ahí "
        "y no se pueden deducir. Es la mitad fija del estándar, igual en toda "
        "instalación; la otra mitad, qué indicadores y sectores existen ACÁ, "
        "sale de get_catalog. Sin argumentos devuelve el documento entero; con "
        "`seccion` devuelve un solo capítulo."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "seccion": {
                "type": "string",
                "description": "Capítulo puntual, por su número ('6') o por "
                               "parte de su título ('filtro'). Por omisión, "
                               "el documento completo.",
            },
        },
        "additionalProperties": False,
    },
)
def get_pack_spec(caller: AiCaller, seccion: str | None = None) -> dict:
    from app.services import pack_service

    # El contrato es público por diseño —el SPEC existe justamente para que lo
    # pueda seguir alguien que no ve este repo ni esta base— y no depende de
    # quién pregunta: no hay gate de visibilidad que re-aplicar. Se deja dicho
    # para que no parezca un olvido. El ensayo de abajo sí lo tiene.
    caller.viewer()

    texto = pack_service.spec_bytes().decode("utf-8")
    secciones = _secciones(texto)
    base = {
        "spec_version": pack_service.SPEC_VERSION,
        "secciones": [t for t, _ in secciones],
        "catalogo": (
            "Los `indicator_key` y los valores de sector/mercado/país válidos "
            "salen de get_catalog, no de este documento: cambian de una "
            "instalación a otra."),
        "ensayo": (
            "Cuando lo tengas escrito, pasalo por preview_pack antes de "
            "entregarlo: valida contra esta base y avisa qué pisaría."),
    }
    if seccion is None:
        return {**base, "contenido": texto}

    titulo, cuerpo = _elegir(secciones, seccion)
    return {**base, "seccion": titulo, "contenido": cuerpo}


@tool(
    name="preview_pack",
    familia="packs",
    description=(
        "Ensaya un pack contra ESTA instalación sin escribir nada, igual que "
        "el paso previo a importarlo en la pantalla. Devuelve los errores que "
        "rechazarían el archivo (el import es todo-o-nada), los avisos de "
        "trampas silenciosas —una señal que nunca puntúa, un ranking que un "
        "solo activo puede dominar— y, fila por fila, qué crearía y qué "
        "ACTUALIZARÍA, con el dueño actual de lo que pisaría. Usalo siempre "
        "antes de entregar un pack: verifica que los indicadores existan acá y "
        "que los sectores del filtro estén cargados, que es lo que no se puede "
        "saber escribiendo a ciegas. No importa nada: aplicarlo lo decide una "
        "persona desde la pantalla."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pack": {
                "type": ["object", "string"],
                "description": "El pack completo: el objeto JSON tal como "
                               "quedaría el archivo (o su texto).",
            },
        },
        "required": ["pack"],
        "additionalProperties": False,
    },
)
def preview_pack(caller: AiCaller, pack) -> dict:
    from app.services import pack_service

    user_id, is_admin = caller.viewer()
    # Re-aplicar el gate: la pantalla equivalente es admin-only, y el informe
    # nombra señales y estrategias que ya existen —con su dueño— para decir cuál
    # pisaría. Sin esto, un analista descubriría por acá las definiciones
    # privadas de otro usuario probando nombres.
    if not is_admin:
        raise ValueError(
            "el ensayo de packs es solo para administradores, igual que la "
            "pantalla que lo hace: el informe dice qué definiciones ya existen "
            "y de quién son. Podés escribir el pack lo mismo —get_pack_spec y "
            "get_catalog no tienen esa restricción— y dárselo a un "
            "administrador para que lo revise y lo aplique.")

    crudo = _crudo(pack)
    try:
        parseado = pack_service.parse_pack(crudo)
    except pack_service.PackError as exc:
        raise ValueError(f"el pack no se pudo leer: {exc}") from exc

    resultado = pack_service.preview_pack(parseado, acting_user_id=user_id)
    resultado["como_leerlo"] = (
        "Con un solo error el archivo se rechaza entero, así que corregilos "
        "todos antes de entregarlo. Los avisos NO impiden importar: son cosas "
        "que el sistema acepta y después no puntúan, así que revisá que cada "
        "uno sea deliberado. Una fila 'actualiza' significa que ya existe algo "
        "con ese nombre o esa key y el import lo pisa: si no era la intención, "
        "cambiá el nombre en vez de sobreescribir una definición del catálogo.")
    return resultado


def _crudo(pack) -> bytes:
    """El pack como bytes de archivo, venga como objeto o como texto.

    Se acepta el texto además del objeto porque un modelo que ya escribió el
    JSON en la conversación tiende a mandarlo tal cual, y rechazarlo solo gasta
    un turno. Cualquiera de las dos formas termina pasando por el MISMO parseo
    que usa el import, así que un error de forma se ve acá y no después.
    """
    if isinstance(pack, str):
        crudo = pack.encode("utf-8")
    elif isinstance(pack, dict):
        crudo = json.dumps(pack, ensure_ascii=False).encode("utf-8")
    else:
        raise ValueError(
            "'pack' tiene que ser el objeto JSON del pack (o su texto); llegó "
            + ("una lista" if isinstance(pack, list) else type(pack).__name__))

    if len(crudo) > MAX_PACK_BYTES:
        raise ValueError(
            f"el pack pesa {len(crudo) // 1024} KB y el tope es "
            f"{MAX_PACK_BYTES // 1024} KB. Partilo: un pack puede traer solo "
            f"señales, y las estrategias que las usan pueden ir en otro.")
    return crudo
