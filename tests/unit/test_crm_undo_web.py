from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.extended_core.crm.models import DealStage
from src.extended_core.crm.services.crm_service import CrmService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestCrmUndoWeb(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_crm_web.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.inventory_service = InventoryService(db=self.db)
        self.order_service = OrderService(db=self.db, event_bus=self.event_bus)
        self.crm_service = CrmService(db=self.db, order_service=self.order_service, event_bus=self.event_bus)

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
        self.inventory_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-COFFEE-01",
            qty_delta=Decimal("100.0"),
            unit_cost=Decimal("150.0"),
            reference_id="INIT-COFFEE",
        )

        # Create contact
        self.contact = self.crm_service.create_contact(
            company_name="宏碁創新科技股份有限公司",
            contact_name="陳經理",
            tax_id="12345678",
            phone="0911-222-333",
        )

        self.app = create_app(db=self.db, event_bus=self.event_bus)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_deal_returns_toast_with_undo_and_deletes_deal(self) -> None:
        resp = self.client.post(
            "/crm/deals",
            headers={"HX-Request": "true"},
            data={
                "contact_id": self.contact.contact_id,
                "title": "2026 年度員工咖啡採購案",
                "stage": "LEAD",
                "sku_1": "SKU-COFFEE-01",
                "qty_1": "50",
                "price_1": "280.00",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="toast-container"', resp.text)
        self.assertIn("成功建立商機", resp.text)
        self.assertIn("撤回建立", resp.text)

        # Check deal exists in DB
        deals = self.crm_service.list_deals()
        self.assertEqual(len(deals), 1)
        deal = deals[0]
        self.assertEqual(deal.title, "2026 年度員工咖啡採購案")
        self.assertIn(f"/crm/deals/{deal.deal_id}/undo", resp.text)

        # Click Undo (delete draft deal)
        undo_resp = self.client.post(
            f"/crm/deals/{deal.deal_id}/undo",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(undo_resp.status_code, 200)
        self.assertIn("已成功撤回商機建立", undo_resp.text)

        # Verify DB: deal deleted
        self.assertIsNone(self.crm_service.get_deal(deal.deal_id))
        self.assertEqual(len(self.crm_service.list_deals()), 0)

    def test_convert_deal_modal_and_confirm_returns_toast_with_no_undo(self) -> None:
        deal = self.crm_service.create_deal(
            contact_id=self.contact.contact_id,
            title="Q3 禮盒大宗採購案",
            stage=DealStage.PROPOSAL,
            items=[("SKU-COFFEE-01", Decimal("30"), Decimal("290.00"))],
        )
        self.crm_service.create_quote(
            deal_id=deal.deal_id,
            items=[("SKU-COFFEE-01", Decimal("30"), Decimal("290.00"))],
        )

        # Open Convert Modal
        modal_resp = self.client.get(f"/crm/deals/{deal.deal_id}/convert-modal")
        self.assertEqual(modal_resp.status_code, 200)
        self.assertIn("贏單轉 ERP 銷售訂單確認", modal_resp.text)
        self.assertIn("宏碁創新科技股份有限公司", modal_resp.text)

        # Submit Conversion
        conv_resp = self.client.post(
            f"/crm/deals/{deal.deal_id}/convert-to-order",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(conv_resp.status_code, 200)
        self.assertIn('id="toast-container"', conv_resp.text)
        self.assertIn("商機已成功拋轉為 ERP 銷售訂單", conv_resp.text)
        self.assertNotIn('<span>撤回</span>', conv_resp.text)

        # Verify DB: deal is WON and converted_order_id is populated
        updated_deal = self.crm_service.get_deal(deal.deal_id)
        self.assertEqual(updated_deal.stage, DealStage.WON)
        self.assertIsNotNone(updated_deal.converted_order_id)
        so = self.order_service.get_order(updated_deal.converted_order_id)
        self.assertEqual(so.total_amount, Decimal("8700.00"))

    def test_advance_deal_stage_returns_toast_with_undo_and_reverts_stage(self) -> None:
        deal = self.crm_service.create_deal(
            contact_id=self.contact.contact_id,
            title="企業資安健檢專案",
            stage=DealStage.LEAD,
            expected_amount=Decimal("120000.0"),
        )
        self.assertEqual(deal.stage, DealStage.LEAD)

        # Advance stage: LEAD -> DISCOVERY
        resp = self.client.post(
            f"/crm/deals/{deal.deal_id}/stage",
            headers={"HX-Request": "true"},
            data={"stage": "DISCOVERY"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="toast-container"', resp.text)
        self.assertIn("已變更階段為 DISCOVERY", resp.text)
        self.assertIn("撤回階段", resp.text)
        self.assertIn(f"/crm/deals/{deal.deal_id}/stage/undo", resp.text)

        # Verify DB is DISCOVERY
        self.assertEqual(self.crm_service.get_deal(deal.deal_id).stage, DealStage.DISCOVERY)

        # Click Undo
        undo_resp = self.client.post(
            f"/crm/deals/{deal.deal_id}/stage/undo",
            headers={"HX-Request": "true"},
            data={"prev_stage": "LEAD"},
        )
        self.assertEqual(undo_resp.status_code, 200)
        self.assertIn('id="toast-container"', undo_resp.text)
        self.assertIn("已回復為 LEAD", undo_resp.text)

        # Verify DB reverted to LEAD
        self.assertEqual(self.crm_service.get_deal(deal.deal_id).stage, DealStage.LEAD)

    def test_create_quote_returns_toast_with_undo_and_deletes_quote(self) -> None:
        deal = self.crm_service.create_deal(
            contact_id=self.contact.contact_id,
            title="咖啡豆長期供應合約",
            stage=DealStage.DISCOVERY,
            items=[("SKU-COFFEE-01", Decimal("20"), Decimal("260.00"))],
        )

        # Create Quote
        resp = self.client.post(
            f"/crm/deals/{deal.deal_id}/quotes",
            headers={"HX-Request": "true"},
            data={
                "sku_1": "SKU-COFFEE-01",
                "qty_1": "20",
                "price_1": "260.00",
                "valid_days": "30",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="toast-container"', resp.text)
        self.assertIn("成功建立報價單", resp.text)
        self.assertIn("撤回報價單", resp.text)

        quotes = self.crm_service.get_quotes_for_deal(deal.deal_id)
        self.assertEqual(len(quotes), 1)
        quote = quotes[0]
        self.assertIn(f"/crm/quotes/{quote.quote_id}/undo", resp.text)

        # Verify deal advanced to PROPOSAL
        self.assertEqual(self.crm_service.get_deal(deal.deal_id).stage, DealStage.PROPOSAL)

        # Click Undo Quote
        undo_resp = self.client.post(
            f"/crm/quotes/{quote.quote_id}/undo",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(undo_resp.status_code, 200)
        self.assertIn('id="toast-container"', undo_resp.text)
        self.assertIn("已成功撤回報價單", undo_resp.text)

        # Verify quote is deleted and deal reverted to DISCOVERY
        self.assertEqual(len(self.crm_service.get_quotes_for_deal(deal.deal_id)), 0)
        reverted_deal = self.crm_service.get_deal(deal.deal_id)
        self.assertEqual(reverted_deal.stage, DealStage.DISCOVERY)

    def test_contacts_toast_oob(self) -> None:
        # Create Contact via HTMX
        resp = self.client.post(
            "/crm/contacts",
            headers={"HX-Request": "true"},
            data={
                "company_name": "新聯陽數位行銷",
                "contact_name": "林總監",
                "tax_id": "88776655",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="toast-container"', resp.text)
        self.assertIn("成功建立客戶：新聯陽數位行銷", resp.text)

        # Fetch contact ID
        with self.db.transaction() as conn:
            row = conn.execute("SELECT contact_id FROM crm_contacts WHERE company_name = '新聯陽數位行銷'").fetchone()
            cid = row["contact_id"]

        # Update Contact via HTMX
        up_resp = self.client.post(
            f"/crm/contacts/{cid}",
            headers={"HX-Request": "true"},
            data={
                "contact_name": "林總經理",
                "phone": "0988-123-456",
            },
        )
        self.assertEqual(up_resp.status_code, 200)
        self.assertIn('id="toast-container"', up_resp.text)
        self.assertIn("成功更新客戶資料：新聯陽數位行銷", up_resp.text)

