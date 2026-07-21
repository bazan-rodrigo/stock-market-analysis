"""write_stats_service: el reporte de escrituras por corrida del Centro de
Datos. Lógica pura (diff/interpretación/registro) + la rama por dialecto de
db_compat (sqlite → None: el motor no expone contadores)."""
from datetime import datetime

from app.services import db_compat, write_stats_service as ws


def _clear():
    ws._runs.clear()


# ── diff ──────────────────────────────────────────────────────────────────────

def test_diff_solo_tablas_que_cambiaron_ordenado_por_magnitud():
    before = {"ind_daily": (100, 200, 0), "prices": (50, 0, 0),
              "ind_weekly": (10, 10, 0)}
    after = {"ind_daily": (100, 214, 0),          # +14 upd
             "prices": (1050, 0, 0),              # +1000 ins
             "ind_weekly": (10, 10, 0)}           # sin cambios → afuera
    d = ws.diff(before, after)
    assert [r["table"] for r in d] == ["prices", "ind_daily"]
    assert d[0] == {"table": "prices", "d_ins": 1000, "d_upd": 0, "d_del": 0}
    assert d[1]["d_upd"] == 14


def test_diff_tabla_nueva_en_after_cuenta_desde_cero():
    d = ws.diff({}, {"ind_daily": (5, 3, 1)})
    assert d == [{"table": "ind_daily", "d_ins": 5, "d_upd": 3, "d_del": 1}]


def test_diff_none_si_falta_un_snapshot():
    assert ws.diff(None, {"x": (1, 1, 1)}) is None
    assert ws.diff({"x": (1, 1, 1)}, None) is None


# ── interpret ─────────────────────────────────────────────────────────────────

def test_interpret_niveles():
    # ~1 upd/activo → normal
    lvl, _ = ws.interpret([{"table": "ind_daily", "d_ins": 0,
                            "d_upd": 145, "d_del": 0}], 145)
    assert lvl == "ok"
    # ~61 upd/activo → re-ranking legítimo (el caso real medido)
    lvl, _ = ws.interpret([{"table": "ind_daily", "d_ins": 0,
                            "d_upd": 8916, "d_del": 0}], 145)
    assert lvl == "warn"
    # miles por activo → patrón de bloat
    lvl, _ = ws.interpret([{"table": "ind_daily", "d_ins": 0,
                            "d_upd": 450_000, "d_del": 0}], 3)
    assert lvl == "high"
    # sin contadores
    lvl, note = ws.interpret(None, 145)
    assert lvl == "na" and "PostgreSQL" in note


def test_interpret_ignora_tablas_no_ind():
    # updates masivos en prices no disparan el veredicto de indicadores
    lvl, _ = ws.interpret([{"table": "prices", "d_ins": 0,
                            "d_upd": 999_999, "d_del": 0}], 10)
    assert lvl == "ok"


# ── registro ──────────────────────────────────────────────────────────────────

def test_record_run_guarda_y_ordena_mas_reciente_primero():
    _clear()
    t = datetime(2026, 7, 21, 1, 0, 0)
    ws.record_run("indicators", "update_indicator_history", 145, t, t,
                  {"ind_daily": (0, 0, 0)}, {"ind_daily": (0, 145, 0)})
    ws.record_run("prices", "update_all_active_assets", 3, t, t,
                  {"prices": (0, 0, 0)}, {"prices": (500, 0, 0)})
    runs = ws.get_runs()
    assert [r["kind"] for r in runs] == ["Descarga de precios",
                                        "Indicadores técnicos"]
    assert runs[1]["level"] == "ok" and runs[1]["diff"][0]["d_upd"] == 145


def test_record_run_respeta_maxlen():
    _clear()
    t = datetime(2026, 7, 21)
    for i in range(ws._MAX_RUNS + 5):
        ws.record_run("synth", "f", 1, t, t, {}, {"prices": (i + 1, 0, 0)})
    assert len(ws.get_runs()) == ws._MAX_RUNS


def test_record_run_nunca_levanta():
    _clear()
    # started sin strftime, snapshots basura: se registra o se descarta,
    # pero JAMÁS propaga (el diagnóstico no puede romper una corrida)
    ws.record_run("indicators", None, None, object(), None, "basura", 42)
    ws.get_runs()


# ── rama por dialecto ─────────────────────────────────────────────────────────

def test_table_write_stats_none_en_sqlite():
    from app.database import get_session
    assert db_compat.table_write_stats(get_session()) is None


def test_snapshot_nunca_levanta():
    assert ws.snapshot(object()) is None
