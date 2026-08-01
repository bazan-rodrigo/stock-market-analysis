"""El manual de usuario, como fuente sobre la SEMÁNTICA del sistema.

Es la herramienta que hace que las respuestas sean sobre *esta* plataforma y no
sobre finanzas en general. Las decisiones que un modelo no puede adivinar están
escritas ahí en prosa: la lectura as-of de los indicadores, que el último precio
es preliminar, que el ranking es transversal, que un indicador sin historia no
sirve para backtest, que un componente sin dato se saltea y no cuenta como cero.

El manual ya tiene control de acceso por rol en el front-matter (`roles:`), así
que se respeta el mismo nivel que vería el usuario en la web.
"""
from app.ai.caller import AiCaller
from app.ai.registry import limite, tool

_TOPE = 10


def _nivel(caller: AiCaller) -> int:
    """Nivel de visibilidad del caller, con el mismo escalafón que la web
    (invitado < analista < admin).

    NO se usa `manual_service.role_of()`: esa función deduce el rol de la
    tripla (autenticado, username, is_admin) que le da flask_login, y con
    `username=None` —que es lo que tiene la capa de IA, porque no le hace
    falta— devuelve "invitado" y recorta el manual a un tercio. El AiCaller ya
    trae la respuesta de forma explícita, así que se mapea directo."""
    from app.services import manual_service

    if caller.is_admin:
        return manual_service.level_of(manual_service.ROLE_ADMIN)
    if caller.user_id is not None:
        return manual_service.level_of(manual_service.ROLE_ANALYST)
    return manual_service.level_of(manual_service.ROLE_GUEST)


@tool(
    name="search_manual",
    description=(
        "Busca en el manual de usuario del sistema. Consultalo ANTES de "
        "explicar cómo funciona algo: acá están las reglas propias de esta "
        "plataforma (cómo se calculan los puntajes, qué significa cada pantalla, "
        "qué trampas tiene cada cálculo), que no se pueden deducir de "
        "conocimiento general de finanzas."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Qué buscar."},
            "limit": {"type": "integer", "minimum": 1,
                      "description": f"Máximo de secciones. Tope {_TOPE}."},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    max_rows=_TOPE,
)
def search_manual(caller: AiCaller, query: str, limit: int | None = None) -> dict:
    from app.services import manual_service

    secciones = manual_service.visible(manual_service.load_sections(),
                                       _nivel(caller))
    tope = limite(limit, _TOPE)
    hits = manual_service.search(secciones, query, limit=tope)
    return {
        "query": query,
        "resultados": [
            {"slug": h.section.slug, "title": h.section.title,
             "chapter": h.section.chapter, "snippet": h.snippet}
            for h in hits
        ],
    }


@tool(
    name="read_manual_section",
    description=(
        "El texto completo de una sección del manual, por su slug (lo devuelve "
        "search_manual). Usalo cuando el fragmento de la búsqueda no alcance."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string"},
        },
        "required": ["slug"],
        "additionalProperties": False,
    },
)
def read_manual_section(caller: AiCaller, slug: str) -> dict:
    from app.services import manual_service

    secciones = manual_service.visible(manual_service.load_sections(),
                                       _nivel(caller))
    seccion = manual_service.section_by_slug(secciones, slug)
    if seccion is None:
        raise ValueError(
            f"no existe una sección '{slug}' que puedas ver. Buscá con "
            f"search_manual.")
    return {"slug": seccion.slug, "title": seccion.title,
            "chapter": seccion.chapter, "body": seccion.body}
