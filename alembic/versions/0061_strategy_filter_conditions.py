"""Filtro de elegibilidad en estrategias: arbol de condiciones AND/OR
(strategy.filter_conditions, JSON) que se evalua antes del scoring — el
activo que no cumple no aparece en strategy_result.

Reemplaza y absorbe a asset_filter (JSON plano de igualdades por atributo):
cada {"sector_id": 3, ...} existente se convierte a un arbol equivalente
{"op": "AND", "children": [{"cond": {"left": {"type": "attribute",
"key": "sector"}, "operator": "=", "right": {"type": "const", "value": 3}}}]}
y la columna asset_filter se elimina.

Revision ID: 0061
Revises: 0060
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

# asset_filter usaba columnas FK ("sector_id"); el arbol usa el nombre del
# atributo a secas ("sector") — mismo criterio que StrategyComponent.group_type.
_ATTR_BY_COLUMN = {
    "sector_id":          "sector",
    "market_id":          "market",
    "industry_id":        "industry",
    "country_id":         "country",
    "instrument_type_id": "instrument_type",
}


def _asset_filter_to_tree(asset_filter: str | None) -> str | None:
    try:
        flt = json.loads(asset_filter) or {}
    except (json.JSONDecodeError, TypeError):
        return None
    children = [
        {"cond": {
            "left":     {"type": "attribute", "key": attr},
            "operator": "=",
            "right":    {"type": "const", "value": flt[col]},
        }}
        for col, attr in _ATTR_BY_COLUMN.items()
        if flt.get(col) is not None
    ]
    if not children:
        return None
    return json.dumps({"op": "AND", "children": children})


def _tree_to_asset_filter(filter_conditions: str | None) -> str | None:
    """Mejor esfuerzo para el downgrade: solo recupera condiciones de
    atributo con '=' del nivel raiz AND — lo unico expresable en el formato
    viejo. El resto del arbol se pierde."""
    try:
        tree = json.loads(filter_conditions) or {}
    except (json.JSONDecodeError, TypeError):
        return None
    if tree.get("op") != "AND":
        return None
    attr_to_col = {v: k for k, v in _ATTR_BY_COLUMN.items()}
    flt = {}
    for child in tree.get("children", []):
        cond = child.get("cond")
        if not cond or cond.get("operator") != "=":
            continue
        left, right = cond.get("left", {}), cond.get("right", {})
        col = attr_to_col.get(left.get("key"))
        if left.get("type") == "attribute" and col and right.get("type") == "const":
            flt[col] = right.get("value")
    return json.dumps(flt) if flt else None


def upgrade() -> None:
    op.add_column("strategy", sa.Column("filter_conditions", sa.Text(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, asset_filter FROM strategy WHERE asset_filter IS NOT NULL"
    )).fetchall()
    for sid, asset_filter in rows:
        tree = _asset_filter_to_tree(asset_filter)
        if tree is not None:
            bind.execute(
                sa.text("UPDATE strategy SET filter_conditions = :t WHERE id = :i"),
                {"t": tree, "i": sid},
            )

    op.drop_column("strategy", "asset_filter")


def downgrade() -> None:
    op.add_column("strategy", sa.Column("asset_filter", sa.Text(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, filter_conditions FROM strategy "
        "WHERE filter_conditions IS NOT NULL"
    )).fetchall()
    for sid, tree in rows:
        flt = _tree_to_asset_filter(tree)
        if flt is not None:
            bind.execute(
                sa.text("UPDATE strategy SET asset_filter = :f WHERE id = :i"),
                {"f": flt, "i": sid},
            )

    op.drop_column("strategy", "filter_conditions")
