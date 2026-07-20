"""
Manual de usuario — /manual y /manual/<slug>.

Renderiza como HTML navegable el contenido de docs/manual/*.md: índice por
capítulos a la izquierda (filtrado según el rol del usuario), sección a la
derecha, buscador sobre todo el manual y navegación anterior/siguiente.

El filtrado por rol se aplica en DOS lugares a propósito: el índice solo
lista lo que el usuario puede ver, y el acceso por URL directa a un slug
fuera de su alcance devuelve un aviso en vez del contenido. Sin lo segundo,
adivinar la URL saltearía el filtro.
"""
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.ui_constants import COLOR_NEUTRAL, COLOR_WARNING
from app.services import manual_service as ms


def current_role() -> str:
    """Rol del usuario logueado, con el mismo criterio que la navbar."""
    from flask_login import current_user
    return ms.role_of(
        bool(getattr(current_user, "is_authenticated", False)),
        getattr(current_user, "username", None),
        bool(getattr(current_user, "is_admin", False)),
    )


# ── Índice ───────────────────────────────────────────────────────────────────

def toc_children(sections: list[ms.Section], active_slug: str | None) -> list:
    """Índice agrupado por capítulo, con la sección actual resaltada."""
    hijos: list = []
    for capitulo, secciones in ms.build_toc(sections):
        hijos.append(html.Div(capitulo, className="manual-toc-chapter"))
        for s in secciones:
            clase = "manual-toc-item"
            if s.slug == active_slug:
                clase += " active"
            etiqueta = [s.title]
            if s.admin_only:
                etiqueta.append(html.Span("admin", className="manual-toc-badge"))
            hijos.append(dcc.Link(etiqueta, href=f"/manual/{s.slug}", className=clase))
    return hijos


def search_children(hits: list[ms.Hit], query: str) -> list:
    """Resultados de búsqueda, en el lugar del índice."""
    if not hits:
        return [html.Div(f"Sin resultados para «{query}»",
                         className="manual-toc-empty")]
    hijos: list = [html.Div(f"{len(hits)} resultado(s)", className="manual-toc-chapter")]
    for h in hits:
        hijos.append(dcc.Link(
            [html.Div(h.section.title, className="manual-hit-title"),
             html.Div(h.snippet, className="manual-hit-snippet")],
            href=f"/manual/{h.section.slug}", className="manual-hit"))
    return hijos


# ── Contenido ────────────────────────────────────────────────────────────────

def _breadcrumb(section: ms.Section) -> html.Div:
    partes = [html.Span(section.chapter, style={"color": COLOR_NEUTRAL})]
    if section.admin_only:
        partes += [" ", dbc.Badge("Solo administradores", color="warning",
                                  className="ms-1", style={"fontSize": "0.62rem"})]
    return html.Div(partes, className="manual-breadcrumb")


def _footer_nav(sections: list[ms.Section], slug: str) -> html.Div:
    anterior, siguiente = ms.neighbors(sections, slug)
    izq = (dcc.Link(f"← {anterior.title}", href=f"/manual/{anterior.slug}",
                    className="manual-nav-link")
           if anterior else html.Span())
    der = (dcc.Link(f"{siguiente.title} →", href=f"/manual/{siguiente.slug}",
                    className="manual-nav-link")
           if siguiente else html.Span())
    return html.Div([izq, der], className="manual-footer-nav")


def _render_section(section: ms.Section, sections: list[ms.Section]) -> list:
    cuerpo = [
        _breadcrumb(section),
        html.H3(section.title, className="manual-title"),
    ]
    if section.page:
        cuerpo.append(dcc.Link(
            f"Ir a la pantalla ({section.page})",
            href=section.page, className="manual-goto"))
    cuerpo += [
        dcc.Markdown(section.body, className="manual-body",
                     link_target="_self"),
        _footer_nav(sections, section.slug),
    ]
    return cuerpo


def _aviso(titulo: str, detalle: str, color: str = COLOR_WARNING) -> list:
    return [html.Div([
        html.H4(titulo, style={"color": color}),
        html.P(detalle, style={"color": COLOR_NEUTRAL}),
        dcc.Link("Volver al inicio del manual", href="/manual",
                 className="manual-nav-link"),
    ], className="manual-body")]


# ── Layout ───────────────────────────────────────────────────────────────────

def layout(slug: str | None = None, **kwargs):
    role = current_role()
    nivel = ms.level_of(role)
    todas = ms.load_sections()
    visibles = ms.visible(todas, nivel)

    if not todas:
        return html.Div(dbc.Alert(
            "El manual todavía no tiene contenido cargado "
            "(docs/manual/ está vacío o no se pudo leer).",
            color="warning"), className="mt-3")

    activa = ms.section_by_slug(visibles, slug)

    if slug and activa is None:
        existe = ms.section_by_slug(todas, slug) is not None
        contenido = _aviso(
            "Sección no disponible",
            ("Esta sección del manual está reservada a otro perfil de usuario."
             if existe else
             f"No existe una sección con el identificador «{slug}»."))
        slug_activo = None
    else:
        if activa is None:
            activa = visibles[0] if visibles else None
        if activa is None:
            contenido = _aviso(
                "Sin secciones disponibles",
                "No hay secciones del manual visibles para tu perfil.")
            slug_activo = None
        else:
            contenido = _render_section(activa, visibles)
            slug_activo = activa.slug

    sidebar = html.Div([
        html.Div([
            dbc.Input(id="manual-search", type="search", debounce=False,
                      placeholder="Buscar en el manual…", size="sm",
                      className="manual-search"),
        ], className="mb-2"),
        html.Div(toc_children(visibles, slug_activo), id="manual-toc",
                 className="manual-toc"),
    ], className="manual-sidebar")

    return html.Div([
        dcc.Store(id="manual-active-slug", data=slug_activo),
        dbc.Row([
            dbc.Col(sidebar, xs=12, md=4, lg=3, xl=3),
            dbc.Col(html.Div(contenido, id="manual-content",
                             className="manual-content"),
                    xs=12, md=8, lg=9, xl=9),
        ], className="g-3"),
    ], className="manual-page")


dash.register_page(__name__, path="/manual",
                   title="Manual de usuario", layout=layout)
dash.register_page(__name__ + "_slug", path_template="/manual/<slug>",
                   title="Manual de usuario", layout=layout)
