from datetime import datetime

from sqlalchemy import (Column, Date, DateTime, Float, ForeignKey, Integer,
                        String, Text)
from app.database import Base


class BacktestRun(Base):
    """Una corrida de backtest = snapshot reproducible.

    La config completa (horizontes, lag, cuantiles, mínimos, período) va en
    `config` como JSON: los resultados persistidos corresponden a ESA config
    y a la historia de strategy_result vigente al momento del run — el
    pipeline reescribe la historia con cada "Recalcular completo", por eso
    los números de un run no se recalculan nunca: se corre uno nuevo.
    """

    __tablename__ = "backtest_run"

    id           = Column(Integer, primary_key=True)
    strategy_id  = Column(Integer, ForeignKey("strategy.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    owner_id     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    config       = Column(Text, nullable=False)      # JSON de parámetros
    status       = Column(String(20), nullable=False, default="running")
    error        = Column(Text)
    date_from    = Column(Date)                      # rango efectivo analizado
    date_to      = Column(Date)
    n_dates      = Column(Integer)                   # fechas computadas
    duration_seconds = Column(Float)
    created_at   = Column(DateTime, nullable=False, default=datetime.utcnow)


class BacktestQuantileStat(Base):
    """Resumen agregado por (horizonte, cuantil) de un run — equal-weight por
    fecha (ver backtest_engine.aggregate_cross_sections)."""

    __tablename__ = "backtest_quantile_stat"

    id         = Column(Integer, primary_key=True)
    run_id     = Column(Integer, ForeignKey("backtest_run.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    horizon    = Column(Integer, nullable=False)   # ruedas
    quantile   = Column(Integer, nullable=False)   # 1..n (n = mejor score)
    n_dates    = Column(Integer, nullable=False)
    mean_ret   = Column(Float)
    median_ret = Column(Float)
    pct_pos    = Column(Float)


class BacktestIcPoint(Base):
    """Serie temporal por fecha de un run: IC (Spearman score→retorno
    forward), spread top−bottom y tamaño del universo, por horizonte."""

    __tablename__ = "backtest_ic_point"

    id       = Column(Integer, primary_key=True)
    run_id   = Column(Integer, ForeignKey("backtest_run.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    date     = Column(Date,    nullable=False)
    horizon  = Column(Integer, nullable=False)
    ic       = Column(Float)
    spread   = Column(Float)
    n_assets = Column(Integer, nullable=False)
