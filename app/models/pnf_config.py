from sqlalchemy import Column, Float, Integer, String
from app.database import Base


class PnfConfig(Base):
    """Configuración del gráfico Punto y Figura (única fila, id=1)."""

    __tablename__ = "pnf_config"

    id             = Column(Integer, primary_key=True, default=1)
    # Método de tamaño de caja: percent (% del último cierre) | atr | fixed
    box_method     = Column(String(10), nullable=False, default="atr")
    box_pct        = Column(Float,   nullable=False, default=1.0)   # si percent
    box_atr_period = Column(Integer, nullable=False, default=14)    # si atr
    box_fixed      = Column(Float,   nullable=False, default=1.0)   # si fixed
    # Cajas necesarias para revertir la columna (clásico: 3)
    reversal       = Column(Integer, nullable=False, default=3)
    # Precio usado: close (solo cierres) | hl (máximos/mínimos)
    source         = Column(String(5), nullable=False, default="close")
