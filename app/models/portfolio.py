from datetime import datetime

from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey,
                        Integer, String)

from app.database import Base


class Portfolio(Base):
    """Una cartera de la biblioteca: de seguimiento (teórica) o real.

    - ptype='seg'  → teórica / de seguimiento (sin plata real). Los campos de
      composición (curada/regla/estrategia) se agregan en la fase de teóricas.
    - ptype='real' → con registro de operaciones (portfolio_transaction); su
      posición y P&L se DERIVAN de ese registro.

    linked_portfolio_id: una real puede apuntar (opcional) a una teórica
    objetivo para el tracking error. base_currency: moneda de valuación de la
    cartera (multi-moneda: cada operación puede venir en otra moneda y se
    convierte as-of al valuar).

    owner_id / is_public: mismo modelo que Strategy/SignalDefinition (ver
    app/services/visibility.py). owner_id controla la EDICIÓN (dueño o admin;
    NULL = solo admin); is_public solo la VISIBILIDAD (default privada: la ven
    solo su dueño y el admin). Reusa visible_filter/can_edit/current_viewer.
    """

    __tablename__ = "portfolio"

    id                  = Column(Integer, primary_key=True)
    name                = Column(String(120), nullable=False)
    ptype               = Column(String(10), nullable=False)   # 'seg' | 'real'
    owner_id            = Column(Integer,
                                 ForeignKey("users.id", ondelete="SET NULL"))
    is_public           = Column(Boolean, nullable=False, default=False)
    base_currency       = Column(String(10))
    benchmark_asset_id  = Column(Integer,
                                 ForeignKey("assets.id", ondelete="SET NULL"))
    linked_portfolio_id = Column(Integer,
                                 ForeignKey("portfolio.id", ondelete="SET NULL"))
    created_at          = Column(DateTime, nullable=False, default=datetime.utcnow)


class PortfolioTransaction(Base):
    """Registro de operaciones de una cartera real.

    kind: 'buy' | 'sell' | 'dividend' | 'split'.
    price: precio por acción; si viene NULL se toma el cierre de mercado de la
    fecha (tabla prices) al calcular. En 'dividend' = importe por acción; en
    'split' se usa quantity como factor.
    commission / taxes: costos de la operación EN LA MONEDA DE LA OPERACIÓN
    (currency). Los impuestos ligados a la operación (IVA sobre la comisión,
    derechos de mercado, etc.) van en `taxes`; el P&L neto descuenta ambos.
    Los impuestos patrimoniales/anuales (Ganancias, Bienes Personales) NO son
    por-operación y quedan fuera de esta tabla.
    """

    __tablename__ = "portfolio_transaction"

    id           = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer,
                          ForeignKey("portfolio.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    asset_id     = Column(Integer,
                          ForeignKey("assets.id", ondelete="CASCADE"),
                          nullable=False)
    kind         = Column(String(10), nullable=False)   # buy|sell|dividend|split
    trade_date   = Column(Date, nullable=False)
    quantity     = Column(Float)                         # split: factor
    price        = Column(Float)                         # NULL → mercado de la fecha
    commission   = Column(Float, nullable=False, default=0.0)
    taxes        = Column(Float, nullable=False, default=0.0)
    currency     = Column(String(10))
    note         = Column(String(255))
    created_at   = Column(DateTime, nullable=False, default=datetime.utcnow)
