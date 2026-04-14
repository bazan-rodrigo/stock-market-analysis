from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Integer, String, Text

from app.database import Base


class ImportLog(Base):
    """Resultado del último intento de importación para cada ticker."""

    __tablename__ = "import_log"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), nullable=False, unique=True)
    status = Column(
        Enum("imported", "skipped", "error"), nullable=False
    )
    detail = Column(Text)
    attempted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
