from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


class RunHistory(Base):
    """Bitácora PERSISTIDA de corridas pesadas (Centro de Datos y scheduler).

    Reemplaza —para lo que hace a "¿qué corrió y cómo terminó?"— el historial
    en memoria de write_stats_service (deque(20)), que se pierde al reciclarse
    el proceso. El caso que motiva esto: si el contenedor muere a mitad de una
    corrida (deploy, reemplazo, OOM), no quedaba NINGÚN rastro consultable de
    que hubo una corrida ni de que se cortó (solo los logs de Railway).

    Ciclo de una fila:
    - start_run inserta status='running' con started_at (finished_at NULL).
    - finish_run la cierra con status ok/error + total/ok/first_error.
    - Si el proceso muere antes de finish_run, la fila queda 'running' para
      siempre; al próximo arranque abort_orphans() la marca 'aborted' (un
      final limpio SIEMPRE deja ok/error, así que un 'running' remanente es
      por definición una corrida que murió). Supone 1 worker (la realidad de
      Railway, mismo supuesto que run_lock).

    Retención: prune_old() la poda por antigüedad al arranque. La tabla crece
    ~pocas filas por día (nocturna + manuales), así que es diminuta; la poda
    es prolijidad, no footprint.
    """

    __tablename__ = "run_history"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    op          = Column(String(32), nullable=False)   # prices|fund|indicators|signals|daily…
    scope       = Column(String(64), nullable=True)    # nombre de fn / all / strategy:5 …
    status      = Column(String(12), nullable=False)   # running|ok|error|aborted
    started_at  = Column(DateTime, nullable=False, default=datetime.utcnow,
                         index=True)                    # ix_run_history_started_at
    finished_at = Column(DateTime, nullable=True)
    total       = Column(Integer, nullable=True)        # nº declarado por el servicio
    unit        = Column(String(16), nullable=True)     # unidad de `total` (activos/fechas/…)
    ok          = Column(Integer, nullable=True)        # de esos, exitosos
    first_error = Column(Text, nullable=True)
    pid         = Column(Integer, nullable=True)
    host        = Column(String(255), nullable=True)
