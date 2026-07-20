"""
Manual de usuario — carga, filtrado por rol y búsqueda.

El contenido vive en `docs/manual/*.md`, versionado en git: cuando cambia una
pantalla, su sección se corrige en el MISMO commit y el cambio se ve en el
diff. El usuario nunca ve Markdown — la página /manual lo renderiza como HTML
navegable.

Cada archivo abre con un front-matter de claves simples. El parseo es propio a
propósito: no hay PyYAML en requirements.txt y no se agrega una dependencia
para leer seis claves.

    ---
    slug: analisis-de-activo
    title: Análisis de Activo
    chapter: 3. Análisis
    order: 310
    roles: invitado
    page: /activo
    ---

`roles` declara el rol MÍNIMO que ve la sección, no una lista cerrada: los
roles son jerárquicos (invitado < analista < admin), así que `roles: analista`
la muestra a analistas Y admins. Si se listan varios separados por coma gana
el menor — así el autor nunca tiene que acordarse de sumar "admin" a mano.

`page` es opcional y ata la sección a una ruta de la app: es lo que permite
que el ícono «?» de cada pantalla sepa adónde ir, y lo que verifica
tests/test_manual_coverage.py.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MANUAL_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "manual"

# ── Roles ────────────────────────────────────────────────────────────────────
# Jerárquicos: cada nivel ve lo suyo y todo lo de los niveles inferiores.
ROLE_GUEST   = "invitado"
ROLE_ANALYST = "analista"
ROLE_ADMIN   = "admin"

ROLE_LEVEL = {ROLE_GUEST: 0, ROLE_ANALYST: 1, ROLE_ADMIN: 2}

ROLE_LABEL = {
    ROLE_GUEST:   "Todos",
    ROLE_ANALYST: "Analistas y administradores",
    ROLE_ADMIN:   "Solo administradores",
}

_REQUIRED_KEYS = ("slug", "title", "chapter")
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class Section:
    """Una sección del manual (un archivo .md)."""
    slug: str
    title: str
    chapter: str
    order: int
    min_level: int
    page: str | None
    body: str

    @property
    def audience(self) -> str:
        """Etiqueta legible de quién puede ver la sección."""
        for role, level in ROLE_LEVEL.items():
            if level == self.min_level:
                return ROLE_LABEL[role]
        return ROLE_LABEL[ROLE_ADMIN]

    @property
    def admin_only(self) -> bool:
        return self.min_level >= ROLE_LEVEL[ROLE_ADMIN]


# ── Lógica pura (testeable sin filesystem ni BD) ─────────────────────────────

def role_of(is_authenticated: bool, username: str | None, is_admin: bool) -> str:
    """Rol del usuario según el mismo criterio que usa la navbar.

    El invitado es un usuario autenticado SIN username (ver navbar.py); no
    confundir con el no autenticado, que ni siquiera llega a la página.
    """
    if not is_authenticated:
        return ROLE_GUEST
    if is_admin:
        return ROLE_ADMIN
    if username:
        return ROLE_ANALYST
    return ROLE_GUEST


def level_of(role: str) -> int:
    return ROLE_LEVEL.get(role, ROLE_LEVEL[ROLE_GUEST])


def min_level_for(roles_raw: str | None) -> int:
    """Nivel mínimo declarado en el front-matter.

    Vacío o no reconocido → invitado (visible para todos): un olvido del autor
    no debe esconder documentación, solo el `roles:` explícito restringe.
    Con varios roles gana el menor, que es el que realmente da acceso.
    """
    if not roles_raw:
        return ROLE_LEVEL[ROLE_GUEST]
    levels = [ROLE_LEVEL[r] for r in
              (p.strip().lower() for p in roles_raw.split(","))
              if r in ROLE_LEVEL]
    return min(levels) if levels else ROLE_LEVEL[ROLE_GUEST]


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Separa el front-matter del cuerpo. Sin front-matter → ({}, texto)."""
    m = _FRONT_MATTER_RE.match(text.replace("\r\n", "\n"))
    if not m:
        return {}, text.replace("\r\n", "\n")
    meta: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip()
    return meta, m.group(2)


def build_section(meta: dict[str, str], body: str, source: str = "") -> Section:
    """Construye la Section validando las claves obligatorias."""
    faltantes = [k for k in _REQUIRED_KEYS if not meta.get(k)]
    if faltantes:
        raise ValueError(
            f"Front-matter incompleto en {source or '<memoria>'}: "
            f"falta {', '.join(faltantes)}")
    try:
        order = int(meta.get("order", "0"))
    except ValueError:
        raise ValueError(
            f"'order' no es un entero en {source or '<memoria>'}: "
            f"{meta.get('order')!r}")
    page = (meta.get("page") or "").strip() or None
    return Section(
        slug=meta["slug"].strip(),
        title=meta["title"].strip(),
        chapter=meta["chapter"].strip(),
        order=order,
        min_level=min_level_for(meta.get("roles")),
        page=page,
        body=body.strip(),
    )


def visible(sections: list[Section], level: int) -> list[Section]:
    """Secciones que un usuario de ese nivel puede ver."""
    return [s for s in sections if s.min_level <= level]


def build_toc(sections: list[Section]) -> list[tuple[str, list[Section]]]:
    """Índice agrupado por capítulo.

    Los capítulos se ordenan por el `order` menor que contengan — así el
    número que abre el nombre del capítulo ("3. Análisis") es decorativo y
    reordenar es cuestión de tocar `order`, no de renombrar capítulos.
    """
    por_capitulo: dict[str, list[Section]] = {}
    for s in sorted(sections, key=lambda x: (x.order, x.title)):
        por_capitulo.setdefault(s.chapter, []).append(s)
    return sorted(por_capitulo.items(), key=lambda kv: kv[1][0].order)


def section_by_slug(sections: list[Section], slug: str | None) -> Section | None:
    if not slug:
        return None
    return next((s for s in sections if s.slug == slug), None)


def section_for_page(sections: list[Section], path: str | None) -> Section | None:
    """Sección atada a una ruta de la app (para el ícono «?»)."""
    if not path:
        return None
    path = path.rstrip("/") or "/"
    return next((s for s in sections
                 if s.page and s.page.rstrip("/") == path), None)


def neighbors(sections: list[Section],
              slug: str) -> tuple[Section | None, Section | None]:
    """(anterior, siguiente) en el orden de lectura del manual."""
    ordenadas = [s for _, grupo in build_toc(sections) for s in grupo]
    for i, s in enumerate(ordenadas):
        if s.slug == slug:
            return (ordenadas[i - 1] if i > 0 else None,
                    ordenadas[i + 1] if i + 1 < len(ordenadas) else None)
    return None, None


def normalize(text: str) -> str:
    """Minúsculas sin acentos — buscar 'analisis' tiene que encontrar 'Análisis'."""
    desc = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in desc if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class Hit:
    section: Section
    snippet: str


def search(sections: list[Section], query: str, limit: int = 40) -> list[Hit]:
    """Búsqueda de texto sobre título y cuerpo.

    Sin ranking sofisticado a propósito: el manual son decenas de secciones,
    no miles de documentos. Ordena por coincidencia en el título primero.
    """
    q = normalize(query or "").strip()
    if len(q) < 2:
        return []
    resultados: list[tuple[int, Hit]] = []
    for s in sections:
        titulo_norm = normalize(s.title)
        cuerpo_norm = normalize(s.body)
        en_titulo = q in titulo_norm
        pos = cuerpo_norm.find(q)
        if not en_titulo and pos < 0:
            continue
        resultados.append((0 if en_titulo else 1, Hit(s, _snippet(s.body, pos))))
    resultados.sort(key=lambda t: (t[0], t[1].section.order))
    return [hit for _, hit in resultados[:limit]]


def _snippet(body: str, pos: int, radio: int = 90) -> str:
    """Fragmento del cuerpo alrededor del match, para previsualizar el hit."""
    if pos < 0:
        return " ".join(body.split())[:2 * radio].strip()
    plano = " ".join(body[max(0, pos - radio):pos + radio].split())
    prefijo = "…" if pos - radio > 0 else ""
    sufijo = "…" if pos + radio < len(body) else ""
    return f"{prefijo}{plano}{sufijo}"


# ── Carga desde disco (cacheada por mtime) ───────────────────────────────────

_cache: list[Section] | None = None
_cache_stamp: tuple[int, float] | None = None


def _stamp(directory: Path) -> tuple[int, float]:
    """Huella del directorio: cantidad de archivos + mtime más reciente.

    Basta para invalidar el cache cuando se edita, agrega o borra una sección
    sin reiniciar la app en desarrollo. En producción el manual no cambia en
    caliente, así que esto es una comodidad, no una garantía.
    """
    archivos = list(directory.glob("*.md"))
    return len(archivos), max((f.stat().st_mtime for f in archivos), default=0.0)


def load_sections(directory: Path | None = None,
                  use_cache: bool = True) -> list[Section]:
    """Todas las secciones del manual, ordenadas por `order`.

    Un archivo con front-matter roto se saltea con un warning en vez de tirar
    abajo la página entera: el manual es documentación, no puede ser lo que
    impida entrar a la app.
    """
    global _cache, _cache_stamp
    directory = directory or MANUAL_DIR
    es_default = directory == MANUAL_DIR

    if not directory.is_dir():
        logger.warning("Directorio del manual inexistente: %s", directory)
        return []

    if use_cache and es_default and _cache is not None:
        if _cache_stamp == _stamp(directory):
            return _cache

    secciones: list[Section] = []
    vistos: dict[str, str] = {}
    for archivo in sorted(directory.glob("*.md")):
        try:
            meta, body = parse_front_matter(archivo.read_text(encoding="utf-8"))
            seccion = build_section(meta, body, source=archivo.name)
        except Exception as exc:
            logger.warning("Sección del manual ignorada (%s): %s", archivo.name, exc)
            continue
        if seccion.slug in vistos:
            logger.warning("Slug duplicado '%s' en %s (ya estaba en %s); se ignora",
                           seccion.slug, archivo.name, vistos[seccion.slug])
            continue
        vistos[seccion.slug] = archivo.name
        secciones.append(seccion)

    secciones.sort(key=lambda s: (s.order, s.title))
    if use_cache and es_default:
        _cache, _cache_stamp = secciones, _stamp(directory)
    return secciones


def clear_cache() -> None:
    """Invalida el cache (tests, o recarga manual tras editar el manual)."""
    global _cache, _cache_stamp
    _cache, _cache_stamp = None, None
