from __future__ import annotations
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional
from src.core.domain.invoice import Invoice, TaxType
from src.shared.base_models import DomainModel

class IssueInvoiceRequest(DomainModel):
    order_id: str
    total_amount: Decimal
    tax_type: TaxType = TaxType.TAXABLE
    buyer_tax_id: Optional[str] = None
    buyer_name: Optional[str] = None

class InvoicePort(ABC):
    @abstractmethod
    def issue_invoice(self, request: IssueInvoiceRequest) -> Invoice:
        """Issue an electronic invoice conforming to Taiwan MIG 3.2.1 format."""
        pass

    @abstractmethod
    def render_invoice_pdf(self, invoice: Invoice) -> bytes:
        """Render a standardized 5.7cm wide electronic invoice receipt PDF."""
        pass
