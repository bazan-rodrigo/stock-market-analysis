"""Token de conexión de IA (MCP) en `users`: hash + fecha de generación.

Un cliente de IA (Claude, ChatGPT, cualquiera que hable MCP) se conecta al
servidor MCP de la aplicación por HTTP y pide datos. El servidor corre FUERA de
Flask, así que no hay `current_user` del que deducir quién pregunta — y sin eso
no se puede aplicar el gate de visibilidad, que es lo único que impide que un
analista lea las definiciones privadas de otro. El token es esa identidad.

Lo que NO es: la credencial del proveedor de IA. Esa se queda en el cliente del
usuario y la plataforma nunca la ve — es la razón de haber elegido MCP en vez
de un panel dentro de la app.

Se reusa `users` en vez de crear una tabla: un token por usuario alcanza, y
revocar es poner el hash en NULL.

**SHA-256 y no bcrypt** (que es lo que usa `password_hash`, dos columnas más
allá): una contraseña es adivinable y conviene que verificarla sea lenta a
propósito; un token de 256 bits aleatorios no lo es. Y bcrypt saltea cada hash,
así que no se podría BUSCAR por hash — habría que traer todos los usuarios y
comparar uno por uno en cada llamada. Con SHA-256 hexadecimal (64 caracteres,
longitud fija) la búsqueda es un índice único.

Portable (post-0076): dos ADD COLUMN de nombre fijo sobre una tabla que ya
existe, más un índice único. Se renderiza offline en ambos dialectos
(tests/test_bootstrap_portability).

Las columnas nacen NULL: nadie tiene token hasta generarlo desde la pantalla
«Conexión IA». Aplicar esta migración no habilita ningún acceso por sí sola.
"""
import sqlalchemy as sa
from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None

# Autocontenido (snapshot): NO importar app.
_TABLE = "users"
_HASH = "mcp_token_hash"
_CREATED = "mcp_token_created_at"
_INDEX = "ix_users_mcp_token_hash"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column(_HASH, sa.String(64), nullable=True))
    op.add_column(_TABLE, sa.Column(_CREATED, sa.DateTime(), nullable=True))
    # Único: dos usuarios no pueden compartir token, y además es el índice por
    # el que entra CADA llamada del servidor MCP. Los NULL no colisionan entre
    # sí en ningún motor, así que los usuarios sin token conviven sin problema.
    op.create_index(_INDEX, _TABLE, [_HASH], unique=True)


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, _CREATED)
    op.drop_column(_TABLE, _HASH)
