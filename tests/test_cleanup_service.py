"""Red contra la divergencia que dejó la pantalla /admin/cleanup desactualizada.

La lista de la pantalla y la del script CLI eran independientes: la pantalla
quedó borrando assets/prices/catálogos con FOREIGN_KEY_CHECKS=0 (dejando ~45
tablas huérfanas) y sin tocar nada del pipeline. Estos tests fijan el alcance
y que las dos entradas consuman la MISMA fuente.
"""
from pathlib import Path

import sqlalchemy as sa

from app.services import cleanup_service as cs

ROOT = Path(__file__).resolve().parent.parent

# Datos cargados a mano o irrecuperables: si alguno aparece en el alcance de la
# limpieza, es un bug. `assets` y los catálogos encabezan la lista porque
# borrarlos fue justamente el incidente que motivó este módulo; las tablas de
# carteras porque el registro de operaciones no se recrea solo.
_MUST_NEVER_WIPE = {
    "assets", "prices", "price_sources",
    # Crudo bajado de la fuente (no ratios) e insumo de ind_fundamental_*: se
    # borraba hasta jul-2026 y una redescarga NO lo restituye — Yahoo sirve
    # una ventana corta de trimestres. Ver el comentario en _LEAF_TABLES.
    "fundamental_quarterly",
    "sectors", "industries", "markets", "countries", "currencies",
    "instrument_types", "catalog_aliases_backup",
    "indicator_definitions", "signal", "strategy", "strategy_component",
    "synthetic_formula", "synthetic_component", "currency_conversion_divisor",
    "portfolio", "portfolio_member", "portfolio_transaction",
    "users", "app_settings", "scheduler_config",
    "pnf_config", "sr_config", "regime_config", "volatility_config",
    "drawdown_config", "fundamental_sources",
}


def _all_targets():
    return set(cs._LEAF_TABLES) | set(cs._REFERENCED_TABLES)


def test_no_borra_datos_curados():
    assert _all_targets() & _MUST_NEVER_WIPE == set()


def test_prefijos_dinamicos_no_barren_tablas_de_definicion():
    """"ind_"/"sig_" llevan "_" a propósito: sin él se llevarían puestas
    `industries`, `indicator_definitions` y `signal`."""
    for name in ("industries", "indicator_definitions", "indicator_update_log",
                 "signal", "signal_eval_log"):
        matches = [p for p in cs._DYNAMIC_PREFIXES if name.startswith(p)]
        assert matches == [], f"{name} matchea el prefijo {matches}"


def test_cubre_todos_los_logs():
    """Cada tabla de log/registro tiene que estar en el alcance — el gap que
    motivó la revisión (verification_run_log y run_lock no los limpiaba nadie)."""
    logs = {
        "indicator_update_log", "fundamental_update_log", "price_update_log",
        "import_log", "signal_eval_log", "verification_run_log",
        "asset_verification_flag", "run_lock",
    }
    assert logs <= _all_targets()


def test_cubre_snapshots_de_backtest_y_cartera():
    snapshots = {
        "backtest_run", "backtest_ic_point", "backtest_quantile_stat",
        "portfolio_run", "portfolio_run_point",
    }
    assert snapshots <= _all_targets()


def test_hijas_de_snapshots_van_antes_que_sus_padres():
    """Sin FOREIGN_KEY_CHECKS=0, el orden importa: las hijas se vacían primero
    (están en _LEAF_TABLES) y los padres al final, con DELETE — MySQL rechaza
    TRUNCATE sobre una tabla con FKs entrantes."""
    for child, parent in (("backtest_ic_point", "backtest_run"),
                          ("backtest_quantile_stat", "backtest_run"),
                          ("portfolio_run_point", "portfolio_run")):
        assert child in cs._LEAF_TABLES
        assert parent in cs._REFERENCED_TABLES


def test_la_pantalla_no_define_su_propia_lista():
    """La página y el script CLI importan el alcance del servicio en vez de
    mantener su propia copia (la copia fue la causa raíz de la divergencia).

    Se verifica sobre el fuente, no importando: los módulos de página llaman a
    register_page() y explotan fuera de una app instanciada (ver
    test_module_registration.py, que usa el mismo patrón).
    """
    page = (ROOT / "app" / "pages" / "admin_cleanup.py").read_text(encoding="utf-8")
    assert "_TABLES_INFO = [" not in page, (
        "admin_cleanup.py volvió a definir su propia lista de tablas — el "
        "alcance vive solo en cleanup_service.")
    assert "from app.services.cleanup_service import" in page

    cli = (ROOT / "scripts" / "clean_data.py").read_text(encoding="utf-8")
    assert "_TABLES = [" not in cli
    assert "cleanup_service" in cli


def test_el_callback_no_desactiva_el_chequeo_de_fks():
    """FOREIGN_KEY_CHECKS=0 fue la causa directa de las ~45 tablas huérfanas:
    con las FKs apagadas MySQL no dispara los ON DELETE CASCADE."""
    # Se busca la sentencia ejecutable, no la palabra: los docstrings la
    # nombran a propósito para explicar por qué NO se usa.
    for rel in ("app/callbacks/admin_cleanup_callbacks.py",
                "app/services/cleanup_service.py",
                "scripts/clean_data.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "SET FOREIGN_KEY_CHECKS" not in src, rel


def test_resolve_tables_ignora_las_que_no_existen(tmp_path):
    """La lista fija sobrevive a los modelos: `screener_snapshot` ya no existe
    y su DELETE reventaba la corrida entera en una base nueva."""
    engine = sa.create_engine(f"sqlite:///{tmp_path/'x.db'}")
    md = sa.MetaData()
    sa.Table("run_lock", md, sa.Column("op", sa.String(8), primary_key=True))
    sa.Table("ind_aapl", md, sa.Column("id", sa.Integer, primary_key=True))
    md.create_all(engine)

    with engine.begin() as conn:
        leaves, referenced = cs.resolve_tables(conn)

    assert set(leaves) == {"run_lock", "ind_aapl"}
    assert referenced == []


def test_clean_data_vacia_lo_derivado_y_respeta_lo_curado(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path/'y.db'}")
    md = sa.MetaData()
    for name in ("ind_aapl", "sig_1", "strat_res_1", "group_scores",
                 "import_log", "run_lock", "portfolio_run_point"):
        sa.Table(name, md, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("portfolio_run", md, sa.Column("id", sa.Integer, primary_key=True))
    # curadas: tienen que sobrevivir
    sa.Table("assets", md, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("prices", md, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("fundamental_quarterly", md,
             sa.Column("id", sa.Integer, primary_key=True))
    md.create_all(engine)

    with engine.begin() as conn:
        for name in ("ind_aapl", "sig_1", "strat_res_1", "group_scores",
                     "import_log", "run_lock", "portfolio_run_point",
                     "portfolio_run", "assets", "prices",
                     "fundamental_quarterly"):
            conn.execute(sa.text(f"INSERT INTO {name} (id) VALUES (1)"))

    res = cs.clean_data(bind=engine)

    with engine.connect() as conn:
        def count(t):
            return conn.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar()

        for name in ("ind_aapl", "sig_1", "strat_res_1", "group_scores",
                     "import_log", "run_lock", "portfolio_run_point",
                     "portfolio_run"):
            assert count(name) == 0, f"{name} debería haber quedado vacía"
        assert count("assets") == 1
        assert count("prices") == 1
        assert count("fundamental_quarterly") == 1

    assert "portfolio_run" in res["tables"]


# ── Mantenimiento: VACUUM/OPTIMIZE ───────────────────────────────────────────

def test_vacuum_tolera_tabla_que_desaparecio_a_mitad_de_corrida(monkeypatch):
    """La lista de tablas se arma ANTES de empezar y las dinámicas pueden
    dropearse mientras corre (signal_store dropea sig_/strat_res_ al borrar
    una señal). En PG medir el tamaño de una tabla inexistente LANZA; con la
    medición fuera del try eso abortaba la corrida y las tablas siguientes
    quedaban sin compactar.
    """
    from app.services import maintenance_service as ms

    vacuumed = []

    class _FakeConn:
        """Sustituto de la Connection en AUTOCOMMIT."""

        def execution_options(self, **kw):
            return self

        def exec_driver_sql(self, sql):
            vacuumed.append(sql)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _FakeEngine:
        dialect = type("D", (), {"name": "postgresql"})()

        def connect(self):
            return _FakeConn()

    def _fake_size(conn, table):
        if table == "strat_res_9":       # dropeada entre el listado y el vacuum
            raise RuntimeError('relation "strat_res_9" does not exist')
        return 1000 if table not in [s.split()[-1] for s in vacuumed] else 400

    monkeypatch.setattr(ms, "engine", _FakeEngine())
    monkeypatch.setattr(ms, "_table_size_bytes", _fake_size)
    monkeypatch.setattr(ms.db_compat, "is_postgres", lambda c: True)
    monkeypatch.setattr(ms.db_compat, "quote_ident", lambda c, t: t)

    res = ms.vacuum_tables(["ind_aapl", "strat_res_9", "ind_msft"])

    # la que desapareció se saltea; las otras dos SÍ se compactan
    assert set(res["tables"]) == {"ind_aapl", "ind_msft"}
    assert len(vacuumed) == 2


def test_los_dos_botones_toman_el_lock_de_escritura_pesada():
    """VACUUM y limpieza tocan las mismas tablas que el pipeline: sin el lock
    podían correr en paralelo con el Centro de Datos o el scheduler."""
    src = (ROOT / "app" / "callbacks" / "admin_cleanup_callbacks.py").read_text(
        encoding="utf-8")
    assert src.count("_launch_locked(") == 3      # 1 def + 2 usos
    assert "HEAVY_WRITE" in src


def test_launch_locked_no_arranca_si_el_lock_esta_tomado(monkeypatch):
    from app.callbacks import admin_cleanup_callbacks as cb

    monkeypatch.setattr(cb._rl, "guarded_acquire", lambda op: None)
    state = {"running": True, "result": "viejo", "error": None}
    llamado = []

    started = cb._launch_locked(state, lambda: llamado.append(1), str, "Error")

    assert started is False
    assert llamado == [], "no debe ejecutar el trabajo si otro tiene el lock"
    assert state["running"] is False
    assert "otra operación pesada" in state["error"]
