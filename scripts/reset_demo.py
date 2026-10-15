from __future__ import annotations
import os
import sys
from decimal import Decimal
from pathlib import Path

# Ensure UTF-8 output encoding for Windows PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.shared.database import Database
from src.shared.event_bus import EventBus
from src.core.services.inventory_service import InventoryService
from src.extended_core.crm.services.crm_service import CrmService
from src.channel_ui.web.demo_seed import seed_demo_data


def reset_demo_case():
    print("=" * 60)
    print("🔄 重置 3Dollar ERP 展示資料庫 (Pristine Demo State)")
    print("=" * 60)

    db_file = PROJECT_ROOT / "erp.db"
    if db_file.exists():
        try:
            db_file.unlink()
            print("  ✓ 移除既有資料庫檔案 erp.db")
        except Exception as e:
            print(f"  ⚠️ 無法刪除資料庫檔案 ({e})，改用清空資料表方式...")

    db = Database()
    event_bus = EventBus()
    db.init_db()

    # 1. 執行標準展示種子資料注入
    print("  ✓ 注入基礎多倉、商品與跨模組示範資料...")
    seed_demo_data(db, event_bus)

    # 2. 確保台北總倉存量充足
    inv_service = InventoryService(db=db)
    inv_service.adjust_stock("WH-MAIN", "SKU-PRO-01", Decimal("50.0"), Decimal("1500.0"), "DEMO-STOCK", "手動展示預留庫存")
    inv_service.adjust_stock("WH-MAIN", "SKU-ACC-02", Decimal("50.0"), Decimal("300.0"), "DEMO-STOCK", "手動展示預留庫存")

    # 3. 建立手動展示專屬 PROPOSAL 商機與報價單
    crm_service = CrmService(db=db, event_bus=event_bus)
    
    # 尋找或建立目標客戶
    contacts = crm_service.list_contacts()
    demo_contact = next((c for c in contacts if "美德" in c.company_name), None)
    if not demo_contact:
        demo_contact = crm_service.create_contact(
            company_name="美德醫療器材股份有限公司",
            contact_name="陳建宏 協理",
            tax_id="84561234",
            email="service@med-demo.com.tw",
            phone="02-27891234",
        )

    deal = crm_service.create_deal(
        contact_id=demo_contact.contact_id,
        title="美德醫療 2026 旗艦智慧終端採購案",
        expected_amount=Decimal("50000.0"),
    )
    quote = crm_service.create_quote(
        deal_id=deal.deal_id,
        items=[
            ("SKU-PRO-01", Decimal("2.0"), Decimal("25000.0")),
        ],
        valid_days=30,
    )

    print(f"  ✓ 手動操作目標商機已建立: {deal.deal_id}")
    print(f"    - 客戶：{demo_contact.company_name} ({demo_contact.contact_name})")
    print(f"    - 商機：{deal.title}")
    print(f"    - 階段：PROPOSAL (提案報價，等待點選『⚡ 贏單轉 ERP』)")
    print(f"    - 報價單：{quote.quote_number} (含稅 NT$ {quote.total_amount:,.0f})")
    print("=" * 60)
    print("✨ 資料庫重置完成！隨時可開伺服器進行手動操作。")
    print("=" * 60)


if __name__ == "__main__":
    reset_demo_case()
