from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.domain.inventory import ReferenceType
from src.core.services.inventory_service import InventoryService
from src.core.services.procurement_service import ProcurementService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestProcurementWeb(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_procurement_web.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.inventory_service = InventoryService(db=self.db)
        self.procurement_service = ProcurementService(db=self.db, event_bus=self.event_bus)

        # Seed warehouses
        self.inventory_service.create_warehouse("WH-MAIN", "台北總倉")
        self.inventory_service.create_warehouse("WH-STORE", "信義旗艦店")

        # Seed product
        self.inventory_service.create_product(
            sku="SKU-PROC-1",
            name="高效散熱模組",
            base_unit="PCS",
            cost_price=Decimal("1500.0"),
            selling_price=Decimal("2500.0"),
            safety_stock=20,
        )

        # Inward initial stock to WH-MAIN (50 units @ 1500)
        self.inventory_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-PROC-1",
            qty_delta=Decimal("50.0"),
            unit_cost=Decimal("1500.0"),
            reference_id="INIT-001",
            notes="期初庫存",
        )

        # Create FastAPI client
        self.app = create_app(db=self.db, event_bus=self.event_bus)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_procurement_page_renders_ok(self):
        """GET /procurement should return 200 and render form, products, and warehouse options."""
        response = self.client.get("/procurement?sku=SKU-PROC-1")
        self.assertEqual(response.status_code, 200)
        content = response.text
        self.assertIn("採購與進貨作業中心", content)
        self.assertIn("快速建立採購單", content)
        self.assertIn("SKU-PROC-1", content)
        self.assertIn("WH-MAIN", content)

    def test_create_purchase_order_flow(self):
        """POST /procurement/create should create a DRAFT PO and return updated list."""
        payload = {
            "supplier_name": "台塑塑膠工業",
            "target_warehouse": "WH-MAIN",
            "sku": ["SKU-PROC-1"],
            "qty": ["30"],
            "unit_cost": ["1200.0"],
        }
        response = self.client.post(
            "/procurement/create",
            data=payload,
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        content = response.text
        self.assertIn("成功建立採購單", content)
        self.assertIn("台塑塑膠工業", content)
        self.assertIn("草稿 (DRAFT)", content)
        self.assertIn("NT$ 36,000.00", content)

        # Verify in DB
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM purchase_orders WHERE supplier_name = '台塑塑膠工業'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["status"], "DRAFT")
            self.assertEqual(float(row["total_amount"]), 36000.0)

    def test_submit_purchase_order_flow(self):
        """POST /procurement/{po_id}/submit should advance PO to SUBMITTED."""
        po = self.procurement_service.create_purchase_order(
            supplier_name="聯發微電子",
            items=[("SKU-PROC-1", Decimal("10"), Decimal("1400.0"))],
        )

        response = self.client.post(f"/procurement/{po.po_id}/submit")
        self.assertEqual(response.status_code, 200)
        content = response.text
        self.assertIn("待到貨 (SUBMITTED)", content)
        self.assertIn("驗收入庫", content)

        # Verify in DB
        updated_po = self.procurement_service.get_purchase_order(po.po_id)
        self.assertEqual(updated_po.status.value, "SUBMITTED")

    def test_receive_modal_endpoint(self):
        """GET /procurement/{po_id}/receive-modal returns modal HTML."""
        po = self.procurement_service.create_purchase_order(
            supplier_name="友達光電",
            items=[("SKU-PROC-1", Decimal("5"), Decimal("1300.0"))],
        )
        self.procurement_service.submit_purchase_order(po.po_id)

        response = self.client.get(f"/procurement/{po.po_id}/receive-modal")
        self.assertEqual(response.status_code, 200)
        self.assertIn("物料驗收入庫 (Goods Receipt)", response.text)
        self.assertIn("WH-MAIN", response.text)

    def test_receive_goods_flow_with_cost_and_accounting_integration(self):
        """POST /procurement/{po_id}/receive should:
        1. Set status to RECEIVED
        2. Update stock ledger with +qty
        3. Recalculate moving average cost: (50*1500 + 30*1100)/(50+30) = 108000/80 = 1350
        4. Trigger ERP_GOODS_RECEIVED and create TanGii AP record & journal entry
        """
        po = self.procurement_service.create_purchase_order(
            supplier_name="國巨電子",
            items=[("SKU-PROC-1", Decimal("30"), Decimal("1100.0"))],
        )
        self.procurement_service.submit_purchase_order(po.po_id)

        response = self.client.post(
            f"/procurement/{po.po_id}/receive",
            data={"warehouse_id": "WH-MAIN"},
        )
        self.assertEqual(response.status_code, 200)
        content = response.text
        self.assertIn("已驗收入庫 (RECEIVED)", content)
        self.assertIn("已完成立帳", content)

        # 1. Check stock ledger & physical balance
        bal = self.inventory_service.get_stock_balance("WH-MAIN", "SKU-PROC-1")
        self.assertEqual(bal, Decimal("80.0"))  # 50 + 30

        # 2. Check moving average cost recalculation
        prod = self.inventory_service.get_product("SKU-PROC-1")
        self.assertIsNotNone(prod)
        # Expected: (50 * 1500 + 30 * 1100) / 80 = (75000 + 33000) / 80 = 108000 / 80 = 1350.0
        self.assertEqual(prod.cost_price, Decimal("1350.0"))

        # 3. Check TanGii Accounting integration (AP & Journal Entries)
        with self.db.transaction() as conn:
            ap_row = conn.execute(
                "SELECT * FROM accounts_payable WHERE po_id = ?",
                (po.po_id,),
            ).fetchone()
            self.assertIsNotNone(ap_row)
            self.assertEqual(float(ap_row["amount"]), 33000.0)
            self.assertEqual(ap_row["status"], "UNPAID")

            # Check journal entry created for goods received
            entry = conn.execute(
                "SELECT * FROM journal_entries WHERE source_event = 'ERP_GOODS_RECEIVED' AND reference_id = ?",
                (ap_row["grn_id"],),
            ).fetchone()
            self.assertIsNotNone(entry)

    def test_error_handling_translations(self):
        """Verify errors are translated into friendly Traditional Chinese."""
        # 1. Missing supplier
        resp = self.client.post(
            "/procurement/create",
            data={"supplier_name": "", "sku": ["SKU-PROC-1"], "qty": ["10"], "unit_cost": ["100"]},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("請輸入供應商名稱", resp.text)

        # 2. Non-existent SKU
        resp2 = self.client.post(
            "/procurement/create",
            data={"supplier_name": "測試廠商", "sku": ["SKU-NON-EXIST"], "qty": ["10"], "unit_cost": ["100"]},
        )
        self.assertEqual(resp2.status_code, 400)
        self.assertIn("商品品號 'SKU-NON-EXIST' 不存在", resp2.text)

        # 3. Invalid negative qty
        resp3 = self.client.post(
            "/procurement/create",
            data={"supplier_name": "測試廠商", "sku": ["SKU-PROC-1"], "qty": ["-5"], "unit_cost": ["100"]},
        )
        self.assertEqual(resp3.status_code, 400)
        self.assertIn("採購數量必須大於 0", resp3.text)

        # 4. Cannot receive DRAFT PO directly
        po = self.procurement_service.create_purchase_order(
            supplier_name="草稿廠商",
            items=[("SKU-PROC-1", Decimal("5"), Decimal("100"))],
        )
        resp4 = self.client.post(f"/procurement/{po.po_id}/receive", data={"warehouse_id": "WH-MAIN"})
        self.assertEqual(resp4.status_code, 400)
        self.assertIn("無法驗收入庫", resp4.text)

    def test_create_and_receive_po_multi_warehouse(self):
        """Verify PO created with WH-STORE defaults to WH-STORE in modal and receives into WH-STORE."""
        # 1. Create PO targeting WH-STORE
        payload = {
            "supplier_name": "新竹晶圓科技",
            "target_warehouse": "WH-STORE",
            "sku": ["SKU-PROC-1"],
            "qty": ["25"],
            "unit_cost": ["1250.0"],
        }
        resp = self.client.post("/procurement/create", data=payload, headers={"HX-Request": "true"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("進貨倉: WH-STORE", resp.text)

        # Find PO
        with self.db.transaction() as conn:
            row = conn.execute("SELECT po_id, warehouse_id FROM purchase_orders WHERE supplier_name = '新竹晶圓科技'").fetchone()
            self.assertEqual(row["warehouse_id"], "WH-STORE")
            po_id = row["po_id"]

        # Submit PO
        self.client.post(f"/procurement/{po_id}/submit")

        # 2. Check receive modal pre-selection
        modal_resp = self.client.get(f"/procurement/{po_id}/receive-modal")
        self.assertEqual(modal_resp.status_code, 200)
        # WH-STORE should be selected
        self.assertIn('value="WH-STORE" selected', modal_resp.text)

        # 3. Receive goods into WH-STORE
        recv_resp = self.client.post(f"/procurement/{po_id}/receive", data={"warehouse_id": "WH-STORE"})
        self.assertEqual(recv_resp.status_code, 200)

        # Verify stock balance in WH-STORE is 25
        bal = self.inventory_service.get_stock_balance("WH-STORE", "SKU-PROC-1")
        self.assertEqual(bal, Decimal("25.0"))



if __name__ == "__main__":
    unittest.main()
