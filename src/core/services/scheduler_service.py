from __future__ import annotations
import datetime
import sqlite3
from decimal import Decimal
from typing import List, Optional

from src.core.domain.invoice import AccountsReceivable, ARStatus
from src.core.services.inventory_service import InventoryService
from src.shared.base_models import DomainModel
from src.shared.database import Database, default_db


class LowStockAlert(DomainModel):
    sku: str
    product_name: str
    warehouse_id: str
    current_balance: Decimal
    locked_stock: Decimal
    available_stock: Decimal
    safety_stock: int
    shortage: Decimal


class DailyBatchSummary(DomainModel):
    batch_date: datetime.date
    low_stock_alerts: List[LowStockAlert]
    overdue_receivables: List[AccountsReceivable]
    total_low_stock_items: int
    total_overdue_ar_items: int
    total_overdue_amount: Decimal


class SchedulerService:
    def __init__(self, db: Database = default_db, inventory_service: Optional[InventoryService] = None) -> None:
        self.db = db
        self.inventory_service = inventory_service or InventoryService(db=db)

    def scan_low_safety_stock(self, warehouse_id: Optional[str] = None) -> List[LowStockAlert]:
        """Scan products across warehouses where available stock falls at or below safety stock threshold."""
        alerts: List[LowStockAlert] = []

        with self.db.transaction() as conn:
            # Query items configured in warehouse_stock_levels for active warehouses and active products
            levels_query = """
                SELECT w.warehouse_id, p.sku, p.name as product_name,
                       wsl.safety_stock as safety_stock
                FROM warehouse_stock_levels wsl
                JOIN warehouses w ON w.warehouse_id = wsl.warehouse_id
                JOIN products p ON p.sku = wsl.sku
                WHERE w.is_active = 1 AND p.is_active = 1 AND wsl.safety_stock > 0
            """
            params: List[str] = []
            if warehouse_id:
                levels_query += " AND w.warehouse_id = ?"
                params.append(warehouse_id)
            levels_query += " ORDER BY w.warehouse_id, p.sku"

            level_rows = conn.execute(levels_query, tuple(params)).fetchall()

            # If warehouse_stock_levels is globally empty (e.g. isolated legacy unit test), fallback to product catalog
            total_levels_row = conn.execute("SELECT COUNT(*) as c FROM warehouse_stock_levels").fetchone()
            is_globally_empty = (not total_levels_row or total_levels_row["c"] == 0)

            if is_globally_empty:
                prod_rows = conn.execute(
                    "SELECT sku, name, safety_stock FROM products WHERE is_active = 1 AND safety_stock > 0"
                ).fetchall()
                if warehouse_id:
                    wh_rows = conn.execute(
                        "SELECT warehouse_id FROM warehouses WHERE warehouse_id = ? AND is_active = 1",
                        (warehouse_id,),
                    ).fetchall()
                else:
                    wh_rows = conn.execute("SELECT warehouse_id FROM warehouses WHERE is_active = 1").fetchall()

                for wh in wh_rows:
                    wh_id = wh["warehouse_id"]
                    for prod in prod_rows:
                        sku = prod["sku"]
                        safety = prod["safety_stock"]
                        balance = self.inventory_service.get_stock_balance(wh_id, sku)
                        locked = self.inventory_service.get_locked_stock(wh_id, sku)
                        available = balance - locked
                        if available <= Decimal(str(safety)):
                            alerts.append(
                                LowStockAlert(
                                    sku=sku,
                                    product_name=prod["name"],
                                    warehouse_id=wh_id,
                                    current_balance=balance,
                                    locked_stock=locked,
                                    available_stock=available,
                                    safety_stock=safety,
                                    shortage=Decimal(str(safety)) - available,
                                )
                            )
                return alerts

            for r in level_rows:
                wh_id = r["warehouse_id"]
                sku = r["sku"]
                safety = int(r["safety_stock"])
                balance = self.inventory_service.get_stock_balance(wh_id, sku)
                locked = self.inventory_service.get_locked_stock(wh_id, sku)
                available = balance - locked
                if available <= Decimal(str(safety)):
                    alerts.append(
                        LowStockAlert(
                            sku=sku,
                            product_name=r["product_name"],
                            warehouse_id=wh_id,
                            current_balance=balance,
                            locked_stock=locked,
                            available_stock=available,
                            safety_stock=safety,
                            shortage=Decimal(str(safety)) - available,
                        )
                    )

        return alerts

    def scan_overdue_receivables(self, as_of_date: Optional[datetime.date] = None) -> List[AccountsReceivable]:
        """Scan unpaid accounts receivable past their due date and transition them to OVERDUE."""
        target_date = as_of_date or datetime.date.today()
        target_str = target_date.isoformat()
        overdue_list: List[AccountsReceivable] = []

        with self.db.transaction() as conn:
            # Transition eligible UNPAID/PARTIAL receivables to OVERDUE
            conn.execute(
                """
                UPDATE accounts_receivable
                SET status = 'OVERDUE'
                WHERE due_date < ? AND status IN ('UNPAID', 'PARTIAL')
                """,
                (target_str,),
            )

            # Retrieve all overdue receivables
            rows = conn.execute(
                """
                SELECT ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status
                FROM accounts_receivable
                WHERE status = 'OVERDUE'
                ORDER BY due_date ASC
                """
            ).fetchall()

            for r in rows:
                due_d = datetime.date.fromisoformat(r["due_date"])
                overdue_list.append(
                    AccountsReceivable(
                        ar_id=r["ar_id"],
                        order_id=r["order_id"],
                        invoice_id=r["invoice_id"],
                        customer_id=r["customer_id"],
                        due_date=due_d,
                        amount=Decimal(str(r["amount"])),
                        paid_amount=Decimal(str(r["paid_amount"])),
                        status=ARStatus.OVERDUE,
                    )
                )

        return overdue_list

    def run_daily_batch(self, as_of_date: Optional[datetime.date] = None) -> DailyBatchSummary:
        """Run the daily automated maintenance batch for ERP inventory and finance."""
        today = as_of_date or datetime.date.today()
        low_stock = self.scan_low_safety_stock()
        overdue_ar = self.scan_overdue_receivables(as_of_date=today)

        total_overdue_amt = sum((ar.amount - ar.paid_amount for ar in overdue_ar), Decimal("0.0"))

        return DailyBatchSummary(
            batch_date=today,
            low_stock_alerts=low_stock,
            overdue_receivables=overdue_ar,
            total_low_stock_items=len(low_stock),
            total_overdue_ar_items=len(overdue_ar),
            total_overdue_amount=total_overdue_amt,
        )
