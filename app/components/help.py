"""
Ícono de ayuda contextual — enlaza una pantalla con su sección del manual.

Uso típico, junto al título de la pantalla:

    from app.components.help import page_header
    ...
    page_header("Análisis de Activo", "analisis-de-activo")

o, cuando el encabezado ya está armado y solo falta el ícono:

    html.H4(["Señales ", help_link("configuracion-senales")])

El slug tiene que existir en docs/manual/ — tests/test_manual_coverage.py
falla si se referencia uno que no está, así que el ícono nunca lleva a una
sección inexistente.

Se usa un badge «?» con CSS propio en vez de un ícono de Font Awesome para no
atarse a la versión de FA que traiga dash-bootstrap-components (los nombres de
clase cambiaron entre FA5 y FA6).
"""
from dash import dcc, html


def help_link(slug: str, tooltip: str = "Abrir el manual de esta pantalla"):
    """Badge «?» que navega a /manual/<slug> sin recargar la página."""
    return dcc.Link(
        "?",
        href=f"/manual/{slug}",
        className="manual-help-icon",
        title=tooltip,
    )


def page_header(title: str, slug: str, **kwargs):
    """Encabezado de pantalla con el ícono de ayuda al lado.

    El nivel es SIEMPRE h4: el título de una pantalla es el título de una
    pantalla, y que cada una eligiera el suyo (había h3, h4, h5 y h6 conviviendo)
    es lo que hacía que la app se viera armada por partes. Antes esta función
    tenía un parámetro `level` "para respetar el tamaño que ya usaba cada
    pantalla" — o sea que codificaba la inconsistencia en vez de resolverla.

    `kwargs` va al componente. El margen inferior default es `mb-2`; las
    pantallas que ponen el título dentro de una fila de controles pasan
    `className="mb-0"` para alinearlo con los botones.
    """
    kwargs.setdefault("className", "mb-2")
    return html.H4([title, " ", help_link(slug)], **kwargs)
