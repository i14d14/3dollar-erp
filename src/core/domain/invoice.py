from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from src.shared.base_models import DomainModel

class InvoiceStatus(str, Enum):
    ISSUED = "ISSUED"
    VOID = "VOID"
    ALLOWANCE = "ALLOWANCE"

class TaxType(str, Enum):
    TAXABLE = "1"  # 應稅 5%
    ZERO_TAX = "2" # 零稅率
    TAX_FREE = "3" # 免稅

class ARStatus(str, Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"

class Invoice(DomainModel):
    invoice_id: str
    order_id: str
    invoice_number: str
    random_code: str
    tax_type: TaxType = TaxType.TAXABLE
    total_amount: Decimal
    tax_amount: Decimal
    buyer_tax_id: Optional[str] = None
    buyer_name: Optional[str] = None
    qrcode_l: Optional[str] = None
    qrcode_r: Optional[str] = None
    status: InvoiceStatus = InvoiceStatus.ISSUED

class AccountsReceivable(DomainModel):
    ar_id: str
    order_id: str
    invoice_id: str
    customer_id: str
    due_date: date
    amount: Decimal
    paid_amount: Decimal = Decimal("0.0")
    status: ARStatus = ARStatus.UNPAID
