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


def test_read_views_filtran_nulls():
    """Las vistas de lectura (subquery) excluyen las filas donde ESTA señal/
    estrategia no puntúa (columna NULL porque la escribió otra) — la corrección
    clave del modelo ancho (lección 'diferencias falsas' de indicadores)."""
    eng = sa.create_engine("sqlite://")
    signal_store.ensure_wide_signal_tables(bind=eng)
    signal_store.ensure_sig_column(5, bind=eng)
    signal_store.ensure_sig_column(6, bind=eng)
    signal_store.ensure_strat_columns(7, bind=eng)
    with eng.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO signal_values_wide (asset_id, date, sig_5, sig_6) "
            "VALUES (1, '2026-01-05', 10, NULL), (2, '2026-01-05', NULL, 20)"))
        conn.execute(sa.text(
            "INSERT INTO strategy_results_wide "
            "(asset_id, date, strat_7_score, strat_7_pct) "
            "VALUES (1, '2026-01-05', 3.5, 90), (2, '2026-01-05', NULL, NULL)"))

    v5 = signal_store._sig_view(5)
    v7 = signal_store._strat_view(7)
    with eng.connect() as conn:
        r5 = conn.execute(sa.select(v5.c.asset_id, v5.c.score)
                          .order_by(v5.c.asset_id)).fetchall()
        r7 = conn.execute(sa.select(v7.c.asset_id, v7.c.score, v7.c.pct)).fetchall()
    assert r5 == [(1, 10.0)]          # activo 2: sig_5 NULL → excluido
    assert r7 == [(1, 3.5, 90.0)]     # activo 2: strat_7 NULL → excluido
    assert v5.name == "signal_values_wide"   # drop-in: .name como la tabla


def test_reconcile_wide_columns_agrega_y_dropea():
    """reconcile asegura una columna por señal/estrategia viva y dropea las de
    ids que ya no existen (red de seguridad de arranque)."""
    from sqlalchemy.orm import Session
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text('CREATE TABLE "signal" (id INTEGER PRIMARY KEY)'))
        conn.execute(sa.text("CREATE TABLE strategy (id INTEGER PRIMARY KEY)"))
        conn.execute(sa.text('INSERT INTO "signal" (id) VALUES (5), (6)'))
        conn.execute(sa.text("INSERT INTO strategy (id) VALUES (7)"))
    sess = Session(eng)
    try:
        signal_store.reconcile_wide_columns(sess)
        assert {"sig_5", "sig_6"} <= signal_store._wide_columns(
            eng, signal_store.SIG_WIDE_TABLE)
        assert {"strat_7_score", "strat_7_pct"} <= signal_store._wide_columns(
            eng, signal_store.STRAT_WIDE_TABLE)

        # baja de la señal 5 → reconcile dropea su columna, deja la 6
        with eng.begin() as conn:
            conn.execute(sa.text('DELETE FROM "signal" WHERE id = 5'))
        signal_store.reconcile_wide_columns(sess)
        cols = signal_store._wide_columns(eng, signal_store.SIG_WIDE_TABLE)
        assert "sig_5" not in cols
        assert "sig_6" in cols
    finally:
        sess.close()


def test_migracion_0093_pivotea_sin_perder_datos():
    """El pivot de la 0093 (merge-en-Python) copia sig_{id}/strat_res_{id} a las
    anchas, con NULL donde una señal no cubre un activo (dispersión)."""
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "mig0093",
        pathlib.Path("alembic/versions/0093_populate_sig_strat_wide.py"))
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        signal_store.ensure_wide_signal_tables(bind=conn)
        for i in (5, 6):
            conn.execute(sa.text(
                f"CREATE TABLE sig_{i} (asset_id INT, date DATE, score FLOAT, "
                "PRIMARY KEY (date, asset_id))"))
        conn.execute(sa.text(
            "CREATE TABLE strat_res_7 (asset_id INT, date DATE, score FLOAT, "
            "pct FLOAT, PRIMARY KEY (date, asset_id))"))
        conn.execute(sa.text(
            "INSERT INTO sig_5 VALUES (1,'2026-01-05',10),(2,'2026-01-05',11)"))
        conn.execute(sa.text("INSERT INTO sig_6 VALUES (1,'2026-01-05',20)"))
        conn.execute(sa.text(
            "INSERT INTO strat_res_7 VALUES (1,'2026-01-05',3.5,90)"))

        sig_tables, strat_tables = mig._dynamic_tables(conn)
        assert sig_tables == {5: "sig_5", 6: "sig_6"}
        assert strat_tables == {7: "strat_res_7"}

        mig._add_columns(conn, "signal_values_wide", ["sig_5", "sig_6"])
        mig._pivot(conn, "?", "signal_values_wide",
                   [("sig_5", [("score", "sig_5")]),
                    ("sig_6", [("score", "sig_6")])])
        mig._add_columns(conn, "strategy_results_wide",
                         ["strat_7_score", "strat_7_pct"])
        mig._pivot(conn, "?", "strategy_results_wide",
                   [("strat_res_7", [("score", "strat_7_score"),
                                     ("pct", "strat_7_pct")])])

        sig_rows = conn.execute(sa.text(
            "SELECT asset_id, sig_5, sig_6 FROM signal_values_wide "
            "ORDER BY asset_id")).fetchall()
        # activo 2 no tenía sig_6 → NULL (dispersión preservada)
        assert sig_rows == [(1, 10.0, 20.0), (2, 11.0, None)]
        srow = conn.execute(sa.text(
            "SELECT asset_id, strat_7_score, strat_7_pct "
            "FROM strategy_results_wide")).fetchone()
        assert tuple(srow) == (1, 3.5, 90.0)


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
