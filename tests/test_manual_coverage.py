"""Integridad del contenido del manual (docs/manual/*.md).

Ata el manual al código: si una pantalla referencia una sección que no existe,
o una sección apunta a una ruta que ya no está, la suite falla acá y no el
usuario contra un enlace roto.

La cobertura pantalla-por-pantalla (que TODA página registrada tenga su
sección) se activa cuando el contenido esté completo — ver el test final.
"""
import re
from pathlib import Path

from app.services import manual_service as ms

ROOT = Path(__file__).resolve().parent.parent
MANUAL_DIR = ROOT / "docs" / "manual"
PAGES_DIR = ROOT / "app" / "pages"

# help_link("slug") y page_header("Título", "slug")
_HELP_LINK_RE = re.compile(r"""help_link\(\s*["']([\w-]+)["']""")
_PAGE_HEADER_RE = re.compile(
    r"""page_header\(\s*["'][^"']*["']\s*,\s*["']([\w-]+)["']""")
_ROUTE_RE = re.compile(r"""path(?:_template)?\s*=\s*["']([^"']+)["']""")


def _secciones():
    return ms.load_sections(MANUAL_DIR, use_cache=False)


def _rutas_registradas() -> set[str]:
    """Rutas declaradas en los register_page de app/pages/."""
    rutas = set()
    for archivo in PAGES_DIR.glob("*.py"):
        src = archivo.read_text(encoding="utf-8")
        for bloque in re.findall(r"register_page\((.*?)\)", src, re.DOTALL):
            for ruta in _ROUTE_RE.findall(bloque):
                rutas.add(ruta.rstrip("/") or "/")
    return rutas


def _slugs_referenciados() -> dict[str, list[str]]:
    """{slug: [archivos que lo referencian]} en todo app/.

    Se saltea app/components/help.py: es el módulo que DEFINE help_link, y los
    slugs que aparecen ahí son los ejemplos de su docstring, no referencias
    reales de una pantalla.
    """
    refs: dict[str, list[str]] = {}
    for archivo in (ROOT / "app").rglob("*.py"):
        if archivo.name == "help.py" and archivo.parent.name == "components":
            continue
        src = archivo.read_text(encoding="utf-8")
        for slug in _HELP_LINK_RE.findall(src) + _PAGE_HEADER_RE.findall(src):
            refs.setdefault(slug, []).append(
                str(archivo.relative_to(ROOT)).replace("\\", "/"))
    return refs


def test_hay_contenido():
    assert _secciones(), "docs/manual/ no tiene ninguna sección válida"


def test_todos_los_md_parsean():
    """load_sections descarta en silencio lo que no parsea: acá eso es un error."""
    archivos = list(MANUAL_DIR.glob("*.md"))
    cargadas = _secciones()
    assert len(cargadas) == len(archivos), (
        f"{len(archivos) - len(cargadas)} archivo(s) de docs/manual/ no cargaron: "
        "front-matter incompleto, 'order' no entero o slug duplicado. "
        "Corré con -o log_cli=true para ver el warning de cada uno.")


def test_slugs_unicos():
    slugs = [s.slug for s in _secciones()]
    duplicados = {s for s in slugs if slugs.count(s) > 1}
    assert not duplicados, f"Slugs duplicados en docs/manual/: {sorted(duplicados)}"


def test_orders_unicos():
    """Dos secciones con el mismo `order` dejan el índice a merced del
    desempate alfabético; mejor que el autor elija."""
    ordenes = [s.order for s in _secciones()]
    repetidos = sorted({o for o in ordenes if ordenes.count(o) > 1})
    assert not repetidos, (
        f"Valores de 'order' repetidos en docs/manual/: {repetidos}")


def test_campos_obligatorios_no_vacios():
    for s in _secciones():
        assert s.slug and s.title and s.chapter, f"Sección incompleta: {s.slug!r}"
        assert s.body, f"La sección '{s.slug}' no tiene cuerpo"


def test_page_apunta_a_una_ruta_existente():
    rutas = _rutas_registradas()
    rotas = [(s.slug, s.page) for s in _secciones()
             if s.page and s.page.rstrip("/") not in rutas]
    assert not rotas, (
        f"Secciones cuyo 'page:' no corresponde a ninguna ruta registrada "
        f"en app/pages/: {rotas}")


def test_todo_slug_referenciado_por_una_pantalla_existe():
    """El ícono «?» nunca puede llevar a una sección inexistente."""
    existentes = {s.slug for s in _secciones()}
    rotas = {slug: archivos for slug, archivos in _slugs_referenciados().items()
             if slug not in existentes}
    assert not rotas, (
        f"Pantallas que referencian secciones inexistentes del manual: {rotas}. "
        f"Creá el .md en docs/manual/ o corregí el slug.")


def test_enlaces_internos_apuntan_a_secciones_existentes():
    """Las secciones se enlazan entre sí con (/manual/slug); un slug mal
    escrito da una pantalla de 'sección inexistente' en vez de un 404, así que
    sin este test pasaría inadvertido."""
    existentes = {s.slug for s in _secciones()}
    rotos: dict[str, list[str]] = {}
    for archivo in MANUAL_DIR.glob("*.md"):
        texto = archivo.read_text(encoding="utf-8")
        for slug in re.findall(r"\(/manual/([a-z0-9-]+)\)", texto):
            if slug not in existentes:
                rotos.setdefault(archivo.name, []).append(slug)
    assert not rotos, f"Enlaces internos del manual a secciones inexistentes: {rotos}"


def test_enlaces_a_pantallas_apuntan_a_rutas_existentes():
    """Igual que el anterior pero para los enlaces directos a la app."""
    rutas = _rutas_registradas()
    rotos: dict[str, list[str]] = {}
    for archivo in MANUAL_DIR.glob("*.md"):
        texto = archivo.read_text(encoding="utf-8")
        for destino in re.findall(r"\]\((/[a-z0-9\-/]+)\)", texto):
            if destino.startswith("/manual"):
                continue    # cubierto por el test anterior
            if destino.rstrip("/") not in rutas:
                rotos.setdefault(archivo.name, []).append(destino)
    assert not rotos, f"Enlaces del manual a rutas inexistentes de la app: {rotos}"


def test_roles_declarados_son_validos():
    """Un rol mal escrito degrada a 'visible para todos' en silencio: que no
    pase inadvertido en una sección de administración."""
    invalidos = []
    for archivo in MANUAL_DIR.glob("*.md"):
        meta, _ = ms.parse_front_matter(archivo.read_text(encoding="utf-8"))
        for rol in (meta.get("roles") or "").split(","):
            rol = rol.strip().lower()
            if rol and rol not in ms.ROLE_LEVEL:
                invalidos.append((archivo.name, rol))
    assert not invalidos, (
        f"Roles desconocidos en el front-matter: {invalidos}. "
        f"Válidos: {sorted(ms.ROLE_LEVEL)}")


def test_cobertura_de_pantallas():
    """Toda pantalla con ruta propia debería tener su sección en el manual.

    Mientras se redacta el contenido este test informa el faltante sin romper
    la suite; al cerrar la última tanda de redacción se saca el skip y queda
    como red permanente (igual que test_module_registration para _PAGES).
    """
    import pytest

    documentadas = {s.page.rstrip("/") for s in _secciones() if s.page}
    # Rutas de detalle o utilitarias que no llevan sección propia
    excluidas = {"/manual", "/login", "/"}
    faltantes = sorted(r for r in _rutas_registradas()
                       if r not in documentadas
                       and r not in excluidas
                       and "<" not in r)
    if faltantes:
        pytest.skip(f"Manual en redacción: faltan {len(faltantes)} pantallas "
                    f"por documentar: {faltantes[:5]}…")
