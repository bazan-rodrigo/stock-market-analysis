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


class CurrentIndicatorValue(Base):
    """Indicadores sin historia (keep_history=False): un valor vigente por activo."""

    __tablename__ = "current_indicator_values"

    asset_id  = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    code      = Column(String(50), primary_key=True)
    value_num = Column(Float,      nullable=True)
    value_str = Column(String(50), nullable=True)
