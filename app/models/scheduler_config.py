from sqlalchemy import Boolean, Column, Integer
from app.database import Base


class SchedulerConfig(Base):
    __tablename__ = "scheduler_config"

    id      = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, nullable=False, default=False)
    hour    = Column(Integer, nullable=False, default=18)
    minute  = Column(Integer, nullable=False, default=0)
