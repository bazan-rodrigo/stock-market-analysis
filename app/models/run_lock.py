from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class RunLock(Base):
    """Lock de corrida PERSISTIDO en la BD, con heartbeat. Reemplaza (y
    endurece) la exclusión mutua en memoria del Centro de Datos
    (_any_running), que se pierde al reciclarse el proceso WSGI y no
    coordina entre procesos.

    Una fila por operación pesada (op = 'indicators', 'prices',
    'signals', 'daily'...). Mientras la corrida vive, un thread actualiza
    `heartbeat`; si el proceso muere (reciclado de mod_wsgi, OOM), el
    heartbeat deja de avanzar y otro proceso puede reclamar el lock pasado
    el umbral de obsolescencia — cerrando el agujero de la doble corrida
    con hijos huérfanos del ProcessPool. La UI usa el heartbeat para
    distinguir 'abortada por reciclado' de 'corriendo' y destrabar el
    botón sin recargar.
    """
    __tablename__ = "run_lock"

    op         = Column(String(64), primary_key=True)
    # Token de propiedad único POR ADQUISICIÓN (no el pid): beat y release
    # solo operan si el token coincide. En un despliegue de un solo proceso
    # WSGI, el Centro de Datos y el scheduler comparten pid — sin el token,
    # un stale-reclaim del mismo pid dejaría que una corrida vieja pise el
    # lock de la que reclamó (release/beat por pid pisarían el lock ajeno).
    token      = Column(String(32), nullable=False)
    pid        = Column(Integer, nullable=False)
    host       = Column(String(255), nullable=True)
    started_at = Column(DateTime, nullable=False)
    heartbeat  = Column(DateTime, nullable=False)
