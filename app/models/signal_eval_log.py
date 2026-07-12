from sqlalchemy import Column, Date, Integer, String

from app.database import Base


class SignalEvalLog(Base):
    """Fechas ya evaluadas por el backfill de señales/estrategias.

    Distingue "corrió y produjo 0 resultados" (legítimo: nadie pasó el
    filtro de elegibilidad ese día, o la señal no tenía datos) de "nunca
    corrió": sin este registro, esas fechas parecen huecos y el delta las
    recorre completas en CADA corrida (visto con ^GSPC: 1927→1993 casi
    vacío se reprocesaba entero en cada 'Calcular historia').

    scope_kind/ref_id: "strategy"/strategy_id, "signal"/signal_id, o
    "all"/0 (corrida sin alcance). Un force/rebuild ignora este registro
    (recalcula todo igual) pero lo repuebla.
    """

    __tablename__ = "signal_eval_log"

    scope_kind = Column(String(10), primary_key=True)  # strategy|signal|all
    ref_id     = Column(Integer,    primary_key=True)  # id según kind (all=0)
    date       = Column(Date,       primary_key=True)
