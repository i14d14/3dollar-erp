import json
import uuid
from decimal import Decimal
from pathlib import Path
import unittest
from starlette.testclient import TestClient

from src.channel_ui.web.app import app
from src.core.domain.order import OrderStatus
from src.core.domain.procurement import POStatus
from src.shared.database import Database


class TestIteration0923Batch2(unittest.TestCase):
    """Targeted tests for Batch 2: CRM Auto-Lock, Customer Name Display, and BOM Batch Undo."""

    def setUp(self):
        self.client = TestClient(app)
        self.db: Database = app.state.db

    def test_crm_won_deal_automatically_locks_inventory(self):
        # 1. Create a contact and a deal with quote
        with self.db.transaction() as conn:
            c = conn.execute("SELECT contact_id FROM crm_contacts LIMIT 1").fetchone()
            contact_id = c["contact_id"]

        unique_title = f"Batch2自動鎖庫商機測試_{uuid.uuid4().hex[:6]}"
        resp_deal = self.client.post(
            "/crm/deals",
            data={
                "contact_id": contact_id,
                "title": unique_title,
                "sku_1": "SKU-PRO-01",
                "qty_1": "2",
                "price_1": "2000",
                "stage": "PROPOSAL",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp_deal.status_code, 200)

        with self.db.transaction() as conn:
            deal_row = conn.execute("SELECT deal_id FROM crm_deals WHERE title = ?", (unique_title,)).fetchone()
            deal_id = deal_row["deal_id"]

        # 2. Convert to ERP order
        conv_resp = self.client.post(
            f"/crm/deals/{deal_id}/convert-to-order",
            data={"warehouse_id": "WH-MAIN"},
            headers={"HX-Request": "true"},
        )
        self.assertEqual(conv_resp.status_code, 200)
        self.assertIn("商機已成功拋轉為 ERP 銷售訂單", conv_resp.text)

        # 3. Verify order in DB is CONFIRMED and stock lock exists
        with self.db.transaction() as conn:
            won_deal = conn.execute("SELECT stage, converted_order_id FROM crm_deals WHERE deal_id = ?", (deal_id,)).fetchone()
            self.assertEqual(won_deal["stage"], "WON")
            order_id = won_deal["converted_order_id"]

            so = conn.execute("SELECT status, warehouse_id FROM sales_orders WHERE order_id = ?", (order_id,)).fetchone()
            self.assertEqual(so["status"], OrderStatus.CONFIRMED.value)
            self.assertEqual(so["warehouse_id"], "WH-MAIN")

            # Check stock lock
            lock = conn.execute("SELECT locked_qty FROM stock_locks WHERE order_id = ? AND sku = 'SKU-PRO-01'", (order_id,)).fetchone()
            self.assertIsNotNone(lock)
            self.assertEqual(float(lock["locked_qty"]), 2.0)

    def test_orders_list_displays_customer_name_from_contacts(self):
        # Visit /orders and ensure customer name is rendered
        resp = self.client.get("/orders")
        self.assertEqual(resp.status_code, 200)
        # Seed data has contacts with company names
        # Check that company name appears in the orders table
        view_service = app.state.view_service
        orders = view_service.list_orders(limit=10)
        crm_orders = [o for o in orders if o.customer_name and o.customer_name != o.customer_id]
        if crm_orders:
            sample = crm_orders[0]
            self.assertIn(sample.customer_name, resp.text)
            self.assertIn(sample.customer_id, resp.text)

    def test_bom_create_pos_returns_undo_and_undo_cancels_pos(self):
        # 1. Create batch POs via BOM split endpoint
        supp_a = f"測試甲供應商_{uuid.uuid4().hex[:6]}"
        supp_b = f"測試乙供應商_{uuid.uuid4().hex[:6]}"
        split_items = [
            {"sku": "SKU-PRO-01", "name": "智慧旗艦終端機", "qty": 5, "unit_cost": 1500, "supplier_name": supp_a},
            {"sku": "SKU-ACC-02", "name": "高速傳輸擴充底座", "qty": 10, "unit_cost": 500, "supplier_name": supp_b},
        ]
        created_po_ids = []
        try:
            resp = self.client.post(
                "/procurement/bom/create-pos",
                data={"items_json": json.dumps(split_items)},
                headers={"HX-Request": "true"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("/procurement/bom/create-pos/undo", resp.text)
            self.assertIn("撤回建立", resp.text)

            # Extract PO ids created from DB
            with self.db.transaction() as conn:
                pos = conn.execute(
                    "SELECT po_id, status FROM purchase_orders WHERE supplier_name IN (?, ?) AND status = 'DRAFT' ORDER BY created_at DESC LIMIT 2",
                    (supp_a, supp_b),
                ).fetchall()
                self.assertEqual(len(pos), 2)
                created_po_ids = [p["po_id"] for p in pos]
                po_ids_str = ",".join(created_po_ids)

            # 2. Call undo endpoint
            undo_resp = self.client.post(
                "/procurement/bom/create-pos/undo",
                data={"po_ids": po_ids_str},
                headers={"HX-Request": "true"},
            )
            self.assertEqual(undo_resp.status_code, 200)
            self.assertIn("已成功撤回 BOM 自動分割建立之 2 張採購單", undo_resp.text)

            # 3. Verify POs in DB are now CANCELED
            with self.db.transaction() as conn:
                for po_id in created_po_ids:
                    po_status = conn.execute("SELECT status FROM purchase_orders WHERE po_id = ?", (po_id,)).fetchone()
                    self.assertEqual(po_status["status"], POStatus.CANCELLED.value)
        finally:
            if created_po_ids:
                with self.db.transaction() as conn:
                    placeholders = ",".join("?" for _ in created_po_ids)
                    conn.execute(f"DELETE FROM purchase_order_items WHERE po_id IN ({placeholders})", created_po_ids)
                    conn.execute(f"DELETE FROM purchase_orders WHERE po_id IN ({placeholders})", created_po_ids)

    def test_bom_create_pos_rejects_when_all_unassigned_or_zero_cost(self):
        with self.db.transaction() as conn:
            initial_count = conn.execute("SELECT count(*) FROM purchase_orders").fetchone()[0]

        # Items with no supplier or zero cost
        invalid_items = [
            {"sku": "SKU-TEST-UNK-1", "name": "未知物料1", "qty": 10, "unit_cost": 0, "supplier_name": ""},
            {"sku": "SKU-TEST-UNK-2", "name": "未知物料2", "qty": 5, "unit_cost": 0, "supplier_name": "未指定供應商"},
        ]
        resp = self.client.post(
            "/procurement/bom/create-pos",
            data={"items_json": json.dumps(invalid_items)},
            headers={"HX-Request": "true"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("BOM 查無有效物料可建立採購單", resp.text)

        # Verify no new PO was created in DB
        with self.db.transaction() as conn:
            after_count = conn.execute("SELECT count(*) FROM purchase_orders").fetchone()[0]
            self.assertEqual(initial_count, after_count)

    def test_bom_create_pos_skips_unassigned_and_creates_valid(self):
        unique_supp = f"有效合格廠商_{uuid.uuid4().hex[:6]}"
        test_sku = f"SKU-TEST-{uuid.uuid4().hex[:6].upper()}"
        mixed_items = [
            {"sku": test_sku, "name": "測試暫存物料", "qty": 8, "unit_cost": 350, "supplier_name": unique_supp},
            {"sku": "SKU-INVALID-02", "name": "無廠商物料", "qty": 12, "unit_cost": 0, "supplier_name": ""},
        ]
        try:
            resp = self.client.post(
                "/procurement/bom/create-pos",
                data={"items_json": json.dumps(mixed_items)},
                headers={"HX-Request": "true"},
            )
            self.assertEqual(resp.status_code, 200)
            # Toast should indicate 1 supplier created, and 1 item skipped
            self.assertIn("成功為 1 家供應商自動分割建立採購單", resp.text)
            self.assertIn("另有 1 筆物料因未指定供應商或單價為 0 已自動排除", resp.text)

            with self.db.transaction() as conn:
                po = conn.execute("SELECT po_id, total_amount FROM purchase_orders WHERE supplier_name = ?", (unique_supp,)).fetchone()
                self.assertIsNotNone(po)
                self.assertEqual(float(po["total_amount"]), 8 * 350.0)
        finally:
            with self.db.transaction() as conn:
                conn.execute("DELETE FROM purchase_order_items WHERE sku = ?", (test_sku,))
                conn.execute("DELETE FROM purchase_orders WHERE supplier_name = ?", (unique_supp,))
                conn.execute("DELETE FROM warehouse_stock_levels WHERE sku = ?", (test_sku,))
                conn.execute("DELETE FROM products WHERE sku = ?", (test_sku,))


if __name__ == "__main__":
    unittest.main()
