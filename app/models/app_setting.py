from sqlalchemy import Boolean, Column, Integer
from app.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    id             = Column(Integer, primary_key=True, default=1)
    public_access  = Column(Boolean, nullable=False, default=False)
