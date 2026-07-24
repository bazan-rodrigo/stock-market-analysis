"""
Reporte de escrituras por corrida (diagnóstico del Centro de Datos).

Motivación: validar en producción que las corridas escriben lo esperado —
en particular el patrón de bloat "un UPDATE por columna" en las tablas anchas
(medido 51% de tuplas muertas en ind_daily antes del arreglo) obligaba a
anotar contadores a mano antes y después de cada corrida. Este servicio lo
hace solo: el chokepoint `_run` del Centro de Datos toma un snapshot de los
contadores acumulados del motor (db_compat.table_write_stats) antes y después
de cada corrida, y acá se guarda el diff con una interpretación.

El registro vive EN MEMORIA del proceso (deque de las últimas corridas): es
diagnóstico, no auditoría — un restart lo limpia y está bien. Sin tabla nueva
ni migración.

Limitaciones (el card las muestra):
- Solo PostgreSQL. En MySQL/MariaDB/sqlite `snapshot()` devuelve None y las
  corridas quedan registradas como "no disponible".
- Los contadores son globales de la base: si DOS corridas escriben a la vez,
  sus deltas se mezclan. Para el uso real (una corrida por vez desde el
  Centro de Datos) alcanza.
"""
import threading
from collections import deque
from datetime import datetime

from app.services import db_compat

# Últimas corridas registradas (proceso). maxlen chico: es un diagnóstico.
_MAX_RUNS = 20
_runs: deque = deque(maxlen=_MAX_RUNS)
_lock = threading.Lock()

# Nombres legibles por op_id del Centro de Datos.
_KIND_LABELS = {
    "prices":     "Descarga de precios",
    "fund":       "Fundamentales",
    "snap":       "Ratios (snapshot)",
    "indicators": "Indicadores técnicos",
    "synth":      "Sintéticos",
    "signals":    "Señales/estrategias",
}


def snapshot(session):
    """Contadores acumulados por tabla, o None si el motor no los expone.
    Nunca levanta: el diagnóstico jamás debe romper una corrida."""
    try:
        return db_compat.table_write_stats(session)
    except Exception:
        return None


def diff(before: dict | None, after: dict | None) -> list[dict] | None:
    """[{table, d_ins, d_upd, d_del}] con las tablas que cambiaron, ordenado
    por magnitud total descendente. None si algún snapshot no está (motor sin
    contadores o snapshot fallido)."""
    if before is None or after is None:
        return None
    out = []
    for table, (ins_a, upd_a, del_a) in after.items():
        ins_b, upd_b, del_b = before.get(table, (0, 0, 0))
        d_ins, d_upd, d_del = ins_a - ins_b, upd_a - upd_b, del_a - del_b
        if d_ins or d_upd or d_del:
            out.append({"table": table, "d_ins": d_ins,
                        "d_upd": d_upd, "d_del": d_del})
    out.sort(key=lambda r: abs(r["d_ins"]) + abs(r["d_upd"]) + abs(r["d_del"]),
             reverse=True)
    return out


def interpret(d: list[dict] | None, total, unit: str | None = "activos"
              ) -> tuple[str, str]:
    """(nivel, nota) para el card. Niveles: 'ok' | 'warn' | 'high' | 'na'.

    El diagnóstico es el del bloat "un UPDATE por columna" y SOLO aplica a
    corridas que escriben tablas de indicadores. La heurística mira updates
    POR ACTIVO en esas tablas:
    - ~0-3 upd/activo: lo normal de un delta (la última fecha + vigentes).
    - decenas-cientos: re-ranking de full_sample tras un dato nuevo — puede
      ser LEGÍTIMO (los percentiles reclasifican la historia); no es error.
    - miles por activo: patrón de escritura por columna sobre la historia
      completa (el bug de bloat) — revisar.

    Una corrida que no escribe ninguna ind_* (señales, precios sueltos) NO
    tiene ratio de bloat que reportar: se dice "no aplica" en vez de un ✓
    vacuo. Idem si el `total` de la corrida no está en unidad de activos (p.
    ej. señales cuenta fechas): el ratio upd/activo no tendría sentido."""
    if d is None:
        return "na", "sin contadores en este motor (solo PostgreSQL)"
    ind_upd = sum(r["d_upd"] for r in d if r["table"].startswith("ind_"))
    if not any(r["table"].startswith("ind_") for r in d):
        return "na", "sin escrituras de indicadores — el diagnóstico no aplica"
    if not total or unit != "activos":
        return "ok", "—"
    ratio = ind_upd / total
    if ratio <= 3:
        return "ok", f"{ratio:.1f} upd/activo — normal"
    if ratio <= 1000:
        return "warn", (f"{ratio:.0f} upd/activo — re-ranking tras dato "
                        "nuevo (legítimo) o revisión amplia")
    return "high", (f"{ratio:.0f} upd/activo — posible escritura por "
                    "columna (patrón de bloat), revisar")


def record_run(op_id: str, fn_name: str, total, unit, started, finished,
               before, after) -> None:
    """Registra una corrida terminada. Nunca levanta.

    `total`/`unit` los declara el servicio en su dict de retorno: el `total`
    NO es siempre "activos" (señales cuenta fechas, indicadores cuenta
    indicadores según el camino), así que la unidad viaja con el número para
    que el card no la invente."""
    try:
        d = diff(before, after)
        level, note = interpret(d, total, unit)
        with _lock:
            _runs.appendleft({
                "kind": _KIND_LABELS.get(op_id, op_id),
                "fn": fn_name or "",
                "total": total,
                "unit": unit,
                "started": started,
                "finished": finished or datetime.now(),
                "diff": d,
                "level": level,
                "note": note,
            })
    except Exception:
        pass


def get_runs() -> list[dict]:
    with _lock:
        return list(_runs)
