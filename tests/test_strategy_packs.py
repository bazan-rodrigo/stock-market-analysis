"""Los xlsx de strategy_packs/ siguen siendo importables: cada pack se
valida con los MISMOS validadores que usa el import real (forma de params
por fórmula, categorías del catálogo, árbol del filtro, referencias de
componentes). Evita que un cambio de reglas o catálogo pudra los packs
commiteados sin que nadie lo note."""
import json
from pathlib import Path

import openpyxl
import pytest

from app.services import signal_engine, strategy_filter
from app.services.indicator_catalog import CATEGORICAL_VALUES

PACKS_DIR = Path(__file__).resolve().parent.parent / "strategy_packs"


def _rows(path, sheet=0):
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[sheet]
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h).strip().lower() for h in rows[0]]
    return [dict(zip(headers, r)) for r in rows[1:] if any(r)]


def _own_signal_keys(estrategia_path: Path) -> set:
    """Señales del propio pack: cada pack debe ser autosuficiente (todas
    las señales que su estrategia usa viven en su <pack>_senales.xlsx —
    duplicadas entre packs si hace falta; el import upsertea por key)."""
    senales = estrategia_path.with_name(
        estrategia_path.name.replace("_estrategia", "_senales"))
    assert senales.exists(), f"falta {senales.name}"
    return {r["key"] for r in _rows(senales)}


def test_hay_packs():
    assert PACKS_DIR.is_dir()
    assert list(PACKS_DIR.glob("*_senales.xlsx"))
    assert list(PACKS_DIR.glob("*_estrategia.xlsx"))


@pytest.mark.parametrize("path", sorted(PACKS_DIR.glob("*_senales.xlsx")),
                         ids=lambda p: p.stem)
def test_senales_del_pack_validas(path):
    own_keys = {r["key"] for r in _rows(path)}
    for r in _rows(path):
        params = json.loads(r["params"])  # JSON parseable
        err = signal_engine.validate_params(r["formula_type"], params)
        assert err is None, (r["key"], err)
        assert r["source"] in ("asset", "group"), r["key"]
        # discrete_map sobre indicador categórico: categorías del catálogo
        if r["formula_type"] == "discrete_map":
            allowed = CATEGORICAL_VALUES.get(r["indicator_key"])
            if allowed:
                unknown = set(params["map"]) - allowed
                assert not unknown, (r["key"], unknown)
        # composites: sus referencias resueltas dentro del PROPIO archivo
        if r["formula_type"] == "composite":
            refs = {c["signal_key"] for c in params["components"]}
            assert refs <= own_keys, (r["key"], refs - own_keys)


@pytest.mark.parametrize("path", sorted(PACKS_DIR.glob("*_estrategia.xlsx")),
                         ids=lambda p: p.stem)
def test_estrategia_del_pack_valida(path):
    estrategias = _rows(path, sheet=0)
    componentes = _rows(path, sheet=1)
    assert estrategias and componentes

    known_keys = _own_signal_keys(path)

    for e in estrategias:
        tree = json.loads(e["filter_conditions"])
        # Tipos de los operandos indicador: categórico si está en el
        # catálogo, numérico si no (los packs solo usan códigos reales;
        # un typo produce un árbol que igual valida la estructura)
        ops = strategy_filter.collect_operands(tree)
        ind_codes = {
            key: ("str" if key in CATEGORICAL_VALUES else "num")
            for t, key, _ in ops if t == "indicator"
        }
        sig_keys = {key for t, key, _ in ops if t == "signal"}
        assert sig_keys <= known_keys, sig_keys - known_keys
        errors = strategy_filter.validate_tree(
            tree, indicator_codes=ind_codes, signal_keys=sig_keys,
            categorical_values=CATEGORICAL_VALUES)
        assert errors == [], (e["name"], errors)

    for c in componentes:
        assert c["signal_key"] in known_keys, c["signal_key"]
        assert float(c["weight"]) > 0
