from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from src.shared.base_models import DomainModel


class WaybillRequest(DomainModel):
    order_id: str
    recipient_name: str
    recipient_phone: str
    shipping_address: str
    package_count: int = 1
    notes: Optional[str] = None


class WaybillResult(DomainModel):
    waybill_id: str
    tracking_number: str
    carrier_name: str
    barcode_payload: str
    qrcode_payload: str
    dispatched_at: datetime


class ShippingCarrierPort(ABC):
    """Abstract port for logistics carriers and shipping waybills."""

    @abstractmethod
    def dispatch_waybill(self, request: WaybillRequest) -> WaybillResult:
        """Dispatch a shipping waybill, issuing a tracking number, barcode, and QR code."""
        pass
