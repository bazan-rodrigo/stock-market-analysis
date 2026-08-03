"""Trinquete: restos de tablas que una migración dropeó (hueco #3 del relevamiento
de trinquetes, docs/notes/project_trinquetes_faltantes.md).

**Por qué existe.** El cutover a tablas anchas (0094) dejó a `cleanup_service`
mirando prefijos que ya no alcanzaban a nada, y la limpieza quedó ROTA con sus
tests en verde. El nombre viejo no estaba en un comentario: estaba en la lógica.
Esta es la red para esa clase de resto.

**Por qué no es un grep de nombres.** Se evaluó y se descartó: la prosa que
explica que una tabla YA NO se usa es legítima y abunda ("group_scores ya no se
escribe acá: el Mapa lo calcula al vuelo"). Un grep la marcaría toda y el
trinquete moriría de ruido en una semana. Así que se mira **solo código
ejecutable** —literales de string, con docstrings excluidos por construcción vía
`ast`— donde un nombre muerto no es historia sino un bug.

Dos chequeos, los dos DERIVADOS (nada de listas escritas a mano que haya que
mantener en paralelo — esa es justo la falla que hundió a los tests de limpieza):

1. Los nombres muertos salen de las **migraciones**: tablas dropeadas en algún
   `upgrade()` que ninguna migración posterior vuelve a crear y que tampoco
   están en `Base.metadata`. Una migración nueva que dropee algo suma su nombre
   sola.
2. Los accesores per-entidad salen de **`signal_store`**: quien los llama tiene
   que conocer también el camino ancho. Un servicio que sepa de `sig_{id}` pero
   nunca haya oído hablar de las anchas es el bug de la limpieza otra vez.

Cada chequeo trae su propio test de que MUERDE: un módulo sintético con el
defecto tiene que salir marcado. Un trinquete que nunca se probó contra el
defecto que dice cubrir no es un trinquete.
"""
import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
APP = RAIZ / "app"
VERSIONS = RAIZ / "alembic" / "versions"

_RE_DROP = re.compile(
    r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?[`\"]?([a-z_0-9]+)", re.I)
_RE_CREATE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?([a-z_0-9]+)", re.I)


def _revision(path: Path) -> int:
    m = re.match(r"(\d+)", path.name)
    return int(m.group(1)) if m else 10**6


def _tablas_por_migracion() -> tuple[dict, dict]:
    """{tabla: primera revisión que la dropea} y {tabla: primera que la crea}.

    Se mira SOLO `upgrade()`: `downgrade()` dropea lo que la migración creó, y
    tomarlo en cuenta daría por muerta a media base.
    """
    dropeadas: dict[str, int] = {}
    creadas: dict[str, int] = {}
    for path in sorted(VERSIONS.glob("*.py"), key=_revision):
        rev = _revision(path)
        arbol = ast.parse(path.read_text(encoding="utf-8"))
        up = next((n for n in arbol.body
                   if isinstance(n, ast.FunctionDef) and n.name == "upgrade"),
                  None)
        if up is None:
            continue
        for nodo in ast.walk(up):
            if isinstance(nodo, ast.Call) and nodo.args:
                destino = {"drop_table": dropeadas,
                           "create_table": creadas}.get(
                               getattr(nodo.func, "attr", None))
                arg = nodo.args[0]
                if destino is not None and isinstance(arg, ast.Constant) \
                        and isinstance(arg.value, str):
                    destino.setdefault(arg.value, rev)
            # SQL crudo: varias migraciones dropean con sa.text(...).
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                for m in _RE_DROP.finditer(nodo.value):
                    dropeadas.setdefault(m.group(1), rev)
                for m in _RE_CREATE.finditer(nodo.value):
                    creadas.setdefault(m.group(1), rev)
    return dropeadas, creadas


def tablas_muertas() -> set[str]:
    """Tablas que una migración dropeó y nada resucita."""
    from app.database import Base
    from app.models import signal_store
    import app.models  # noqa: F401 — puebla Base.metadata

    dropeadas, creadas = _tablas_por_migracion()
    vivas = set(Base.metadata.tables) | {signal_store.SIG_WIDE_TABLE,
                                         signal_store.STRAT_WIDE_TABLE}
    return {t for t, rev in dropeadas.items()
            if t not in vivas and creadas.get(t, -1) < rev}


def _literales_ejecutables(fuente: str):
    """(línea, texto) de cada string literal que NO sea un docstring.

    La distinción es todo el punto: en un docstring el nombre viejo es historia;
    en un literal vivo es la tabla que la query va a buscar.
    """
    arbol = ast.parse(fuente)
    docstrings = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and nodo.body:
            if ast.get_docstring(nodo, clean=False) is not None:
                docstrings.add(id(nodo.body[0].value))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) \
                and id(nodo) not in docstrings:
            yield nodo.lineno, nodo.value


def restos_muertos(fuente: str, muertas: set[str]) -> list[tuple[int, str]]:
    """(línea, tabla) por cada nombre muerto usado en código ejecutable.

    Palabra completa: `signal_value` está muerta pero `signal_values_wide` es la
    tabla viva que la reemplazó, y una coincidencia por substring marcaría
    justamente al sucesor.
    """
    encontrados = []
    for linea, texto in _literales_ejecutables(fuente):
        for tabla in sorted(muertas):
            if re.search(rf"\b{re.escape(tabla)}\b", texto):
                encontrados.append((linea, tabla))
    return encontrados


def test_ninguna_tabla_muerta_sobrevive_en_codigo_ejecutable():
    muertas = tablas_muertas()
    assert muertas, "la derivación no encontró ninguna tabla dropeada: revisá _tablas_por_migracion"

    culpables = []
    for path in sorted(APP.rglob("*.py")):
        fuente = path.read_text(encoding="utf-8")
        for linea, tabla in restos_muertos(fuente, muertas):
            culpables.append(f"{path.relative_to(RAIZ)}:{linea} → {tabla}")

    assert not culpables, (
        "Nombres de tablas que una migración dropeó, usados en código vivo:\n  "
        + "\n  ".join(culpables))


def test_el_detector_de_tablas_muertas_muerde():
    """Que el chequeo de arriba esté en verde no prueba nada por sí solo."""
    fuente = (
        '"""Docstring: group_scores se dropeó en la 0092."""\n'
        'VIVA = "SELECT * FROM signal_values_wide"\n'
        '# comentario: signal_value ya no existe\n'
        'MUERTA = "SELECT * FROM signal_value"\n')
    hallado = restos_muertos(fuente, {"group_scores", "signal_value"})

    assert hallado == [(4, "signal_value")], hallado
    # Las tres exclusiones que hacen usable al trinquete, uña por uña:
    # el docstring (línea 1), la tabla viva que CONTIENE el nombre muerto
    # (línea 2) y el comentario (línea 3).


# ── Chequeo 2: quien toca las tablas per-entidad conoce las anchas ────────────

def accesores_per_entidad() -> set[str]:
    """Los accesores de `signal_store` que devuelven la tabla PER-ENTIDAD.

    Derivados del módulo: cualquier `*_sig_table` / `*_strat_table` /
    `*_table_name`, menos los `read_*`, que son justamente el despachador que
    elige entre ancha y per-entidad según el flag.
    """
    from app.models import signal_store

    patron = re.compile(r"_(?:sig|strat)_table$|^(?:sig|strat)_table_name$")
    return {n for n in dir(signal_store)
            if patron.search(n) and not n.startswith("read_")}


def marcas_de_conciencia() -> set[str]:
    """Cómo se ve, en el texto de un módulo, que conoce las tablas anchas: el
    nombre de las tablas, el de las constantes que las nombran, o el del
    despachador que elige entre ancha y per-entidad."""
    from app.models import signal_store

    constantes = {n for n in dir(signal_store) if n.endswith("_WIDE_TABLE")}
    return (constantes
            | {getattr(signal_store, n) for n in constantes}
            | {signal_store.use_wide_signal_tables.__name__,
               signal_store.read_sig_table.__name__,
               signal_store.read_strat_table.__name__})


def prefijos_per_entidad() -> set[str]:
    """`sig_` y `strat_res_`, derivados de las funciones que arman los nombres."""
    from app.models import signal_store

    return {signal_store.sig_table_name(0)[:-1],
            signal_store.strat_table_name(0)[:-1]}


def barre_por_prefijo_sin_anchas(fuente: str, prefijos: set[str],
                                 marcas: set[str]) -> set[str]:
    """Prefijos per-entidad usados en código EJECUTABLE por un módulo que nunca
    nombra las anchas.

    Esta es la forma exacta del bug de `cleanup_service`: una lista de prefijos
    que se escribió cuando `sig_{id}` era todo lo que había, y que después del
    cutover dejó de alcanzar a la mitad de los datos sin que nada avisara. El
    prefijo se busca solo cuando se lo usa COMO prefijo (`sig_%`, `sig_{`,
    `sig_3`), no cuando es parte de un nombre de variable.
    """
    usados = set()
    for _linea, texto in _literales_ejecutables(fuente):
        # El LIKE de MySQL escapa el guión bajo ('sig\_%'): sin normalizar,
        # justo la rama que barre por prefijo se escaparía del chequeo.
        plano = texto.replace("\\", "")
        for prefijo in prefijos:
            if re.search(rf"{re.escape(prefijo)}(?:%|\{{|\d|$)", plano):
                usados.add(prefijo)
    if not usados or any(re.search(rf"\b{re.escape(m)}\b", fuente)
                         for m in marcas):
        return set()
    return usados


def ignora_las_anchas(fuente: str, accesores: set[str],
                      marcas: set[str]) -> set[str]:
    """Accesores per-entidad usados por un módulo que nunca nombra las anchas."""
    usados = {a for a in accesores if re.search(rf"\b{a}\b", fuente)}
    if not usados or any(re.search(rf"\b{m}\b", fuente) for m in marcas):
        return set()
    return usados


def test_quien_usa_las_per_entidad_conoce_las_anchas():
    accesores, marcas = accesores_per_entidad(), marcas_de_conciencia()
    assert accesores, "no se derivó ningún accesor per-entidad de signal_store"

    culpables = {}
    for path in sorted(APP.rglob("*.py")):
        # signal_store ES el despachador: define las dos formas por definición.
        if path.name == "signal_store.py":
            continue
        usados = ignora_las_anchas(path.read_text(encoding="utf-8"),
                                   accesores, marcas)
        if usados:
            culpables[str(path.relative_to(RAIZ))] = sorted(usados)

    assert not culpables, (
        "Módulos que usan las tablas per-entidad sin conocer las anchas "
        "(el bug de cleanup_service otra vez):\n  " + "\n  ".join(
            f"{k} → {v}" for k, v in culpables.items()))


def test_el_detector_de_conciencia_muerde():
    accesores, marcas = accesores_per_entidad(), marcas_de_conciencia()

    ciego = "t = signal_store.get_sig_table(sig_id)\n"
    consciente = ("if signal_store.use_wide_signal_tables():\n"
                  "    ...\n"
                  "t = signal_store.get_sig_table(sig_id)\n")

    assert ignora_las_anchas(ciego, accesores, marcas) == {"get_sig_table"}
    assert ignora_las_anchas(consciente, accesores, marcas) == set()


def test_quien_barre_por_prefijo_conoce_las_anchas():
    prefijos, marcas = prefijos_per_entidad(), marcas_de_conciencia()
    assert prefijos == {"sig_", "strat_res_"}

    culpables = {}
    for path in sorted(APP.rglob("*.py")):
        if path.name == "signal_store.py":
            continue
        usados = barre_por_prefijo_sin_anchas(
            path.read_text(encoding="utf-8"), prefijos, marcas)
        if usados:
            culpables[str(path.relative_to(RAIZ))] = sorted(usados)

    assert not culpables, (
        "Módulos que barren las tablas per-entidad por prefijo sin incluir las "
        "anchas — el bug de cleanup_service otra vez:\n  " + "\n  ".join(
            f"{k} → {v}" for k, v in culpables.items()))


def test_el_detector_de_barrido_por_prefijo_muerde():
    prefijos, marcas = prefijos_per_entidad(), marcas_de_conciencia()

    # La forma real del bug: barrer el catálogo por prefijo y creer que con eso
    # se cubrió todo. Es lo que hacía purge_assets antes del 2-ago-2026.
    ciego = 'dyn = list_tables_by_prefix(s, "ind_", "sig_", "strat_res_")\n'
    like  = 'sql = "... WHERE table_name LIKE \'sig\\\\_%\'"\n'
    sano  = (ciego + 'tables = (*dyn, signal_store.SIG_WIDE_TABLE)\n')
    ajeno = 'def f(sig_id):\n    return sig_id\n'

    assert barre_por_prefijo_sin_anchas(ciego, prefijos, marcas) == {
        "sig_", "strat_res_"}
    assert barre_por_prefijo_sin_anchas(like, prefijos, marcas) == {"sig_"}
    assert barre_por_prefijo_sin_anchas(sano, prefijos, marcas) == set()
    # Un `sig_id` suelto es una variable, no un prefijo de tabla.
    assert barre_por_prefijo_sin_anchas(ajeno, prefijos, marcas) == set()
