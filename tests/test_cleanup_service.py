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


def test_cubre_el_almacenamiento_vivo_de_senales_y_estrategias():
    """Regresión del cutover a tablas anchas: la limpieza se apoyaba en los
    prefijos "sig_"/"strat_res_", que dejaron de matchear cuando la 0094
    dropeó las per-entidad. Resultado: borraba signal_eval_log (los markers)
    pero DEJABA los valores, mientras la pantalla prometía vaciarlos.

    Los prefijos siguen en la lista (barren remanentes en una base sin migrar),
    pero el almacenamiento vivo tiene que estar nombrado explícitamente."""
    vivas = {"signal_values_wide", "strategy_results_wide"}
    assert vivas <= _all_targets()
    # Y que no dependa del prefijo, que es justo lo que falló:
    for name in vivas:
        assert not any(name.startswith(p) for p in cs._DYNAMIC_PREFIXES)


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
    for name in ("ind_aapl", "sig_1", "strat_res_1",
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
        for name in ("ind_aapl", "sig_1", "strat_res_1",
                     "import_log", "run_lock", "portfolio_run_point",
                     "portfolio_run", "assets", "prices",
                     "fundamental_quarterly"):
            conn.execute(sa.text(f"INSERT INTO {name} (id) VALUES (1)"))

    res = cs.clean_data(bind=engine)

    with engine.connect() as conn:
        def count(t):
            return conn.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar()

        for name in ("ind_aapl", "sig_1", "strat_res_1",
                     "import_log", "run_lock", "portfolio_run_point",
                     "portfolio_run"):
            assert count(name) == 0, f"{name} debería haber quedado vacía"
        assert count("assets") == 1
        assert count("prices") == 1
        assert count("fundamental_quarterly") == 1

    assert "portfolio_run" in res["tables"]


# ── El alcance de la limpieza, DERIVADO del esquema ──────────────────────────
# Los tests de cobertura de arriba (logs, snapshots, anchas) enumeran nombres a
# mano: son útiles para explicar POR QUÉ cada grupo está, pero no pueden ver una
# tabla que nadie escribió en ninguna lista. Este par de tests sí — recorren el
# esquema real y exigen una decisión explícita por tabla.

def _universo_de_tablas() -> set[str]:
    """Toda tabla ESTÁTICA del esquema: los modelos ORM más las que se crean
    fuera de Base.metadata (las anchas de indicadores y de señales, que tienen
    su propio MetaData en los stores). Las dinámicas —ind_{code}, y las
    sig_{id}/strat_res_{id} de bases sin migrar— no son enumerables sin datos:
    las cubren los prefijos, y que los prefijos no se lleven puesta una tabla de
    definición lo fija test_prefijos_dinamicos_no_barren_tablas_de_definicion.
    """
    import app.models  # noqa: F401  — puebla Base.metadata
    from app.database import Base
    from app.models.indicator_store import _WIDE_CADENCE_TABLE
    from app.models import signal_store as ss

    return (set(Base.metadata.tables)
            | set(_WIDE_CADENCE_TABLE.values())
            | {ss.SIG_WIDE_TABLE, ss.STRAT_WIDE_TABLE})


def _en_alcance(tabla: str) -> bool:
    return (tabla in cs._LEAF_TABLES or tabla in cs._REFERENCED_TABLES
            or any(tabla.startswith(p) for p in cs._DYNAMIC_PREFIXES))


def test_toda_tabla_del_esquema_esta_clasificada():
    """Trinquete DERIVADO: cada tabla del esquema tiene que estar o en el
    alcance de la limpieza, o en `_PRESERVED_TABLES` con su motivo escrito.

    Es la red que faltaba. Los tests de cobertura escritos a mano estuvieron en
    verde mientras la limpieza estaba ROTA: cuando la 0094 dropeó las tablas por
    señal, `sig_`/`strat_res_` dejaron de matchear y los valores de señales
    quedaron sin vaciar, pero los tests seguían preguntando por los nombres que
    alguien había tipeado. Lo mismo con `run_history`, que nació con la 0096 y
    quedó sin vaciar sin que nadie lo decidiera: lo destapó este test.

    NO decide nada por vos — te impide olvidarte de decidir. Una tabla nueva
    rompe la suite hasta que se la clasifica de un lado o del otro.
    """
    sin_clasificar = sorted(
        t for t in _universo_de_tablas()
        if not _en_alcance(t) and t not in cs._PRESERVED_TABLES)

    assert not sin_clasificar, (
        "Tablas sin clasificar en cleanup_service: "
        f"{sin_clasificar}.\nAgregá cada una a _LEAF_TABLES/_REFERENCED_TABLES "
        "(si la limpieza tiene que vaciarla) o a _PRESERVED_TABLES con el "
        "motivo por el que se conserva.")


def test_preservadas_y_alcance_no_se_solapan_ni_mienten():
    """La clasificación tiene que ser una PARTICIÓN del esquema: sin tablas en
    los dos lados (contradicción) y sin entradas que ya no existan (una
    preservada fantasma tapa el agujero que este test busca: parece decidida y
    no hay nada)."""
    universo = _universo_de_tablas()

    en_ambos = sorted(t for t in cs._PRESERVED_TABLES if _en_alcance(t))
    assert not en_ambos, f"declaradas preservadas Y en el alcance: {en_ambos}"

    fantasmas = sorted(set(cs._PRESERVED_TABLES) - universo)
    assert not fantasmas, (
        f"_PRESERVED_TABLES nombra tablas que no existen: {fantasmas}")

    sin_motivo = sorted(t for t, m in cs._PRESERVED_TABLES.items() if not m.strip())
    assert not sin_motivo, f"preservadas sin motivo escrito: {sin_motivo}"


# ── Reinicio a fábrica: el alcance se DERIVA del catálogo ────────────────────

def _esquema_completo(engine):
    """Arma el esquema como en una instalación real: los modelos ORM MÁS las
    tablas que viven fuera de Base.metadata (las anchas de indicadores y de
    señales, una ind_{code} per-código) y alembic_version."""
    import app.models  # noqa: F401  — puebla Base.metadata
    from app.database import Base
    from app.models.indicator_store import ensure_wide_ind_tables
    from app.models.signal_store import ensure_wide_signal_tables

    Base.metadata.create_all(engine)
    ensure_wide_ind_tables(bind=engine)
    ensure_wide_signal_tables(bind=engine)
    md = sa.MetaData()
    sa.Table("ind_aapl", md, sa.Column("date", sa.Date, primary_key=True))
    sa.Table("alembic_version", md,
             sa.Column("version_num", sa.String(32), primary_key=True))
    md.create_all(engine)


def test_reset_vacia_todo_lo_que_existe_menos_alembic_version(tmp_path):
    """Trinquete DERIVADO, no una lista a mano —que es justo lo que se pudre—:
    el reinicio a fábrica tiene que alcanzar CADA tabla del catálogo.

    La versión enumerada (Base.metadata + prefijos dinámicos) dejaba afuera en
    silencio todo lo que no fuera modelo ORM ni matcheara un prefijo: las
    anchas de señales cumplen las dos condiciones, así que el botón prometía
    una base recién instalada y dejaba adentro los valores de señales y los
    rankings de estrategias.
    """
    engine = sa.create_engine(f"sqlite:///{tmp_path/'reset.db'}")
    _esquema_completo(engine)

    with engine.begin() as conn:
        wiped = cs._fresh_install_wipe(conn)

    existentes = set(sa.inspect(engine).get_table_names())
    assert set(wiped) == existentes - {"alembic_version"}
    # Nombradas aparte para que el fallo diga QUÉ se escapó, no solo cuántas:
    assert {"signal_values_wide", "strategy_results_wide",
            "ind_daily", "ind_aapl"} <= set(wiped)


def test_reset_no_depende_de_que_la_tabla_sea_modelo_orm(tmp_path):
    """El alcance no puede salir de Base.metadata: por el camino del CLI
    (`scripts/clean_data.py --reset` importa SOLO cleanup_service) el metadata
    está vacío y el reset no vaciaba ni `assets`, mientras el script informaba
    que había reiniciado la base. Se fija con tablas que no son modelo ni
    matchean los prefijos dinámicos."""
    engine = sa.create_engine(f"sqlite:///{tmp_path/'ajenas.db'}")
    tablas = ("signal_values_wide", "strategy_results_wide", "zz_ajena")
    md = sa.MetaData()
    for name in tablas:
        sa.Table(name, md, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("alembic_version", md,
             sa.Column("version_num", sa.String(32), primary_key=True))
    md.create_all(engine)
    with engine.begin() as conn:
        for name in tablas:
            conn.execute(sa.text(f"INSERT INTO {name} (id) VALUES (1)"))
        conn.execute(sa.text(
            "INSERT INTO alembic_version (version_num) VALUES ('0100')"))

    with engine.begin() as conn:
        cs._fresh_install_wipe(conn)

    with engine.connect() as conn:
        def count(t):
            return conn.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar()

        for name in tablas:
            assert count(name) == 0, f"{name} debería haber quedado vacía"
        # La versión de migraciones sobrevive: el esquema ya está en head y el
        # reinicio no lo toca (no hay que re-estampar).
        assert count("alembic_version") == 1


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


def test_los_tres_botones_toman_el_lock_de_escritura_pesada():
    """VACUUM, limpieza y reinicio a fábrica tocan las mismas tablas que el
    pipeline: sin el lock podían correr en paralelo con el Centro de Datos o el
    scheduler."""
    src = (ROOT / "app" / "callbacks" / "admin_cleanup_callbacks.py").read_text(
        encoding="utf-8")
    assert src.count("_launch_locked(") == 4      # 1 def + 3 usos
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
