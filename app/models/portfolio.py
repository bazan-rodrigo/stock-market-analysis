from datetime import datetime

from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey,
                        Integer, String, Text)

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
    # ── Composición (sólo teóricas, ptype='seg') ──
    # composition_method: 'curated' (lista PortfolioMember) | 'strategy' (top-N
    # de una estrategia) | 'rule' (regla dinámica, rule_json — se implementa
    # después). strategy_id: Integer plano (sin FK de BD — el servicio tolera que
    # la estrategia ya no exista). rebalance: cada cuántas ruedas se recalcula.
    composition_method  = Column(String(10))
    strategy_id         = Column(Integer)
    top_n               = Column(Integer)
    rebalance           = Column(Integer)
    rule_json           = Column(Text)
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


class PortfolioMember(Base):
    """Miembro de una cartera teórica CURADA (lista estática de activos).

    `weight` opcional: si todos son None, la cartera es equal-weight entre sus
    miembros.
    """

    __tablename__ = "portfolio_member"

    id           = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer,
                          ForeignKey("portfolio.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    asset_id     = Column(Integer,
                          ForeignKey("assets.id", ondelete="CASCADE"),
                          nullable=False)
    weight       = Column(Float)


class PortfolioRun(Base):
    """Snapshot inmutable de una corrida de backtest de cartera (nivel C) —
    para poder compararlas lado a lado (nivel D)."""

    __tablename__ = "portfolio_run"

    id          = Column(Integer, primary_key=True)
    owner_id    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    strategy_id = Column(Integer)
    name        = Column(String(120))
    config      = Column(Text)      # JSON: top_n / rebalance / cost / spec
    summary     = Column(Text)      # JSON: KPIs por sub-modo
    created_at  = Column(DateTime, nullable=False, default=datetime.utcnow)


class PortfolioRunPoint(Base):
    """Punto de la serie de equity de una corrida, por sub-modo
    ('gated' | 'ranking' | 'benchmark')."""

    __tablename__ = "portfolio_run_point"

    id      = Column(Integer, primary_key=True)
    run_id  = Column(Integer,
                     ForeignKey("portfolio_run.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    submode = Column(String(12))
    date    = Column(Date, nullable=False)
    value   = Column(Float)
