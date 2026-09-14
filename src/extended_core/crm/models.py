from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from src.shared.base_models import DomainModel

class DealStage(str, Enum):
    LEAD = "LEAD"
    DISCOVERY = "DISCOVERY"
    PROPOSAL = "PROPOSAL"
    WON = "WON"
    LOST = "LOST"

class QuoteStatus(str, Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"

class Contact(DomainModel):
    contact_id: str
    company_name: str
    tax_id: Optional[str] = None
    contact_name: str
    email: Optional[str] = None
    phone: Optional[str] = None

class Deal(DomainModel):
    deal_id: str
    contact_id: str
    title: str
    stage: DealStage = DealStage.LEAD
    expected_amount: Decimal = Decimal("0.0")
    converted_order_id: Optional[str] = None

class Quote(DomainModel):
    quote_id: str
    deal_id: str
    quote_number: str
    total_amount: Decimal = Decimal("0.0")
    valid_until: date
    docx_path: Optional[str] = None
    pdf_path: Optional[str] = None
    status: QuoteStatus = QuoteStatus.DRAFT
