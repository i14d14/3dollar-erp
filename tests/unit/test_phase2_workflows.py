from __future__ import annotations
import json
from decimal import Decimal
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.core.services.procurement_service import ProcurementService
from src.extended_core.crm.models import DealStage
from src.extended_core.crm.services.crm_service import CrmService
from src.shared.database import Database
from src.shared.event_bus import EventBus


@pytest.fixture
def test_db_and_app(tmp_path: Path):
    db_file = tmp_path / "test_phase2.db"
    db = Database(db_file)
    db.init_db()
    event_bus = EventBus()

    inv = InventoryService(db=db)
    inv.create_warehouse("WH-MAIN", "台北總部主倉")
    inv.create_warehouse("WH-STORE", "信義實體門市倉")
    inv.create_product(
        sku="SKU-PRO-01",
        name="旗艦智慧終端機",
        base_unit="PCS",
        cost_price=Decimal("1500.0"),
        selling_price=Decimal("2500.0"),
        safety_stock=10,
    )
    inv.create_product(
        sku="SKU-ACC-02",
        name="極速充電套件組",
        base_unit="SET",
        cost_price=Decimal("300.0"),
        selling_price=Decimal("650.0"),
        safety_stock=5,
    )
    # Seed a past purchase order to establish historical supplier quote
    proc = ProcurementService(db=db, event_bus=event_bus)
    proc.create_purchase_order(
        supplier_name="祥茂電子工業",
        items=[("SKU-PRO-01", Decimal("10"), Decimal("1400.0"))],
    )
    proc.create_purchase_order(
        supplier_name="宏碁零組件供應商",
        items=[("SKU-ACC-02", Decimal("10"), Decimal("280.0"))],
    )

    app = create_app(db=db, event_bus=event_bus)
    client = TestClient(app)
    return db, client, proc, inv


def test_procurement_prefill_and_bom_split(test_db_and_app):
    db, client, proc, inv = test_db_and_app

    # 1. Test /procurement pre-fill parameters
    resp = client.get("/procurement?sku=SKU-PRO-01&warehouse_id=WH-STORE&qty=15&supplier_name=祥茂電子工業")
    assert resp.status_code == 200
    html = resp.text
    assert 'value="祥茂電子工業"' in html
    assert 'value="15"' in html
    assert 'value="1500.00"' in html
    assert 'selected' in html

    # 2. Test /procurement/bom/sample
    sample_resp = client.get("/procurement/bom/sample")
    assert sample_resp.status_code == 200
    assert len(sample_resp.content) > 1000

    # 3. Test /procurement/bom/create-pos (one-click split PO creation grouped by supplier)
    items_to_split = [
        {"sku": "SKU-PRO-01", "qty": 5, "unit_cost": 1400.0, "supplier_name": "祥茂電子工業"},
        {"sku": "SKU-ACC-02", "qty": 10, "unit_cost": 280.0, "supplier_name": "宏碁零組件供應商"},
    ]
    post_resp = client.post(
        "/procurement/bom/create-pos",
        data={"items_json": json.dumps(items_to_split)},
    )
    assert post_resp.status_code == 200
    assert "成功為 2 家供應商自動分割建立採購單" in post_resp.text

    # Verify 2 distinct POs exist in database for the two suppliers
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT po_id, supplier_name, total_amount FROM purchase_orders ORDER BY rowid DESC LIMIT 2"
        ).fetchall()
        suppliers = {r["supplier_name"] for r in rows}
        assert "祥茂電子工業" in suppliers
        assert "宏碁零組件供應商" in suppliers


def test_dashboard_low_stock_prefill_link(test_db_and_app):
    db, client, proc, inv = test_db_and_app

    # Stock is currently 0 for both products (which is < safety_stock 10 and 5)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "採購補貨" in resp.text
    assert "/procurement?sku=SKU-PRO-01" in resp.text
    assert "warehouse_id=" in resp.text
    assert "qty=" in resp.text
    assert "supplier_name=" in resp.text


def test_inventory_warehouse_names_and_low_stock_button(test_db_and_app):
    db, client, proc, inv = test_db_and_app

    resp = client.get("/inventory")
    assert resp.status_code == 200
    # Check that warehouse names appear in options
    assert "台北總部主倉 (WH-MAIN)" in resp.text
    assert "信義實體門市倉 (WH-STORE)" in resp.text
    # Check that low stock row has low stock warning link
    assert "低於安全量" in resp.text


def test_accounting_reports_and_mathjax(test_db_and_app):
    db, client, proc, inv = test_db_and_app

    # 1. Trial balance tab contains MathJax script and EAS equation
    resp = client.get("/accounting?tab=trial_balance")
    assert resp.status_code == 200
    assert "MathJax" in resp.text
    assert r"$\sum Dr = \sum Cr$" in resp.text

    # 2. Reports tab
    reports_resp = client.get("/accounting?tab=reports")
    assert reports_resp.status_code == 200
    assert "全方位財務與營運整合報表中心" in reports_resp.text

    # 3. 4-in-1 Executive report streaming download
    dl_resp = client.get("/accounting/reports/executive-financial")
    assert dl_resp.status_code == 200
    assert len(dl_resp.content) > 1000
    assert "spreadsheetml.sheet" in dl_resp.headers.get("content-type", "")


def test_crm_multi_item_deal_and_quotation(test_db_and_app):
    db, client, proc, inv = test_db_and_app

    # Create contact
    crm = CrmService(db=db, order_service=OrderService(db=db, event_bus=EventBus(), inventory_service=inv), event_bus=EventBus())
    contact = crm.create_contact(company_name="大同資訊實業系統部", contact_name="林副總", tax_id="99887766")

    # Create deal via web endpoint with multi-item form
    resp = client.post(
        "/crm/deals",
        data={
            "contact_id": contact.contact_id,
            "title": "智慧門市擴充案",
            "stage": "LEAD",
            "sku_1": "SKU-PRO-01",
            "qty_1": "4",
            "price_1": "2500",
            "sku_2": "SKU-ACC-02",
            "qty_2": "2",
            "price_2": "650",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    # Expected total: 4 * 2500 + 2 * 650 = 10000 + 1300 = 11,300
    assert "11,300" in resp.text
    assert "智慧門市擴充案" in resp.text
