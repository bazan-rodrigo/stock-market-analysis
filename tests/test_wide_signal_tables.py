"""Fase 1 de las tablas anchas de señales/estrategias
(docs/notes/design_sig_wide_tables.md): flag + ensure_wide_signal_tables +
primitivas de columna (ADD/DROP dinámico). Todavía NADA lee/escribe estas tablas
(el cutover es fase 2-4). Estos tests fijan el esquema base y las primitivas.
"""
import sqlalchemy as sa

from app.models import signal_store


def test_flag_default_off(monkeypatch):
    # En fase 1 el default es OFF: el camino vivo sigue siendo per-entidad.
    monkeypatch.delenv("USE_WIDE_SIGNAL_TABLES", raising=False)
    assert signal_store.use_wide_signal_tables() is False


def test_flag_on_por_env(monkeypatch):
    monkeypatch.setenv("USE_WIDE_SIGNAL_TABLES", "1")
    assert signal_store.use_wide_signal_tables() is True
    monkeypatch.setenv("USE_WIDE_SIGNAL_TABLES", "off")
    assert signal_store.use_wide_signal_tables() is False


def test_column_name_helpers():
    # La columna de una señal es el mismo `sig_{id}` que hoy nombra su tabla.
    assert signal_store.sig_column_name(6) == "sig_6"
    assert signal_store.strat_score_column(7) == "strat_7_score"
    assert signal_store.strat_pct_column(7) == "strat_7_pct"


def test_ensure_wide_signal_tables_esquema_e_idempotente():
    eng = sa.create_engine("sqlite://")
    signal_store.ensure_wide_signal_tables(bind=eng)
    signal_store.ensure_wide_signal_tables(bind=eng)  # segunda vez: no-op

    insp = sa.inspect(eng)
    for name in ("signal_values_wide", "strategy_results_wide"):
        assert insp.has_table(name)
        # PK (date, asset_id) — date primero, para el append cronológico
        assert insp.get_pk_constraint(name)["constrained_columns"] == [
            "date", "asset_id"]
        # índice secundario (asset_id, date) para las lecturas por activo
        assert any(ix["column_names"] == ["asset_id", "date"]
                   for ix in insp.get_indexes(name))
        # base: SIN columnas de valor todavía
        assert {c["name"] for c in insp.get_columns(name)} == {
            "asset_id", "date"}


def test_ensure_sig_column_add_idempotente_y_drop():
    eng = sa.create_engine("sqlite://")
    signal_store.ensure_wide_signal_tables(bind=eng)

    signal_store.ensure_sig_column(6, bind=eng)
    signal_store.ensure_sig_column(6, bind=eng)  # idempotente (checkfirst)

    cols = {c["name"]: c
            for c in sa.inspect(eng).get_columns("signal_values_wide")}
    assert set(cols) == {"asset_id", "date", "sig_6"}
    assert isinstance(cols["sig_6"]["type"], sa.Float)  # float4

    signal_store.drop_sig_column(6, bind=eng)
    signal_store.drop_sig_column(6, bind=eng)  # idempotente
    assert {c["name"] for c in sa.inspect(eng).get_columns(
        "signal_values_wide")} == {"asset_id", "date"}


def test_ensure_strat_columns_add_idempotente_y_drop():
    eng = sa.create_engine("sqlite://")
    signal_store.ensure_wide_signal_tables(bind=eng)

    signal_store.ensure_strat_columns(7, bind=eng)
    signal_store.ensure_strat_columns(7, bind=eng)  # idempotente

    cols = {c["name"] for c in sa.inspect(eng).get_columns(
        "strategy_results_wide")}
    assert cols == {"asset_id", "date", "strat_7_score", "strat_7_pct"}

    signal_store.drop_strat_columns(7, bind=eng)
    assert {c["name"] for c in sa.inspect(eng).get_columns(
        "strategy_results_wide")} == {"asset_id", "date"}


def test_columnas_de_dos_entidades_conviven():
    # Varias señales/estrategias comparten la misma tabla ancha: cada una suma
    # su(s) columna(s), sin pisarse.
    eng = sa.create_engine("sqlite://")
    signal_store.ensure_wide_signal_tables(bind=eng)
    signal_store.ensure_sig_column(6, bind=eng)
    signal_store.ensure_sig_column(9, bind=eng)
    signal_store.ensure_strat_columns(7, bind=eng)

    sig_cols = {c["name"] for c in sa.inspect(eng).get_columns(
        "signal_values_wide")}
    assert sig_cols == {"asset_id", "date", "sig_6", "sig_9"}

    # borrar una no toca la otra
    signal_store.drop_sig_column(6, bind=eng)
    assert {c["name"] for c in sa.inspect(eng).get_columns(
        "signal_values_wide")} == {"asset_id", "date", "sig_9"}
