"""
Packs de señales y estrategias: el formato de intercambio (SPEC v1).

Un *pack* es un archivo JSON autosuficiente con las señales y la estrategia
que las usa, pensado para que lo escriba alguien que NO tiene el código de la
aplicación a la vista — una persona, o un modelo de lenguaje al que se le
entregan dos cosas: `strategy_packs/SPEC.md` (el contrato) y el catálogo de la
instalación (`build_catalog`, botón «Catálogo» en Señales).

El contrato está escrito en prosa en SPEC.md y implementado acá;
`tests/test_pack_spec.py` ata los dos, para que el documento publicado no se
desactualice en silencio respecto del validador (ya pasó con `composite`,
`source=group` y `scope`, que se removieron del código).

Dos formatos de entrada para el mismo contenido:
  - **JSON** (canónico): un archivo con `signals` y `strategies`. Se sube tal
    cual, primero en Señales y después en Estrategias — cada pantalla lee la
    parte que le toca.
  - **Excel** (histórico): las dos planillas que exporta la app.
Los dos caminos se normalizan a las MISMAS filas (las columnas del Excel) y de
ahí en adelante comparten validación y escritura: un pack no puede pasar por
un camino y fallar por el otro.

Lo que NO viaja en el pack es el catálogo de la instalación (qué indicadores
existen, qué sectores/mercados hay cargados): eso depende de cada base y por
eso se exporta aparte.

Portabilidad de los atributos: en el árbol de filtro guardado, un operando
`attribute` (sector, mercado, …) compara contra el **id** de la fila de
catálogo, y los ids son distintos en cada instalación — un pack que los
llevara hardcodeados no sería importable en otra base. Por eso el import
acepta **nombres** y los resuelve a ids acá (`resolve_attribute_values`);
los ids siguen aceptándose para no romper los archivos exportados por la app.
"""
import copy
import json
import logging
from pathlib import Path

from app.services import signal_engine, strategy_filter
from app.services.visibility import parse_publica

logger = logging.getLogger(__name__)

SPEC_VERSION = 1

# Columnas de las planillas. Fuente única: las usan el export a Excel, el
# conversor JSON→Excel y el test que verifica que el SPEC las documente.
SIGNAL_COLUMNS = ("key", "name", "description", "indicator_key",
                  "formula_type", "params", "publica")
STRATEGY_COLUMNS = ("name", "description", "filter_conditions", "publica")
COMPONENT_COLUMNS = ("strategy_name", "signal_key", "weight")

# Claves de nivel superior que el pack puede traer. Las de metadata son
# documentación para quien lo lee (la app las ignora).
PACK_METADATA_KEYS = frozenset({"spec_version", "pack", "title", "description",
                                "author", "notes", "version"})


class PackError(ValueError):
    """Archivo que ni siquiera llega a validarse fila por fila."""


# ══════════════════════════════════════════════════════════════════════════════
# Lógica pura (sin base de datos)
# ══════════════════════════════════════════════════════════════════════════════

def looks_like_json(file_bytes: bytes, filename: str | None = None) -> bool:
    """¿Este upload es un pack JSON o una planilla Excel?

    Por extensión cuando la hay; si no, por el primer byte no-blanco. El sniff
    importa porque el archivo puede llegar sin nombre y un .xlsx es un ZIP
    (empieza con 'PK'), así que la distinción es inequívoca.
    """
    if filename:
        name = filename.strip().lower()
        if name.endswith(".json"):
            return True
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            return False
    return file_bytes.lstrip()[:1] in (b"{", b"[")


def parse_pack(file_bytes: bytes) -> dict:
    """bytes de un archivo JSON → dict del pack, validado en su forma general.

    Solo chequea que el envoltorio sea utilizable; el contenido lo validan
    `validate_pack` (offline) y el import (contra la base).
    """
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PackError(f"el archivo no es texto UTF-8 válido: {exc}") from exc
    try:
        pack = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PackError(
            f"JSON inválido (línea {exc.lineno}, columna {exc.colno}): "
            f"{exc.msg}") from exc

    if not isinstance(pack, dict):
        raise PackError(
            "el pack debe ser un objeto JSON con las claves 'signals' y/o "
            "'strategies'; llegó "
            + ("una lista" if isinstance(pack, list) else type(pack).__name__))

    version = pack.get("spec_version", SPEC_VERSION)
    try:
        version = int(version)
    except (TypeError, ValueError):
        raise PackError(f"spec_version inválida: {pack.get('spec_version')!r}")
    if version != SPEC_VERSION:
        raise PackError(
            f"spec_version {version}: esta instalación entiende la versión "
            f"{SPEC_VERSION}. Pedile a quien armó el pack la versión "
            f"{SPEC_VERSION} del formato (strategy_packs/SPEC.md).")

    for key in ("signals", "strategies"):
        if key in pack and not isinstance(pack[key], list):
            raise PackError(f"'{key}' debe ser una lista de objetos")
    if not pack.get("signals") and not pack.get("strategies"):
        raise PackError("el pack no trae ni señales ni estrategias")
    return pack


def _params_to_text(params) -> str:
    """params del pack (objeto JSON, lo natural de escribir) → el texto que
    guarda la columna `params`. Un string se respeta tal cual: así un pack
    puede llevar el valor exacto que exportó la app.

    Se conserva el ORDEN de las claves: en `thresholds` el orden es semántico
    (gana el primer límite que el valor supera), y reordenar acá cambiaría los
    resultados en silencio.
    """
    if params is None:
        return "{}"
    if isinstance(params, str):
        return params
    return json.dumps(params, ensure_ascii=False)


def _es_publica(value) -> bool:
    """Visibilidad tolerante a basura: un `publica` inválido ya se reporta
    como error propio; acá se lo trata como privado para poder seguir
    validando el resto en vez de tumbar el validador entero."""
    try:
        return parse_publica(_publica_to_text(value))
    except ValueError:
        return False


def _publica_to_text(value) -> str:
    """`publica` del pack (bool, lo natural en JSON) → el texto de la columna.
    Ausente = privada, igual que en la planilla."""
    if value is None:
        return "no"
    if isinstance(value, bool):
        return "si" if value else "no"
    return str(value)


def signal_rows_from_pack(pack: dict) -> list[dict]:
    """Sección `signals` → filas normalizadas (las columnas de la planilla).

    Las claves desconocidas se dejan pasar a la fila: `source` es la única que
    importa, y el validador del import la rechaza con su mensaje propio (fue
    removida) en vez de ignorarla en silencio.
    """
    signals = pack.get("signals") or []
    if not signals:
        raise PackError(
            "este pack no trae señales. Si trae estrategias, importalo en la "
            "pantalla de Estrategias.")
    rows: list[dict] = []
    for i, sig in enumerate(signals):
        if not isinstance(sig, dict):
            raise PackError(f"signals[{i}] debe ser un objeto")
        row = {k: v for k, v in sig.items()
               if k not in ("params", "publica", "filter")}
        row["params"] = _params_to_text(sig.get("params"))
        row["publica"] = _publica_to_text(sig.get("publica"))
        rows.append(row)
    return rows


def strategy_rows_from_pack(pack: dict) -> tuple[list[dict], list[dict]]:
    """Sección `strategies` → (filas de estrategia, filas de componente),
    con la misma forma que las dos hojas de la planilla."""
    strategies = pack.get("strategies") or []
    if not strategies:
        raise PackError(
            "este pack no trae estrategias. Si trae señales, importalo en la "
            "pantalla de Señales.")
    rows_s: list[dict] = []
    rows_c: list[dict] = []
    for i, strat in enumerate(strategies):
        if not isinstance(strat, dict):
            raise PackError(f"strategies[{i}] debe ser un objeto")
        name = str(strat.get("name") or "").strip()
        # `filter` (objeto) es la forma canónica; `filter_conditions` (texto)
        # se acepta para poder pegar lo que exportó la app sin retocarlo.
        tree = strat.get("filter", strat.get("filter_conditions"))
        rows_s.append({
            "name": name,
            "description": strat.get("description"),
            "filter_conditions": (tree if isinstance(tree, str) or tree is None
                                  else json.dumps(tree, ensure_ascii=False)),
            "publica": _publica_to_text(strat.get("publica")),
        })
        components = strat.get("components") or []
        if not isinstance(components, list):
            raise PackError(f"strategies[{i}].components debe ser una lista")
        for comp in components:
            if not isinstance(comp, dict):
                raise PackError(
                    f"strategies[{i}].components: cada componente debe ser un "
                    f"objeto con signal_key y weight")
            row = dict(comp)
            row["strategy_name"] = name
            rows_c.append(row)
    return rows_s, rows_c


def _texto_a_params(value, donde: str):
    """Columna `params` (texto JSON) → objeto. Inversa de `_params_to_text`."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError) as exc:
        raise PackError(f"{donde}: la columna 'params' no es JSON válido: "
                        f"{exc}") from exc


def _texto_a_publica(value):
    """Columna `publica` (si/no) → bool, o None si la celda está vacía.

    None significa "el archivo no lo dice", y se omite del pack: ausente es
    privada en los dos formatos, así que omitirlo conserva la semántica sin
    inventar una decisión que el original no tomó.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return parse_publica(str(value))


def _numero_prolijo(value):
    """3.0 → 3. Los pesos salen de una celda de Excel como float; escribirlos
    así en el JSON hace ruido al leerlo y al diffearlo."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def pack_from_rows(signal_rows: list[dict] | None,
                   strategy_rows: list[dict] | None,
                   component_rows: list[dict] | None,
                   *, name: str | None = None,
                   description: str | None = None) -> dict:
    """Filas de las planillas → pack JSON. Inversa de `signal_rows_from_pack` +
    `strategy_rows_from_pack`.

    Existe para convertir al formato canónico lo que hoy solo está en planillas
    (las de `strategy_packs/`, o las que exporta la app). Las celdas vacías se
    omiten en vez de viajar como `null`: un pack se lee y se edita a mano.
    """
    pack: dict = {"spec_version": SPEC_VERSION}
    if name:
        pack["pack"] = name
    if description:
        pack["description"] = description

    signals = []
    for i, row in enumerate(signal_rows or []):
        key = str(row.get("key") or "").strip()
        if not key and not any(v not in (None, "") for v in row.values()):
            continue                      # fila vacía al final de la hoja
        donde = f"señales[{key or i}]"
        sig: dict = {}
        for col in SIGNAL_COLUMNS:
            valor = row.get(col)
            if col == "params":
                sig[col] = _texto_a_params(valor, donde)
            elif col == "publica":
                publica = _texto_a_publica(valor)
                if publica is not None:
                    sig[col] = publica
            elif valor not in (None, ""):
                sig[col] = valor
        # Columnas de más (`source` y cualquier otra): se conservan para que el
        # import las rechace con su mensaje propio en vez de desaparecer acá.
        sig.update({k: v for k, v in row.items()
                    if k not in SIGNAL_COLUMNS and v not in (None, "")})
        signals.append(sig)
    if signals:
        pack["signals"] = signals

    por_estrategia: dict[str, list[dict]] = {}
    for row in component_rows or []:
        ckey = str(row.get("signal_key") or "").strip()
        if not ckey:
            continue
        comp: dict = {"signal_key": ckey}
        if row.get("weight") is not None:
            comp["weight"] = _numero_prolijo(row["weight"])
        por_estrategia.setdefault(_clave(row.get("strategy_name")), []).append(comp)

    strategies = []
    for i, row in enumerate(strategy_rows or []):
        nombre = str(row.get("name") or "").strip()
        if not nombre:
            continue
        donde = f"estrategias[{nombre or i}]"
        strat: dict = {"name": nombre}
        if row.get("description") not in (None, ""):
            strat["description"] = row["description"]
        publica = _texto_a_publica(row.get("publica"))
        if publica is not None:
            strat["publica"] = publica
        tree = row.get("filter_conditions")
        if tree not in (None, "") and str(tree).strip():
            try:
                strat["filter"] = json.loads(tree) if isinstance(tree, str) else tree
            except (TypeError, ValueError) as exc:
                raise PackError(f"{donde}: la columna 'filter_conditions' no es "
                                f"JSON válido: {exc}") from exc
        strat["components"] = por_estrategia.get(_clave(nombre), [])
        strategies.append(strat)
    if strategies:
        pack["strategies"] = strategies

    return pack


# ── Atributos: nombre → id ────────────────────────────────────────────────────

def _is_id(value) -> bool:
    """Un id ya resuelto: entero, o texto de solo dígitos (así lo persiste a
    veces la UI). Un nombre de catálogo nunca es solo dígitos."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, str) and value.strip().isdigit()


def resolve_attribute_values(tree: dict, index: dict[str, dict]) -> tuple[dict, list[str]]:
    """Reescribe los valores de las condiciones sobre atributos (sector,
    mercado, industria, país, tipo de instrumento) de **nombre** al valor que
    espera el evaluador.

    index: {"sector": {"<nombre en minúscula>": <valor>}, ...}.
      - En el import, `<valor>` es el id de la fila de catálogo → el árbol
        queda listo para evaluarse.
      - En la validación offline no hay ids: se pasa el nombre como valor
        (identidad) y la función sirve solo para detectar nombres inexistentes.

    Devuelve (árbol nuevo, errores). No muta el árbol recibido. Los ids que ya
    vengan resueltos se dejan intactos.
    """
    from difflib import get_close_matches

    errors: list[str] = []
    result = copy.deepcopy(tree)

    def _map_one(attr: str, value, path: str):
        if _is_id(value):
            return int(value) if not isinstance(value, bool) else value
        text = str(value).strip()
        table = index.get(attr) or {}
        hit = table.get(text.lower())
        if hit is not None:
            return hit
        if not table:
            errors.append(
                f"{path}: no se puede resolver '{text}': esta instalación no "
                f"tiene ningún valor cargado para {attr}")
            return value
        cerca = get_close_matches(text.lower(), list(table), n=3, cutoff=0.6)
        sugerencia = (f" ¿Quisiste decir {', '.join(repr(c) for c in cerca)}?"
                      if cerca else
                      f" Valores cargados: {len(table)} "
                      f"(exportá el catálogo para verlos).")
        errors.append(f"{path}: {attr} '{text}' no existe en esta "
                      f"instalación.{sugerencia}")
        return value

    def _walk(node, path: str):
        if not isinstance(node, dict):
            return
        if "cond" in node:
            cond = node.get("cond")
            if not isinstance(cond, dict):
                return
            left, right = cond.get("left"), cond.get("right")
            if not (isinstance(left, dict) and isinstance(right, dict)):
                return
            if left.get("type") != "attribute" or right.get("type") != "const":
                return
            attr = left.get("key")
            if attr not in strategy_filter.ATTRIBUTE_KEYS:
                return      # atributo desconocido: lo reporta validate_tree
            value = right.get("value")
            if isinstance(value, list):
                right["value"] = [_map_one(attr, v, path) for v in value]
            elif value is not None:
                right["value"] = _map_one(attr, value, path)
            return
        for i, child in enumerate(node.get("children") or []):
            _walk(child, f"{path}.{i}")

    _walk(result, "filtro")
    return result, errors


# ── Validación offline (misma que aplica el import, sin tocar la base) ────────

def _catalog_indices(catalog: dict) -> dict:
    """Índices derivados del catálogo exportado, en las formas que piden
    validate_tree y resolve_attribute_values."""
    indicators = catalog.get("indicators") or []
    codes = {d["code"]: d.get("type", "num") for d in indicators if d.get("code")}
    categorical = {
        d["code"]: frozenset(str(v) for v in d["values"])
        for d in indicators if d.get("code") and d.get("values")
    }
    attributes = {
        attr: {str(name).strip().lower(): str(name) for name in (values or [])}
        for attr, values in (catalog.get("attributes") or {}).items()
    }
    signals = {s["key"] for s in (catalog.get("signals") or []) if s.get("key")}
    public_signals = {s["key"] for s in (catalog.get("signals") or [])
                      if s.get("key") and s.get("publica")}
    return {"indicator_codes": codes, "categorical": categorical,
            "attributes": attributes, "signal_keys": signals,
            "public_signal_keys": public_signals,
            "keep_history": {d["code"]: d.get("keep_history", True)
                             for d in indicators if d.get("code")}}


def validate_pack(pack: dict, catalog: dict | None = None) -> dict:
    """Valida un pack ya parseado. Devuelve {"errors": [...], "warnings": [...],
    "checked": [...], "skipped": [...]}.

    Reproduce offline lo que el import verifica contra la base — para eso hace
    falta el catálogo de la instalación (`build_catalog`). Sin catálogo valida
    igual todo lo que no depende de la base (forma del archivo, params, la
    gramática del árbol) y deja constancia en `skipped` de lo que no pudo
    mirar, en vez de dar un OK que no significa nada.

    Los `warnings` no impiden importar: son las trampas silenciosas —cosas que
    el pipeline acepta y después no puntúan— que en la pantalla se ven y en un
    archivo escrito a ciegas no.
    """
    errors: list[str] = []
    warnings: list[str] = []
    checked = ["forma del archivo", "parámetros de cada fórmula",
               "gramática del filtro", "referencias entre señales y estrategias"]
    skipped: list[str] = []

    idx = _catalog_indices(catalog or {})
    con_catalogo = bool(catalog)
    if con_catalogo:
        checked += ["indicadores existentes",
                    "valores de atributos (sector, mercado, …)"]
    else:
        skipped += ["que los indicadores existan en la instalación",
                    "que los sectores/mercados/países del filtro existan",
                    "las categorías válidas de cada indicador"]

    # ── Señales ───────────────────────────────────────────────────────────────
    pack_signals: dict[str, dict] = {}
    for i, sig in enumerate(pack.get("signals") or []):
        path = f"signals[{i}]"
        if not isinstance(sig, dict):
            errors.append(f"{path}: debe ser un objeto")
            continue
        key = str(sig.get("key") or "").strip()
        if not key:
            errors.append(f"{path}: falta 'key'")
            continue
        if key in pack_signals:
            errors.append(f"{path}: la key '{key}' está repetida en el pack")
        path = f"signals[{key}]"
        pack_signals[key] = sig

        if sig.get("source"):
            errors.append(f"{path}: 'source' ya no se soporta (las señales de "
                          f"grupo se removieron)")
        try:
            parse_publica(_publica_to_text(sig.get("publica")))
        except ValueError as exc:
            errors.append(f"{path}: {exc}")

        formula = str(sig.get("formula_type") or "")
        params = sig.get("params")
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}: params no es JSON válido: {exc.msg}")
                params = None
        if params is not None and not isinstance(params, dict):
            errors.append(f"{path}: params debe ser un objeto")
            params = None
        error = signal_engine.validate_params(formula, params or {})
        if error:
            errors.append(f"{path}: {error}")
            continue

        code = str(sig.get("indicator_key") or "").strip()
        if not code:
            errors.append(f"{path}: falta 'indicator_key'")
        elif con_catalogo and code not in idx["indicator_codes"]:
            errors.append(f"{path}: el indicador '{code}' no existe en esta "
                          f"instalación")
        elif con_catalogo:
            tipo = idx["indicator_codes"][code]
            if tipo == "str" and formula != "discrete_map":
                errors.append(
                    f"{path}: '{code}' devuelve categorías; con la fórmula "
                    f"'{formula}' la señal nunca puntúa (usá discrete_map)")
            if tipo == "num" and formula == "discrete_map":
                errors.append(
                    f"{path}: '{code}' devuelve números; discrete_map compara "
                    f"contra texto y la señal nunca puntúa")
            if not idx["keep_history"].get(code, True):
                warnings.append(
                    f"{path}: '{code}' no guarda historia — la señal solo "
                    f"tendrá valores desde hoy en adelante (sin backtest)")
            faltantes = sorted(set(idx["categorical"].get(code, ()))
                               - set((params or {}).get("map", {})))
            if formula == "discrete_map" and faltantes:
                warnings.append(
                    f"{path}: el mapa no cubre {faltantes} — en esas "
                    f"categorías la señal no puntúa (y no cuenta como cero)")

        if formula == "threshold":
            limites = [lim for lim, _ in (params or {}).get("thresholds", [])
                       if lim is not None]
            if limites != sorted(limites, reverse=True):
                warnings.append(
                    f"{path}: los thresholds no están de mayor a menor. Se "
                    f"evalúan en orden y gana el primero que el valor supera: "
                    f"así escrito, los tramos de abajo nunca se alcanzan")
            if not any(lim is None for lim, _ in (params or {}).get("thresholds", [])):
                warnings.append(
                    f"{path}: sin tramo final [null, score]: los valores que no "
                    f"superan ningún límite quedan sin puntaje")
        if formula == "range" and (params or {}).get("clamp") is False:
            warnings.append(
                f"{path}: clamp=false deja que el puntaje se salga de ±100 y "
                f"un extremo domine el ranking de la estrategia")

    # ── Estrategias ───────────────────────────────────────────────────────────
    usadas: set[str] = set()
    known_signals = set(pack_signals) | idx["signal_keys"]
    for i, strat in enumerate(pack.get("strategies") or []):
        path = f"strategies[{i}]"
        if not isinstance(strat, dict):
            errors.append(f"{path}: debe ser un objeto")
            continue
        name = str(strat.get("name") or "").strip()
        if not name:
            errors.append(f"{path}: falta 'name'")
            continue
        path = f"strategies[{name}]"
        try:
            parse_publica(_publica_to_text(strat.get("publica")))
        except ValueError as exc:
            errors.append(f"{path}: {exc}")
        es_publica = _es_publica(strat.get("publica"))

        usadas_aqui: set[str] = set()
        components = strat.get("components") or []
        if not components:
            errors.append(f"{path}: sin componentes — una estrategia sin "
                          f"señales no puntúa nada")
        for comp in components:
            if not isinstance(comp, dict):
                errors.append(f"{path}: componente inválido (se esperaba un "
                              f"objeto con signal_key y weight)")
                continue
            if comp.get("scope"):
                errors.append(f"{path}: 'scope' ya no se soporta (el Alcance "
                              f"de grupo se removió)")
            ckey = str(comp.get("signal_key") or "").strip()
            if not ckey:
                errors.append(f"{path}: componente sin signal_key")
                continue
            usadas_aqui.add(ckey)
            if ckey not in known_signals:
                errors.append(
                    f"{path}: la señal '{ckey}' no está en el pack"
                    + (" ni en la instalación" if con_catalogo else "")
                    + (". El pack tiene que ser autosuficiente: incluí todas "
                       "las señales que usa"))
            try:
                float(comp.get("weight", 1))
            except (TypeError, ValueError):
                errors.append(f"{path}: peso no numérico en '{ckey}': "
                              f"{comp.get('weight')!r}")

        tree = strat.get("filter", strat.get("filter_conditions"))
        if isinstance(tree, str):
            try:
                tree = json.loads(tree) if tree.strip() else None
            except json.JSONDecodeError as exc:
                errors.append(f"{path}: filtro con JSON inválido: {exc.msg}")
                tree = None
        if not tree:
            warnings.append(
                f"{path}: sin filtro de elegibilidad — la estrategia rankea "
                f"TODOS los activos de la base")
        else:
            tree, attr_errors = resolve_attribute_values(tree, idx["attributes"])
            if con_catalogo:
                errors += [f"{path}: {e}" for e in attr_errors]
            usadas_aqui |= {k for t, k, _ in strategy_filter.collect_operands(tree)
                            if t == "signal" and k}
            arbol_errores = strategy_filter.validate_tree(
                tree,
                indicator_codes=(idx["indicator_codes"] if con_catalogo
                                 else _lax_indicator_codes(tree)),
                signal_keys=known_signals,
                categorical_values=idx["categorical"],
            )
            errors += [f"{path}: {e}" for e in arbol_errores]

        usadas |= usadas_aqui
        if es_publica:
            # Solo las señales de ESTA estrategia: `usadas` acumula las de
            # todas y le atribuiría a la última los pecados de las anteriores.
            privadas = sorted(
                k for k in usadas_aqui
                if (k in pack_signals
                    and not _es_publica(pack_signals[k].get("publica")))
                or (k not in pack_signals and con_catalogo
                    and k in idx["signal_keys"]
                    and k not in idx["public_signal_keys"]))
            if privadas:
                errors.append(
                    f"{path}: la estrategia es pública y usa señales privadas "
                    f"{privadas} — marcá esas señales publica: true")

    huerfanas = sorted(set(pack_signals) - usadas)
    if huerfanas:
        warnings.append(
            f"señales que ninguna estrategia del pack usa: {huerfanas}. Cada "
            f"señal cargada cuesta cómputo en cada corrida del pipeline")

    return {"errors": errors, "warnings": warnings,
            "checked": checked, "skipped": skipped}


def _lax_indicator_codes(tree: dict) -> dict[str, str]:
    """Sin catálogo no se sabe qué indicadores existen ni de qué tipo son.
    Para poder validar igual el RESTO de la gramática del árbol, se declaran
    todos los códigos que el árbol menciona como numéricos: así validate_tree
    no reporta 'indicador desconocido' en cada condición (ruido que taparía
    los errores reales) pero sigue chequeando operadores, listas y estructura.
    """
    return {k: "num" for t, k, _ in strategy_filter.collect_operands(tree)
            if t == "indicator" and k}


# ══════════════════════════════════════════════════════════════════════════════
# Catálogo de la instalación (toca la base)
# ══════════════════════════════════════════════════════════════════════════════

def _attribute_models():
    from app.models import (Country, Industry, InstrumentType, Market, Sector)
    return {"sector": Sector, "market": Market, "industry": Industry,
            "country": Country, "instrument_type": InstrumentType}


def attribute_index(session) -> dict[str, dict[str, int]]:
    """{atributo: {nombre en minúscula: id}} para resolver los nombres del
    pack. Nombres repetidos con distinto caso: gana el primero por orden
    alfabético, de forma determinista."""
    index: dict[str, dict[str, int]] = {}
    for attr, model in _attribute_models().items():
        filas = session.query(model.id, model.name).order_by(model.name).all()
        tabla: dict[str, int] = {}
        for fid, nombre in filas:
            clave = str(nombre or "").strip().lower()
            if clave and clave not in tabla:
                tabla[clave] = fid
        index[attr] = tabla
    return index


def build_catalog() -> dict:
    """Catálogo de ESTA instalación: lo que un autor de packs necesita saber y
    no puede deducir del SPEC — qué indicadores hay, de qué tipo, qué
    categorías devuelven, qué sectores/mercados/países están cargados y qué
    señales ya existen.

    Es la mitad variable del estándar: el SPEC es igual en todas las
    instalaciones, esto no.
    """
    from datetime import datetime

    from app.database import get_session
    from app.models import SignalDefinition, Strategy
    from app.models.indicator_definition import IndicatorDefinition
    from app.services.indicator_catalog import CATEGORICAL_VALUES
    from app.services.signal_service import _VIRTUAL_CODES

    s = get_session()

    indicators = []
    for d in s.query(IndicatorDefinition).order_by(IndicatorDefinition.code).all():
        entry = {
            "code": d.code,
            "name": d.name,
            "type": d.type,
            "category": d.category,
            "scale": d.scale,
            "description": d.description,
            "keep_history": bool(d.keep_history),
        }
        valores = CATEGORICAL_VALUES.get(d.code)
        if valores:
            entry["values"] = sorted(valores)
        indicators.append(entry)

    # Indicadores virtuales: no tienen fila en el catálogo pero el import los
    # acepta como indicator_key, así que sin esto un autor no sabría que
    # existen.
    for code in sorted(_VIRTUAL_CODES):
        indicators.append({
            "code": code, "name": "Último cierre", "type": "num",
            "category": "precio", "scale": None, "keep_history": True,
            "virtual": True,
            "description": "Precio de cierre del día, sin tabla de indicador.",
        })

    attributes = {
        attr: [r.name for r in
               s.query(model.name).order_by(model.name).all() if r.name]
        for attr, model in _attribute_models().items()
    }

    signals = [
        {"key": sg.key, "name": sg.name, "indicator_key": sg.indicator_key,
         "formula_type": sg.formula_type, "publica": bool(sg.is_public)}
        for sg in s.query(SignalDefinition).order_by(SignalDefinition.key).all()
    ]
    strategies = [
        {"name": st.name, "publica": bool(st.is_public)}
        for st in s.query(Strategy).order_by(Strategy.name).all()
    ]

    return {
        "spec_version": SPEC_VERSION,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "formula_types": list(signal_engine.FORMULA_TYPES),
        "operators": {
            "numeric": sorted(strategy_filter.NUMERIC_OPERATORS),
            "categorical": sorted(strategy_filter.CATEGORICAL_OPERATORS),
        },
        "operand_types": sorted(strategy_filter.OPERAND_TYPES),
        "attribute_keys": sorted(strategy_filter.ATTRIBUTE_KEYS),
        "indicators": indicators,
        "attributes": attributes,
        "signals": signals,
        "strategies": strategies,
    }


# ── Ensayo e importación (pantalla /admin/packs) ──────────────────────────────

def _clave(texto) -> str:
    """Normalización de key/nombre para el cruce: el import matchea sin
    distinguir caso (db_compat.ci_equals), así que el ensayo tiene que
    predecirlo igual o diría "crea" donde el import va a actualizar."""
    return str(texto or "").strip().lower()


def preview_pack(pack: dict, acting_user_id: int | None = None) -> dict:
    """Ensayo del import contra ESTA base, **sin escribir nada**.

    Es lo que el validador offline no puede dar: además de la forma del
    archivo, mira contra qué se va a estrellar o qué va a pisar. Devuelve
    {"errors", "warnings", "rows", "summary"} — con errores, el import se
    rechazaría entero (es todo-o-nada), así que la pantalla no deja seguir.

    `rows` describe fila por fila lo que va a pasar, en el mismo formato que
    después muestra el resultado real, para que la tabla no cambie de forma
    entre el antes y el después.
    """
    from app.database import get_session
    from app.models import SignalDefinition, Strategy, User

    resultado = validate_pack(pack, build_catalog())
    errors = list(resultado["errors"])
    warnings = list(resultado["warnings"])

    s = get_session()
    usuarios = {u.id: u.username for u in s.query(User.id, User.username).all()}
    señales_db = {_clave(sg.key): sg
                  for sg in s.query(SignalDefinition).all()}
    estrategias_db = {_clave(st.name): st for st in s.query(Strategy).all()}

    rows: list[dict] = []
    creados = actualizados = 0

    def _fila(tipo, nombre, existente, detalle):
        nonlocal creados, actualizados
        dueño = "—"
        if existente is None:
            accion = "crea"
            creados += 1
        else:
            accion = "actualiza"
            actualizados += 1
            dueño = usuarios.get(existente.owner_id, "—")
            if (existente.owner_id is not None
                    and existente.owner_id != acting_user_id):
                warnings.append(
                    f"{tipo.lower()} '{nombre}': ya existe y es de {dueño} — "
                    f"importar la pisa (queda su definición, con su dueño)")
        # `status` lo llena el import (texto visible) y `estado` es el código
        # que colorea la fila (imported/error/skipped, ver grids.py).
        rows.append({"tipo": tipo, "nombre": nombre, "accion": accion,
                     "dueno": dueño, "detail": detalle,
                     "status": "", "estado": ""})

    for sig in (pack.get("signals") or []):
        if not isinstance(sig, dict) or not str(sig.get("key") or "").strip():
            continue
        key = str(sig["key"]).strip()
        detalle = " · ".join(x for x in (
            sig.get("formula_type"),
            f"sobre {sig['indicator_key']}" if sig.get("indicator_key") else None,
            "pública" if _es_publica(sig.get("publica")) else "privada",
        ) if x)
        _fila("Señal", key, señales_db.get(_clave(key)), detalle)

    for strat in (pack.get("strategies") or []):
        if not isinstance(strat, dict) or not str(strat.get("name") or "").strip():
            continue
        nombre = str(strat["name"]).strip()
        componentes = strat.get("components") or []
        tiene_filtro = bool(strat.get("filter") or strat.get("filter_conditions"))
        detalle = " · ".join([
            f"{len(componentes)} componente(s)",
            "con filtro" if tiene_filtro else "sin filtro",
            "pública" if _es_publica(strat.get("publica")) else "privada",
        ])
        _fila("Estrategia", nombre, estrategias_db.get(_clave(nombre)), detalle)

    return {"errors": errors, "warnings": warnings, "rows": rows,
            "summary": {"crea": creados, "actualiza": actualizados}}


def import_pack(file_bytes: bytes, owner_id: int | None = None) -> dict:
    """Los dos pasos del import de un pack, en el orden que exigen las
    referencias: señales primero, estrategias después.

    Devuelve {"signals": [...], "strategies": [...], "aborted": bool}.

    **No es una sola transacción**: cada paso es todo-o-nada por su cuenta. Si
    las señales entran y las estrategias fallan, las señales quedan — por eso
    la pantalla obliga a pasar por `preview_pack` antes, que valida las dos
    partes contra la base. Ante un error en las señales se corta acá mismo
    (`aborted`): seguir daría una segunda lista de errores en cascada, todos
    "señal no encontrada", que tapan el problema real.
    """
    from app.services import signal_service, strategy_service

    pack = parse_pack(file_bytes)
    salida: dict = {"signals": [], "strategies": [], "aborted": False}

    if pack.get("signals"):
        salida["signals"] = signal_service.import_signal_rows(
            signal_rows_from_pack(pack), owner_id=owner_id)
        if any(r["status"] != "ok" for r in salida["signals"]):
            salida["aborted"] = True
            return salida

    if pack.get("strategies"):
        rows_s, rows_c = strategy_rows_from_pack(pack)
        salida["strategies"] = strategy_service.import_strategy_rows(
            rows_s, rows_c, owner_id=owner_id)
    return salida


def catalog_bytes() -> bytes:
    """El catálogo como archivo descargable (JSON legible: se pega en el
    contexto de un modelo o se abre a mano)."""
    return json.dumps(build_catalog(), ensure_ascii=False,
                      indent=2).encode("utf-8")


# La especificación viaja con la aplicación (está en el repo y el deploy lo
# copia entero), así que se sirve leyéndola de disco. Empotrarla como string en
# el código sería duplicar 18 KB de documento y garantizar que un día digan
# cosas distintas — justo lo que test_pack_spec.py existe para impedir.
SPEC_PATH = Path(__file__).resolve().parents[2] / "strategy_packs" / "SPEC.md"


def spec_bytes() -> bytes:
    """El contrato publicado, para descargarlo desde la pantalla.

    Quien usa la aplicación no tiene acceso al repositorio: sin esto, la mitad
    fija del estándar —la que hay que entregarle a quien escriba el pack— sería
    inalcanzable desde la app.
    """
    if not SPEC_PATH.exists():
        raise FileNotFoundError(
            f"no se encontró la especificación en {SPEC_PATH}. Debería viajar "
            f"con la aplicación (strategy_packs/SPEC.md).")
    return SPEC_PATH.read_bytes()
