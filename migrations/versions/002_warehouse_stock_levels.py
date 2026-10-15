"""002_warehouse_stock_levels

Revision ID: 002_warehouse_stock_levels
Revises: 001_initial_schema
Create Date: 2026-09-24 11:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_warehouse_stock_levels"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "warehouse_stock_levels",
        sa.Column("warehouse_id", sa.String(), sa.ForeignKey("warehouses.warehouse_id"), primary_key=True),
        sa.Column("sku", sa.String(), sa.ForeignKey("products.sku"), primary_key=True),
        sa.Column("safety_stock", sa.Integer(), server_default="10", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_wh_stock_levels_sku", "warehouse_stock_levels", ["sku"])

    # Backfill warehouse_stock_levels from existing stock_ledger and products
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO warehouse_stock_levels (warehouse_id, sku, safety_stock)
            SELECT DISTINCT l.warehouse_id, l.sku, COALESCE(p.safety_stock, 10)
            FROM stock_ledger l
            JOIN products p ON p.sku = l.sku
            WHERE NOT EXISTS (
                SELECT 1 FROM warehouse_stock_levels wsl
                WHERE wsl.warehouse_id = l.warehouse_id AND wsl.sku = l.sku
            );
        """)
    )


def downgrade() -> None:
    op.drop_index("idx_wh_stock_levels_sku", table_name="warehouse_stock_levels")
    op.drop_table("warehouse_stock_levels")
