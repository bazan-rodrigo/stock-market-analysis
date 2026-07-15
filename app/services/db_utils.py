"""
Utilidades de mantenimiento de BD compartidas.

CONVENCIÓN (ver CLAUDE.md): todo DELETE masivo sobre un rango grande va por
VENTANAS QUE AVANZAN (delete_by_ranges) — nunca una sentencia única (retiene
locks/undo por minutos; medido 400s+ sobre signal_value) y NUNCA un loop
`DELETE ... LIMIT N` sobre el rango completo: cada lote re-escanea desde el
inicio del rango los tombstones que dejaron los lotes anteriores (el purge
de InnoDB no alcanza) — O(n²), medido en vivo 17min+ sin terminar para lo
que las ventanas hacen en decenas de segundos.
"""
import logging

import sqlalchemy as sa

logger = logging.getLogger(__name__)


def delete_by_ranges(session, table: str, range_col: str, windows,
                     where_extra: str = "", params: dict | None = None) -> int:
    """DELETE masivo por ventanas consecutivas sobre range_col: una sentencia
    `DELETE FROM {table} WHERE {range_col} BETWEEN :lo AND :hi [AND extra]`
    por ventana, con commit por ventana. Cada sentencia ataca un tramo
    VIRGEN del índice (nunca re-escanea filas ya borradas) y su transacción
    queda acotada al tamaño de la ventana. Devuelve filas borradas.

    windows: iterable de pares (lo, hi) inclusive, en orden.
    table/range_col/where_extra se interpolan: SOLO strings construidos por
    el caller (nombres propios, ids numéricos validados) — nunca input del
    usuario. Valores variables adicionales van en params.
    """
    extra = f" AND {where_extra}" if where_extra else ""
    stmt = sa.text(
        f"DELETE FROM {table} WHERE {range_col} BETWEEN :lo AND :hi{extra}")
    base = dict(params or {})
    total = n_win = 0
    for lo, hi in windows:
        res = session.execute(stmt, {**base, "lo": lo, "hi": hi})
        session.commit()
        total += res.rowcount
        n_win += 1
    if total:
        logger.info("delete_by_ranges: %s filas borradas de %s (%s ventanas)",
                    total, table, n_win)
    return total
