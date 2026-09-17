from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from pydantic import model_validator
from src.shared.base_models import DomainModel

class AccountType(str, Enum):
    ASSET = "ASSET"          # 資產 (1)
    LIABILITY = "LIABILITY"  # 負債 (2)
    EQUITY = "EQUITY"        # 權益 (3)
    REVENUE = "REVENUE"      # 收入 (4)
    EXPENSE = "EXPENSE"      # 費用與成本 (5)

class Account(DomainModel):
    account_code: str
    account_name: str
    account_type: AccountType
    is_active: bool = True

class JournalLine(DomainModel):
    line_id: str
    entry_id: str
    account_code: str
    debit: Decimal = Decimal("0.0")
    credit: Decimal = Decimal("0.0")

class JournalEntry(DomainModel):
    entry_id: str
    entry_date: date
    source_event: str
    reference_id: str
    description: str
    lines: List[JournalLine] = []

    @model_validator(mode="after")
    def validate_debit_credit_balance(self) -> JournalEntry:
        if not self.lines:
            return self
        total_debit = sum((line.debit for line in self.lines), Decimal("0.0"))
        total_credit = sum((line.credit for line in self.lines), Decimal("0.0"))
        if abs(total_debit - total_credit) > Decimal("0.001"):
            raise ValueError(
                f"傳票借貸不平衡！借方總額 ({total_debit}) 不等於貸方總額 ({total_credit}) (Double-entry bookkeeping imbalance)"
            )
        return self

class APStatus(str, Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"

class AccountsPayable(DomainModel):
    ap_id: str
    po_id: str
    grn_id: Optional[str] = None
    supplier_name: str
    due_date: date
    amount: Decimal
    paid_amount: Decimal = Decimal("0.0")
    status: APStatus = APStatus.UNPAID
    created_at: Optional[str] = None

class AgingBucket(str, Enum):
    CURRENT = "CURRENT"          # 未到期 (0 days overdue)
    DAYS_1_30 = "DAYS_1_30"      # 逾期 1 - 30 天
    DAYS_31_60 = "DAYS_31_60"    # 逾期 31 - 60 天
    DAYS_60_PLUS = "DAYS_60_PLUS"# 逾期 60 天以上

class AgingItem(DomainModel):
    item_id: str                 # ar_id or ap_id
    reference_id: str            # order_id / inv_id or po_id / grn_id
    partner_name: str            # Customer name or supplier name
    amount: Decimal              # Total amount
    paid_amount: Decimal         # Paid amount
    outstanding_amount: Decimal  # Remaining unpaid
    due_date: date
    days_overdue: int
    bucket: AgingBucket
    status: str

class AgingReport(DomainModel):
    report_type: str             # "RECEIVABLE" or "PAYABLE"
    as_of_date: date
    total_outstanding: Decimal
    current_amount: Decimal
    days_1_30_amount: Decimal
    days_31_60_amount: Decimal
    days_60_plus_amount: Decimal
    items: List[AgingItem] = []

class TrialBalanceItem(DomainModel):
    account_code: str
    account_name: str
    account_type: AccountType
    debit_total: Decimal = Decimal("0.0")
    credit_total: Decimal = Decimal("0.0")
    balance_debit: Decimal = Decimal("0.0")
    balance_credit: Decimal = Decimal("0.0")

class TrialBalance(DomainModel):
    as_of_date: date
    items: List[TrialBalanceItem] = []
    total_debit: Decimal = Decimal("0.0")
    total_credit: Decimal = Decimal("0.0")
    is_balanced: bool = True

class IncomeStatement(DomainModel):
    start_date: Optional[date] = None
    end_date: date
    revenue: Decimal = Decimal("0.0")
    cogs: Decimal = Decimal("0.0")
    gross_profit: Decimal = Decimal("0.0")
    operating_expenses: Decimal = Decimal("0.0")
    net_profit: Decimal = Decimal("0.0")
