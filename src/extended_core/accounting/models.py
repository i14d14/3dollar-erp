from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import List
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
        if total_debit != total_credit:
            raise ValueError(
                f"Double-entry bookkeeping imbalance! Total Debit={total_debit} does not equal Total Credit={total_credit}"
            )
        return self
