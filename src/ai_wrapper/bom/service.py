from __future__ import annotations
from decimal import Decimal
from typing import List, Optional

from src.ai_wrapper.bom.models import (
    BomComparisonItem,
    BomComparisonSummary,
    BomItem,
    BomParseResult,
    SupplierPriceQuote,
)
from src.shared.database import Database, default_db


class BomComparisonService:
    """Service to compare BOM requirements against historical multi-supplier purchasing records."""

    def __init__(self, db: Database = default_db) -> None:
        self.db = db

    def get_supplier_quotes_for_sku(self, sku: str) -> List[SupplierPriceQuote]:
        """Fetch all historical supplier purchase quotes for a given SKU, ordered by unit cost asc."""
        quotes: List[SupplierPriceQuote] = []
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT po.supplier_name, poi.unit_cost, po.po_id, po.created_at
                FROM purchase_order_items poi
                JOIN purchase_orders po ON poi.po_id = po.po_id
                WHERE poi.sku = ?
                ORDER BY poi.unit_cost ASC
                """,
                (sku,),
            ).fetchall()

            seen_suppliers = set()
            for r in rows:
                supplier = r["supplier_name"]
                # Keep the best (lowest) quote per supplier if duplicates exist
                if supplier not in seen_suppliers:
                    seen_suppliers.add(supplier)
                    quotes.append(
                        SupplierPriceQuote(
                            supplier_name=supplier,
                            unit_cost=Decimal(str(r["unit_cost"])),
                            po_id=r["po_id"],
                            order_date=str(r["created_at"])[:10] if r["created_at"] else None,
                        )
                    )
        return quotes

    def get_standard_cost_for_sku(self, sku: str) -> Decimal:
        """Fetch standard catalog cost from products table."""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT cost_price FROM products WHERE sku = ?", (sku,)).fetchone()
            if row and row["cost_price"] is not None:
                return Decimal(str(row["cost_price"]))
        return Decimal("0.0")

    def compare_bom(self, bom_result: BomParseResult) -> BomComparisonSummary:
        """Execute price comparison for all items in a parsed BOM."""
        comparison_items: List[BomComparisonItem] = []
        unquoted_skus: List[str] = []

        total_qty = Decimal("0.0")
        total_lowest = Decimal("0.0")
        total_highest = Decimal("0.0")
        total_standard = Decimal("0.0")

        for item in bom_result.items:
            total_qty += item.qty
            standard_cost = self.get_standard_cost_for_sku(item.sku)
            quotes = self.get_supplier_quotes_for_sku(item.sku)

            if quotes:
                lowest = quotes[0]
                highest = max(quotes, key=lambda q: q.unit_cost)
                sub_low = item.qty * lowest.unit_cost
                sub_high = item.qty * highest.unit_cost
                savings = sub_high - sub_low
                has_history = True
            else:
                lowest = None
                highest = None
                sub_low = item.qty * standard_cost
                sub_high = item.qty * standard_cost
                savings = Decimal("0.0")
                has_history = False
                unquoted_skus.append(item.sku)

            sub_std = item.qty * standard_cost
            total_lowest += sub_low
            total_highest += sub_high
            total_standard += sub_std

            comparison_items.append(
                BomComparisonItem(
                    sku=item.sku,
                    name=item.name,
                    spec=item.spec,
                    qty=item.qty,
                    unit=item.unit,
                    standard_cost=standard_cost,
                    quotes=quotes,
                    lowest_quote=lowest,
                    highest_quote=highest,
                    estimated_subtotal_lowest=sub_low,
                    estimated_subtotal_highest=sub_high,
                    potential_savings=savings,
                    has_history=has_history,
                )
            )

        total_potential_savings = total_highest - total_lowest

        return BomComparisonSummary(
            total_skus=len(bom_result.items),
            total_qty=total_qty,
            total_cost_lowest=total_lowest,
            total_cost_highest=total_highest,
            total_cost_standard=total_standard,
            total_potential_savings=total_potential_savings,
            items=comparison_items,
            unquoted_skus=unquoted_skus,
        )
