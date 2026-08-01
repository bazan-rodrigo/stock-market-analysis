from datetime import datetime

import bcrypt
from flask_login import UserMixin
from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String

from app.database import Base


class User(UserMixin, Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    # name=: obligatorio para PostgreSQL (CREATE TYPE); MySQL lo ignora y
    # sigue rindiendo ENUM('admin','analyst') idéntico al esquema histórico
    role = Column(Enum("admin", "analyst", name="user_role"),
                  nullable=False, default="analyst")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # ── Conexión de un cliente de IA por MCP (migración 0099) ────────────────
    # Identidad del usuario ante el servidor MCP, que corre fuera de Flask y no
    # tiene `current_user` del que deducir quién pregunta. NO es la credencial
    # del proveedor de IA: esa vive en el cliente del usuario y la plataforma
    # nunca la ve.
    # SHA-256 hex (64 chars) y no bcrypt como `password_hash`: un token de 256
    # bits aleatorios no es adivinable, y bcrypt saltea cada hash, así que no
    # permitiría BUSCAR por hash en cada llamada. Ver app/ai/tokens.py.
    mcp_token_hash = Column(String(64), unique=True, index=True)
    mcp_token_created_at = Column(DateTime)

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(
            password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    def get_id(self) -> str:
        return str(self.id)

    @property
    def is_active(self) -> bool:
        return self.active

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
