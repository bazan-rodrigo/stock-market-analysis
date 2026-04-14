from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, scoped_session

from app.config import Config

engine = create_engine(
    Config.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

_SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Session = scoped_session(_SessionFactory)


class Base(DeclarativeBase):
    pass


def get_session():
    return Session()


def teardown_session(exception=None):
    """Llamar al final de cada request Flask para liberar la sesión."""
    Session.remove()
