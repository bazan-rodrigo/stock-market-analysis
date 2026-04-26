"""índices en market_event.asset_id y market_event.scope

Las queries de get_events_for_assets filtran por asset_id.in_(...) y
scope = 'country' / 'global'. Sin índices, cada consulta hace full scan
sobre la tabla (crece con el tiempo).

Revision ID: 0028
Revises: 0027
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_market_event_asset_id", "market_event", ["asset_id"])
    op.create_index("ix_market_event_scope",    "market_event", ["scope"])


def downgrade() -> None:
    op.drop_index("ix_market_event_scope",    table_name="market_event")
    op.drop_index("ix_market_event_asset_id", table_name="market_event")
