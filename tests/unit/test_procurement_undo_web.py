from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.domain.procurement import POStatus
from src.core.services.inventory_service import InventoryService
from src.core.services.procurement_service import ProcurementService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestProcurementUndoWeb(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_procurement_web.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.inventory_service = InventoryService(db=self.db)
        self.procurement_service = ProcurementService(db=self.db, event_bus=self.event_bus)

        # Seed warehouse & product
        self.inventory_service.create_warehouse("WH-MAIN", "台北總倉")
        self.inventory_service.create_product(
            sku="SKU-COFFEE-01",
            name="精品濾掛咖啡",
            base_unit="BOX",
            cost_price=Decimal("150.0"),
            selling_price=Decimal("300.0"),
            safety_stock=20,
        )

        self.app = create_app(db=self.db, event_bus=self.event_bus)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_po_returns_toast_with_cancel_button_and_undo_cancels_po(self) -> None:
        resp = self.client.post(
            "/procurement/create",
            headers={"HX-Request": "true"},
            data={
                "supplier_name": "優質咖啡莊園",
                "sku": ["SKU-COFFEE-01"],
                "qty": ["25"],
                "unit_cost": ["140.00"],
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="toast-container"', resp.text)
        self.assertIn('hx-swap-oob="innerHTML:#toast-container"', resp.text)
        self.assertIn("成功建立採購單", resp.text)
        self.assertIn("撤回建立", resp.text)

        # Extract PO ID from response
        pos = [p for p in self.procurement_service.list_purchase_orders() if p.supplier_name == "優質咖啡莊園"]
        self.assertGreaterEqual(len(pos), 1)
        po = pos[0]
        self.assertEqual(po.status, POStatus.DRAFT)
        self.assertIn(f"/procurement/{po.po_id}/cancel", resp.text)

        # Click Undo (cancel PO)
        undo_resp = self.client.post(
            f"/procurement/{po.po_id}/cancel",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(undo_resp.status_code, 200)
        self.assertIn("已成功撤回採購單建立", undo_resp.text)

        # Verify PO is CANCELLED
        updated_po = self.procurement_service.get_purchase_order(po.po_id)
        self.assertEqual(updated_po.status, POStatus.CANCELLED)

    def test_submit_po_returns_toast_with_undo_and_reverts_to_draft(self) -> None:
        # Create draft PO
        po = self.procurement_service.create_purchase_order(
            supplier_name="優質咖啡莊園",
            items=[("SKU-COFFEE-01", Decimal("10"), Decimal("140.00"))],
        )
        self.assertEqual(po.status, POStatus.DRAFT)

        # Submit PO
        resp = self.client.post(
            f"/procurement/{po.po_id}/submit",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="toast-container"', resp.text)
        self.assertIn("已確認送出，等待供應商到貨", resp.text)
        self.assertIn("撤回下訂", resp.text)
        self.assertIn(f"/procurement/{po.po_id}/submit/undo", resp.text)

        # Verify DB is SUBMITTED
        self.assertEqual(self.procurement_service.get_purchase_order(po.po_id).status, POStatus.SUBMITTED)

        # Click Undo Submit
        undo_resp = self.client.post(
            f"/procurement/{po.po_id}/submit/undo",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(undo_resp.status_code, 200)
        self.assertIn("已成功撤回下訂，已恢復為草稿 (DRAFT)", undo_resp.text)

        # Verify DB is DRAFT
        self.assertEqual(self.procurement_service.get_purchase_order(po.po_id).status, POStatus.DRAFT)

    def test_receive_po_returns_toast_with_undo_and_reverts_goods_receipt(self) -> None:
        po = self.procurement_service.create_purchase_order(
            supplier_name="優質咖啡莊園",
            items=[("SKU-COFFEE-01", Decimal("10"), Decimal("140.00"))],
        )
        self.procurement_service.submit_purchase_order(po.po_id)

        # Test modal rendering
        modal_resp = self.client.get(f"/procurement/{po.po_id}/receive-modal")
        self.assertEqual(modal_resp.status_code, 200)
        self.assertIn("物料驗收入庫 (Goods Receipt)", modal_resp.text)

        # 1. Submit goods receipt
        recv_resp = self.client.post(
            f"/procurement/{po.po_id}/receive",
            headers={"HX-Request": "true"},
            data={"warehouse_id": "WH-MAIN"},
        )
        self.assertEqual(recv_resp.status_code, 200)
        self.assertIn('id="toast-container"', recv_resp.text)
        self.assertIn("已成功驗收入庫", recv_resp.text)
        self.assertIn("撤回入庫", recv_resp.text)
        self.assertIn(f"/procurement/{po.po_id}/receive/undo", recv_resp.text)

        # Verify PO is RECEIVED and stock increased
        self.assertEqual(self.procurement_service.get_purchase_order(po.po_id).status, POStatus.RECEIVED)
        self.assertEqual(self.inventory_service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01"), Decimal("10"))

        # Verify AP and Journal Entry exist
        with self.db.transaction() as conn:
            ap_row = conn.execute("SELECT ap_id, amount, status FROM accounts_payable WHERE po_id = ?", (po.po_id,)).fetchone()
            self.assertIsNotNone(ap_row)
            self.assertEqual(Decimal(str(ap_row["amount"])), Decimal("1400.00"))

            je_row = conn.execute("SELECT entry_id FROM journal_entries WHERE source_event = 'ERP_GOODS_RECEIVED'").fetchone()
            self.assertIsNotNone(je_row)

        # 2. Click Undo (revert goods receipt)
        undo_resp = self.client.post(
            f"/procurement/{po.po_id}/receive/undo",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(undo_resp.status_code, 200)
        self.assertIn('id="toast-container"', undo_resp.text)
        self.assertIn("已成功撤回驗收入庫", undo_resp.text)

        # Verify PO is restored to SUBMITTED
        updated_po = self.procurement_service.get_purchase_order(po.po_id)
        self.assertEqual(updated_po.status, POStatus.SUBMITTED)

        # Verify physical stock is deducted back to 0
        self.assertEqual(self.inventory_service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01"), Decimal("0"))

        # Verify AP record is deleted/cleaned
        with self.db.transaction() as conn:
            ap_check = conn.execute("SELECT ap_id FROM accounts_payable WHERE po_id = ?", (po.po_id,)).fetchone()
            self.assertIsNone(ap_check)

            # Verify REVERSAL journal entry was created
            reversal_je = conn.execute("SELECT entry_id FROM journal_entries WHERE source_event = 'REVERSAL'").fetchone()
            self.assertIsNotNone(reversal_je)

    def test_revert_goods_receipt_fails_if_stock_insufficient(self) -> None:
        po = self.procurement_service.create_purchase_order(
            supplier_name="優質咖啡莊園",
            items=[("SKU-COFFEE-01", Decimal("10"), Decimal("140.00"))],
        )
        self.procurement_service.submit_purchase_order(po.po_id)

        # Receive PO
        self.client.post(
            f"/procurement/{po.po_id}/receive",
            headers={"HX-Request": "true"},
            data={"warehouse_id": "WH-MAIN"},
        )
        self.assertEqual(self.inventory_service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01"), Decimal("10"))

        # Artificially deduct stock (e.g. outbound shipment of 8 units, leaving only 2)
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO stock_ledger (ledger_id, warehouse_id, sku, qty_delta, balance_after, unit_cost, reference_type, reference_id, notes)
                VALUES ('TEST-LEDGER-01', 'WH-MAIN', 'SKU-COFFEE-01', -8.0, 2.0, 140.0, 'DELIVERY', 'DO-TEST', 'Simulate delivery')
                """
            )
        self.assertEqual(self.inventory_service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01"), Decimal("2"))

        # Attempt to undo receipt (needs 10 units to revert, but only 2 available)
        fail_resp = self.client.post(
            f"/procurement/{po.po_id}/receive/undo",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(fail_resp.status_code, 400)
        self.assertIn("現有庫存", fail_resp.text)
        self.assertIn("小於入庫量", fail_resp.text)

