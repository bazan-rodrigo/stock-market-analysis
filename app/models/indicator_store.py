"""
Almacenamiento de indicadores por tabla separada.

Cada indicador con keep_history=True tiene su propia tabla ind_{code}
con PK (asset_id, date), sin contención entre indicadores al escribir.

Los indicadores con keep_history=False (best_sma_*, best_ema_*) se
almacenan en current_indicator_values (un solo valor vigente por activo).
"""
import threading

from sqlalchemy import Column, Date, Float, ForeignKey, Integer, MetaData, String, Table

from app.database import Base, engine

_meta      = MetaData()
_meta_lock = threading.Lock()


def get_ind_table(code: str) -> Table:
    """Refleja la tabla ind_{code} desde la BD (usa caché interno de MetaData)."""
    name = f"ind_{code}"
    # Fast path: tabla ya reflejada con columnas
    if name in _meta.tables and len(_meta.tables[name].columns) > 0:
        return _meta.tables[name]
    # Slow path: un solo thread refleja a la vez para evitar race condition
    with _meta_lock:
        if name in _meta.tables and len(_meta.tables[name].columns) > 0:
            return _meta.tables[name]
        return Table(name, _meta, autoload_with=engine, extend_existing=True)


# Lookup "as-of": máxima antigüedad aceptada del último valor. Los
# indicadores semanales/mensuales se guardan con fechas de fin de período
# (el resample etiqueta las semanas en domingo), así que una fecha diaria
# arbitraria no tiene fila exacta. El tope evita levantar valores zombie de
# activos que dejaron de cotizar (45 días cubre etiquetas mensuales +
# feriados largos).
ASOF_MAX_LOOKBACK_DAYS = 45


def query_values_asof(session, code: str, target_date) -> dict[int, object]:
    """{asset_id: value} con la última fila de ind_{code} <= target_date por
    activo (ver ASOF_MAX_LOOKBACK_DAYS). Usado por signal_service y por el
    filtro de elegibilidad de estrategias — un match exacto de fecha dejaría
    sin valor a los indicadores semanales/mensuales casi cualquier día."""
    from datetime import timedelta

    import sqlalchemy as sa

    tbl = get_ind_table(code)
    cutoff = target_date - timedelta(days=ASOF_MAX_LOOKBACK_DAYS)
    latest = (
        sa.select(tbl.c.asset_id, sa.func.max(tbl.c.date).label("mx"))
        .where(tbl.c.date <= target_date, tbl.c.date >= cutoff)
        .group_by(tbl.c.asset_id)
        .subquery()
    )
    rows = session.execute(
        sa.select(tbl.c.asset_id, tbl.c.value)
        .select_from(tbl.join(
            latest,
            sa.and_(tbl.c.asset_id == latest.c.asset_id,
                    tbl.c.date == latest.c.mx),
        ))
    ).fetchall()
    return {aid: v for aid, v in rows if v is not None}


class CurrentIndicatorValue(Base):
    """Indicadores sin historia (keep_history=False): un valor vigente por activo."""

    __tablename__ = "current_indicator_values"

    asset_id  = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    code      = Column(String(50), primary_key=True)
    value_num = Column(Float,      nullable=True)
    value_str = Column(String(50), nullable=True)


class IndAssetMeta(Base):
    """Metadato de invalidación/caché por activo e indicador: referencia
    externa (benchmark_id, ver _BENCHMARK_DEP_CODES) o hash del prefijo
    histórico (checksum, ver _CHECKSUM_DEP_CODES) usados en el último
    cálculo completo de la serie, para detectar cuándo el camino rápido
    del delta debe invalidarse aunque no haya huecos en el historial
    guardado. min_date/max_date/row_count cachean el resultado de
    _query_tail_stats (evita un full-scan de ind_{code} en cada delta) y
    se recalculan en cada backfill_indicator exitoso — ver
    _upsert_ind_stats_meta y el DELETE junto al TRUNCATE en force.

    Nota: la consola SQL de administración permite DML arbitrario sobre
    ind_* sin pasar por estos servicios. Si se edita una tabla ind_{code}
    a mano ahí, este caché (y benchmark_id/checksum) puede quedar
    desincronizado — forzar un rebuild (force=True) de ese indicador
    después de cualquier edición manual."""

    __tablename__ = "ind_asset_meta"

    asset_id     = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    code         = Column(String(50), primary_key=True)
    benchmark_id = Column(Integer, nullable=True)
    checksum     = Column(String(64), nullable=True)
    min_date     = Column(Date, nullable=True)
    max_date     = Column(Date, nullable=True)
    row_count    = Column(Integer, nullable=True)
