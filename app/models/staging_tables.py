"""Tablas STAGING del backfill acotado de señales/estrategias.

Los recálculos acotados (una señal/estrategia) escriben acá primero —
tablas vacías con UN solo índice (la clave natural): inserción masiva al
costo mínimo, la misma ventaja que el TRUNCATE le da al recálculo completo.
Después un merge por ventanas pasa a las oficiales SOLO las diferencias
(UPDATE in-place de cambiados / INSERT de nuevos / DELETE de obsoletos) —
ver signal_backfill_range. La oficial queda intacta hasta el merge: un
crash a mitad del recálculo no pierde nada.

Sin columna id: la clave natural compuesta es el único índice a mantener.
Se vacían al inicio y al final de cada corrida staging.
"""
from sqlalchemy import Column, Date, Float, Integer, String

from app.database import Base


class SignalValueStaging(Base):
    __tablename__ = "signal_value_staging"

    signal_id = Column(Integer, primary_key=True, autoincrement=False)
    asset_id  = Column(Integer, primary_key=True, autoincrement=False)
    date      = Column(Date,    primary_key=True)
    score     = Column(Float)


class GroupSignalValueStaging(Base):
    __tablename__ = "group_signal_value_staging"

    signal_id  = Column(Integer,    primary_key=True, autoincrement=False)
    group_type = Column(String(30), primary_key=True)
    group_id   = Column(Integer,    primary_key=True, autoincrement=False)
    date       = Column(Date,       primary_key=True)
    score      = Column(Float)


class GroupScoreStaging(Base):
    __tablename__ = "group_scores_staging"

    group_type     = Column(String(30), primary_key=True)
    group_id       = Column(Integer,    primary_key=True, autoincrement=False)
    date           = Column(Date,       primary_key=True)
    regime_score_d = Column(Float)
    regime_score_w = Column(Float)
    regime_score_m = Column(Float)
    n_assets       = Column(Integer)


class StrategyResultStaging(Base):
    __tablename__ = "strategy_result_staging"

    strategy_id = Column(Integer, primary_key=True, autoincrement=False)
    asset_id    = Column(Integer, primary_key=True, autoincrement=False)
    date        = Column(Date,    primary_key=True)
    score       = Column(Float)
    pct         = Column(Float)
