"""Lógica del manual de usuario: parseo del front-matter, filtrado por rol,
índice, navegación y búsqueda. Todo lógica pura — no toca la base ni Dash."""
import pytest

from app.services import manual_service as ms


def _sec(slug, title="T", chapter="Cap", order=0, roles=None, page=None,
         body="cuerpo"):
    """Section armada a mano, sin pasar por el filesystem."""
    meta = {"slug": slug, "title": title, "chapter": chapter, "order": str(order)}
    if roles:
        meta["roles"] = roles
    if page:
        meta["page"] = page
    return ms.build_section(meta, body)


# ── Front-matter ─────────────────────────────────────────────────────────────

def test_parse_front_matter_separa_meta_y_cuerpo():
    meta, body = ms.parse_front_matter(
        "---\nslug: x\ntitle: Título\n---\n# Hola\n\nTexto.")
    assert meta == {"slug": "x", "title": "Título"}
    assert body.strip() == "# Hola\n\nTexto."


def test_parse_front_matter_tolera_crlf():
    """Los .md se editan en Windows: el front-matter no puede romperse por \\r."""
    meta, body = ms.parse_front_matter(
        "---\r\nslug: x\r\ntitle: T\r\n---\r\nCuerpo\r\n")
    assert meta["slug"] == "x"
    assert "\r" not in body


def test_parse_front_matter_sin_front_matter_devuelve_texto_entero():
    meta, body = ms.parse_front_matter("# Solo markdown")
    assert meta == {}
    assert body == "# Solo markdown"


def test_parse_front_matter_ignora_lineas_sin_dos_puntos():
    meta, _ = ms.parse_front_matter("---\nslug: x\nbasura\n# comentario\n---\nc")
    assert meta == {"slug": "x"}


def test_parse_front_matter_respeta_dos_puntos_en_el_valor():
    meta, _ = ms.parse_front_matter("---\ntitle: Backtest: niveles A-D\n---\nc")
    assert meta["title"] == "Backtest: niveles A-D"


def test_build_section_exige_las_claves_obligatorias():
    with pytest.raises(ValueError, match="chapter"):
        ms.build_section({"slug": "x", "title": "T"}, "cuerpo")


def test_build_section_rechaza_order_no_entero():
    with pytest.raises(ValueError, match="order"):
        ms.build_section(
            {"slug": "x", "title": "T", "chapter": "C", "order": "diez"}, "c")


def test_build_section_page_vacia_es_none():
    assert _sec("x", page=None).page is None
    assert ms.build_section(
        {"slug": "x", "title": "T", "chapter": "C", "page": "  "}, "c").page is None


# ── Roles ────────────────────────────────────────────────────────────────────

def test_role_of_distingue_los_tres_perfiles():
    assert ms.role_of(True, "ana", False) == ms.ROLE_ANALYST
    assert ms.role_of(True, "jefe", True) == ms.ROLE_ADMIN
    # Invitado = autenticado SIN username (mismo criterio que la navbar)
    assert ms.role_of(True, None, False) == ms.ROLE_GUEST
    assert ms.role_of(False, None, False) == ms.ROLE_GUEST


def test_role_of_admin_sin_username_sigue_siendo_admin():
    assert ms.role_of(True, None, True) == ms.ROLE_ADMIN


def test_min_level_sin_roles_es_visible_para_todos():
    """Olvidarse el `roles:` no debe esconder documentación."""
    assert ms.min_level_for(None) == ms.ROLE_LEVEL[ms.ROLE_GUEST]
    assert ms.min_level_for("") == ms.ROLE_LEVEL[ms.ROLE_GUEST]
    assert ms.min_level_for("perfil-inventado") == ms.ROLE_LEVEL[ms.ROLE_GUEST]


def test_min_level_toma_el_rol_menor_de_la_lista():
    assert ms.min_level_for("admin") == ms.ROLE_LEVEL[ms.ROLE_ADMIN]
    assert ms.min_level_for("admin, analista") == ms.ROLE_LEVEL[ms.ROLE_ANALYST]
    assert ms.min_level_for("ADMIN , Invitado") == ms.ROLE_LEVEL[ms.ROLE_GUEST]


def test_visible_es_jerarquico():
    """`roles: analista` la ve el analista Y el admin, sin declararlo."""
    secciones = [_sec("pub"), _sec("ana", roles="analista"),
                 _sec("adm", roles="admin")]

    def slugs(role):
        return [s.slug for s in ms.visible(secciones, ms.level_of(role))]

    assert slugs(ms.ROLE_GUEST) == ["pub"]
    assert slugs(ms.ROLE_ANALYST) == ["pub", "ana"]
    assert slugs(ms.ROLE_ADMIN) == ["pub", "ana", "adm"]


def test_admin_only_y_audiencia():
    assert _sec("x", roles="admin").admin_only is True
    assert _sec("x", roles="analista").admin_only is False
    assert _sec("x", roles="admin").audience == ms.ROLE_LABEL[ms.ROLE_ADMIN]
    assert _sec("x").audience == ms.ROLE_LABEL[ms.ROLE_GUEST]


# ── Índice y navegación ──────────────────────────────────────────────────────

def test_build_toc_agrupa_y_ordena_capitulos_por_su_order_menor():
    """El número del nombre del capítulo es decorativo: manda `order`."""
    secciones = [
        _sec("b1", chapter="Segundo", order=200),
        _sec("a2", chapter="Primero", order=110),
        _sec("a1", chapter="Primero", order=100),
    ]
    toc = ms.build_toc(secciones)
    assert [cap for cap, _ in toc] == ["Primero", "Segundo"]
    assert [s.slug for s in toc[0][1]] == ["a1", "a2"]


def test_neighbors_recorre_el_orden_de_lectura_cruzando_capitulos():
    secciones = [
        _sec("a", chapter="Uno", order=100),
        _sec("b", chapter="Uno", order=110),
        _sec("c", chapter="Dos", order=200),
    ]
    assert ms.neighbors(secciones, "a")[0] is None
    assert ms.neighbors(secciones, "a")[1].slug == "b"
    # El siguiente de la última del capítulo 1 es la primera del capítulo 2
    assert ms.neighbors(secciones, "b")[1].slug == "c"
    assert ms.neighbors(secciones, "c")[1] is None


def test_neighbors_slug_inexistente_no_rompe():
    assert ms.neighbors([_sec("a")], "no-existe") == (None, None)


def test_section_by_slug():
    secciones = [_sec("a"), _sec("b")]
    assert ms.section_by_slug(secciones, "b").slug == "b"
    assert ms.section_by_slug(secciones, "z") is None
    assert ms.section_by_slug(secciones, None) is None


def test_section_for_page_ignora_la_barra_final():
    secciones = [_sec("a", page="/activo"), _sec("b", page="/admin/users/")]
    assert ms.section_for_page(secciones, "/activo").slug == "a"
    assert ms.section_for_page(secciones, "/activo/").slug == "a"
    assert ms.section_for_page(secciones, "/admin/users").slug == "b"
    assert ms.section_for_page(secciones, "/otra") is None
    assert ms.section_for_page(secciones, None) is None


# ── Búsqueda ─────────────────────────────────────────────────────────────────

def test_search_ignora_acentos_y_mayusculas():
    secciones = [_sec("a", title="Análisis de Activo", body="Sobre el ANÁLISIS.")]
    assert len(ms.search(secciones, "analisis")) == 1
    assert len(ms.search(secciones, "ANÁLISIS")) == 1


def test_search_exige_al_menos_dos_caracteres():
    secciones = [_sec("a", title="Activo")]
    assert ms.search(secciones, "a") == []
    assert ms.search(secciones, "") == []
    assert ms.search(secciones, None) == []
    assert len(ms.search(secciones, "ac")) == 1


def test_search_prioriza_coincidencias_en_el_titulo():
    secciones = [
        _sec("cuerpo", title="Otra cosa", body="menciona backtest al pasar",
             order=10),
        _sec("titulo", title="Backtest de estrategia", body="nada", order=20),
    ]
    assert [h.section.slug for h in ms.search(secciones, "backtest")] == \
        ["titulo", "cuerpo"]


def test_search_devuelve_snippet_alrededor_del_match():
    cuerpo = "bla " * 60 + "PALABRACLAVE" + " ble" * 60
    hits = ms.search([_sec("a", body=cuerpo)], "palabraclave")
    assert "PALABRACLAVE" in hits[0].snippet
    assert hits[0].snippet.startswith("…")
    assert len(hits[0].snippet) < len(cuerpo)


def test_search_respeta_el_limite():
    secciones = [_sec(f"s{i}", body="comun") for i in range(50)]
    assert len(ms.search(secciones, "comun", limit=5)) == 5


# ── Carga desde disco ────────────────────────────────────────────────────────

def _escribir(directorio, nombre, texto):
    (directorio / nombre).write_text(texto, encoding="utf-8")


def test_load_sections_lee_ordena_y_cachea_por_directorio(tmp_path):
    _escribir(tmp_path, "b.md", "---\nslug: b\ntitle: B\nchapter: C\norder: 20\n---\nB")
    _escribir(tmp_path, "a.md", "---\nslug: a\ntitle: A\nchapter: C\norder: 10\n---\nA")
    secciones = ms.load_sections(tmp_path)
    assert [s.slug for s in secciones] == ["a", "b"]


def test_load_sections_ignora_archivos_rotos_sin_tirar_abajo_el_manual(tmp_path):
    """Un .md mal escrito no puede dejar la página inaccesible."""
    _escribir(tmp_path, "ok.md", "---\nslug: ok\ntitle: OK\nchapter: C\n---\nX")
    _escribir(tmp_path, "roto.md", "---\ntitle: sin slug\n---\nX")
    _escribir(tmp_path, "order.md",
              "---\nslug: o\ntitle: T\nchapter: C\norder: ninguno\n---\nX")
    assert [s.slug for s in ms.load_sections(tmp_path)] == ["ok"]


def test_load_sections_descarta_slugs_duplicados(tmp_path):
    _escribir(tmp_path, "a.md", "---\nslug: dup\ntitle: Primera\nchapter: C\n---\nX")
    _escribir(tmp_path, "b.md", "---\nslug: dup\ntitle: Segunda\nchapter: C\n---\nX")
    secciones = ms.load_sections(tmp_path)
    assert len(secciones) == 1
    assert secciones[0].title == "Primera"   # gana el primero por nombre de archivo


def test_load_sections_directorio_inexistente_devuelve_vacio(tmp_path):
    assert ms.load_sections(tmp_path / "no-existe") == []
