"""
Consola SQL para administradores.

Estado de sesión: dict server-side keyed por UUID (dcc.Store).
Cada sesión mantiene una conexión SQLAlchemy con una transacción abierta
mientras hay DML pendiente.
"""
import io
import threading
import uuid
from datetime import datetime, timedelta

from dash import Input, Output, State, callback, dash_table, dcc, no_update
import dash_bootstrap_components as dbc
from sqlalchemy import text

from app.components.table_styles import HEADER, DATA, CELL

# ── Estado server-side ────────────────────────────────────────────────────────
_lock     = threading.Lock()
_sessions: dict[str, dict] = {}   # {uuid: {conn, has_pending, last_used}}

_MAX_ROWS        = 5_000
_SESSION_TTL_MIN = 30


def _get_conn(session_id: str):
    from app.database import engine
    with _lock:
        entry = _sessions.get(session_id)
        if entry:
            entry["last_used"] = datetime.utcnow()
            return entry["conn"]
        conn = engine.connect()
        _sessions[session_id] = {
            "conn":        conn,
            "has_pending": False,
            "last_used":   datetime.utcnow(),
        }
        return conn


def _close_conn(session_id: str):
    with _lock:
        entry = _sessions.pop(session_id, None)
    if entry:
        try:
            entry["conn"].close()
        except Exception:
            pass


def _set_pending(session_id: str, flag: bool):
    with _lock:
        if session_id in _sessions:
            _sessions[session_id]["has_pending"] = flag


def _has_pending(session_id: str) -> bool:
    with _lock:
        return _sessions.get(session_id, {}).get("has_pending", False)


def _purge_stale():
    cutoff = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MIN)
    with _lock:
        stale = [sid for sid, e in _sessions.items() if e["last_used"] < cutoff]
    for sid in stale:
        _close_conn(sid)


# ── Inicializar sesión al cargar la página ────────────────────────────────────
@callback(
    Output("sql-session-id", "data"),
    Input("sql-session-id",  "id"),
)
def init_session(_):
    _purge_stale()
    return str(uuid.uuid4())


# ── Ejecutar SQL ──────────────────────────────────────────────────────────────
@callback(
    Output("sql-result-container", "children"),
    Output("sql-status",           "children"),
    Output("sql-status",           "style"),
    Output("sql-btn-commit",       "disabled"),
    Output("sql-btn-rollback",     "disabled"),
    Output("sql-btn-export",       "disabled"),
    Input("sql-btn-exec",          "n_clicks"),
    State("sql-input",             "value"),
    State("sql-session-id",        "data"),
    prevent_initial_call=True,
)
def execute_sql(_, sql, session_id):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return no_update, "Acceso denegado.", _style("danger"), True, True, True

    if not sql or not sql.strip():
        return no_update, "Escribí una consulta SQL.", _style("warning"), no_update, no_update, no_update

    stmt = sql.strip().rstrip(";")
    is_select = stmt.upper().lstrip().startswith("SELECT")

    try:
        conn = _get_conn(session_id)
        result = conn.execute(text(stmt))

        if is_select:
            rows = result.fetchmany(_MAX_ROWS)
            cols = list(result.keys())
            data = [{c: _fmt(r[i]) for i, c in enumerate(cols)} for r in rows]
            note = f"+{len(data)} más" if len(data) == _MAX_ROWS else ""
            status = f"{len(data)} filas{('  ·  ' + note) if note else ''}"
            table = _build_table(cols, data)
            pending = _has_pending(session_id)
            return table, status, _style("ok"), not pending, not pending, len(data) == 0

        else:
            rowcount = result.rowcount
            _set_pending(session_id, True)
            status = f"{rowcount} fila(s) afectada(s) — pendiente de commit/rollback"
            return _info("DML ejecutado. Revisá y hacé Commit o Rollback."),\
                   status, _style("warning"), False, False, False

    except Exception as exc:
        _set_pending(session_id, False)
        return _error(str(exc)), f"Error: {exc}", _style("danger"), True, True, True


# ── Commit ────────────────────────────────────────────────────────────────────
@callback(
    Output("sql-status",     "children", allow_duplicate=True),
    Output("sql-status",     "style",    allow_duplicate=True),
    Output("sql-btn-commit",  "disabled", allow_duplicate=True),
    Output("sql-btn-rollback","disabled", allow_duplicate=True),
    Input("sql-btn-commit",   "n_clicks"),
    State("sql-session-id",   "data"),
    prevent_initial_call=True,
)
def commit_tx(_, session_id):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Acceso denegado.", _style("danger"), True, True

    try:
        conn = _get_conn(session_id)
        conn.commit()
        _set_pending(session_id, False)
        return "Commit OK.", _style("ok"), True, True
    except Exception as exc:
        return f"Error en commit: {exc}", _style("danger"), False, False


# ── Rollback ──────────────────────────────────────────────────────────────────
@callback(
    Output("sql-status",      "children", allow_duplicate=True),
    Output("sql-status",      "style",    allow_duplicate=True),
    Output("sql-btn-commit",  "disabled", allow_duplicate=True),
    Output("sql-btn-rollback","disabled", allow_duplicate=True),
    Input("sql-btn-rollback",  "n_clicks"),
    State("sql-session-id",    "data"),
    prevent_initial_call=True,
)
def rollback_tx(_, session_id):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return "Acceso denegado.", _style("danger"), True, True

    try:
        conn = _get_conn(session_id)
        conn.rollback()
        _set_pending(session_id, False)
        return "Rollback OK.", _style("warning"), True, True
    except Exception as exc:
        return f"Error en rollback: {exc}", _style("danger"), False, False


# ── Exportar CSV ──────────────────────────────────────────────────────────────
@callback(
    Output("sql-download", "data"),
    Input("sql-btn-export", "n_clicks"),
    State("sql-input",      "value"),
    State("sql-session-id", "data"),
    prevent_initial_call=True,
)
def export_csv(_, sql, session_id):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return no_update
    if not sql or not sql.strip():
        return no_update

    try:
        conn   = _get_conn(session_id)
        result = conn.execute(text(sql.strip().rstrip(";")))
        rows   = result.fetchall()
        cols   = list(result.keys())
        buf    = io.StringIO()
        buf.write(",".join(cols) + "\n")
        for row in rows:
            buf.write(",".join(_csv_val(v) for v in row) + "\n")
        return dcc.send_string(buf.getvalue(), filename="sql_export.csv")
    except Exception:
        return no_update


# ── Helpers ───────────────────────────────────────────────────────────────────
def _fmt(v):
    if v is None:
        return ""
    return str(v)


def _csv_val(v):
    s = "" if v is None else str(v)
    if "," in s or '"' in s or "\n" in s:
        s = '"' + s.replace('"', '""') + '"'
    return s


def _style(kind: str) -> dict:
    colors = {
        "ok":      {"color": "#4caf50"},
        "warning": {"color": "#facc15"},
        "danger":  {"color": "#ef5350"},
    }
    return {**{"fontSize": "0.82rem", "fontFamily": "monospace"},
            **colors.get(kind, {})}


def _build_table(cols: list, data: list):
    columns = [{"name": c, "id": c} for c in cols]
    return dash_table.DataTable(
        columns=columns,
        data=data,
        page_size=50,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto", "marginTop": "8px"},
        style_header=HEADER,
        style_data=DATA,
        style_cell={
            **CELL,
            "textAlign":  "left",
            "fontSize":   "0.78rem",
            "padding":    "3px 6px",
            "fontFamily": "monospace",
            "maxWidth":   "300px",
            "overflow":   "hidden",
            "textOverflow": "ellipsis",
            "whiteSpace": "nowrap",
        },
    )


def _error(msg: str):
    return dbc.Alert(msg, color="danger", className="mt-2",
                     style={"fontFamily": "monospace", "fontSize": "0.82rem",
                            "whiteSpace": "pre-wrap"})


def _info(msg: str):
    return dbc.Alert(msg, color="warning", className="mt-2",
                     style={"fontSize": "0.82rem"})
