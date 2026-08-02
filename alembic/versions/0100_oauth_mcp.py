"""Servidor OAuth del MCP: clientes registrados y concesiones emitidas.

Por qué hace falta. El token de `users.mcp_token_hash` (0099) alcanza para
cualquier cliente que permita mandar un header `Authorization`, pero **los
conectores remotos de las aplicaciones de IA no lo permiten**: hacen registro
dinámico de cliente y después el flujo de OAuth. Sin un servidor de
autorización detrás, agregar el conector falla con "no se pudo registrar con el
servicio de inicio de sesión". Pasó en el primer intento real.

El token de 0099 NO se reemplaza: sigue siendo la credencial de la persona y es
lo que se pide en la pantalla de autorización. OAuth queda como el envoltorio
que el protocolo exige; la identidad de fondo sigue siendo la misma, y por eso
revocar el token corta también las sesiones OAuth.

Se persiste todo (no memoria): un redeploy reinicia el proceso, y si los
clientes registrados vivieran en memoria cada deploy desconectaría a todos sin
ningún error que lo explicara.

Portable (post-0076): tipos genéricos y DDL de nombre fijo → se renderiza
offline en ambos dialectos (tests/test_bootstrap_portability). Espeja
app/models/oauth.py.
"""
import sqlalchemy as sa
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_client",
        sa.Column("client_id", sa.String(255), primary_key=True),
        # El documento completo del protocolo, tal como lo entrega el SDK: no
        # se desarma en columnas para que una versión nueva que agregue campos
        # no pierda información ni exija otra migración.
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "oauth_grant",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # pending | code | access | refresh
        sa.Column("kind", sa.String(10), nullable=False),
        # SHA-256 hex del valor. Nunca se guarda el valor.
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Integer()),
        sa.Column("scopes", sa.Text()),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.Text()),
        sa.Column("code_challenge", sa.String(255)),
        sa.Column("redirect_uri", sa.Text()),
        sa.Column("redirect_uri_explicit", sa.Boolean()),
        sa.Column("resource", sa.Text()),
    )
    # Único: es el índice por el que entra CADA llamada autenticada.
    op.create_index("ix_oauth_grant_token_hash", "oauth_grant",
                    ["token_hash"], unique=True)
    op.create_index("ix_oauth_grant_kind", "oauth_grant", ["kind"])
    op.create_index("ix_oauth_grant_client_id", "oauth_grant", ["client_id"])
    # Para la purga de vencidas, que corre seguido y no debería escanear todo.
    op.create_index("ix_oauth_grant_expires_at", "oauth_grant", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_oauth_grant_expires_at", table_name="oauth_grant")
    op.drop_index("ix_oauth_grant_client_id", table_name="oauth_grant")
    op.drop_index("ix_oauth_grant_kind", table_name="oauth_grant")
    op.drop_index("ix_oauth_grant_token_hash", table_name="oauth_grant")
    op.drop_table("oauth_grant")
    op.drop_table("oauth_client")
