from __future__ import annotations
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List
from src.core.domain.order import DeliveryOrder, SalesOrder
from src.shared.base_models import DomainModel

class ShippingLabelData(DomainModel):
    do_id: str
    order_id: str
    recipient_name: str
    recipient_phone: str
    shipping_address: str
    tracking_number: str

class PrinterPort(ABC):
    @abstractmethod
    def generate_shipping_label_pdf(self, label_data: ShippingLabelData, page_format: str = "100x150") -> bytes:
        """Generate a standardized logistics shipping label PDF (100x150mm or single A4)."""
        pass

    @abstractmethod
    def generate_a4_shipping_labels_pdf(
        self,
        labels: List[ShippingLabelData],
        layout: str = "2x2",
        start_position: int = 1,
    ) -> bytes:
        """Generate multi-label sticker sheets on standard A4 paper (2x2 4-up)."""
        pass

    @abstractmethod
    def generate_barcode_label_pdf(self, sku: str, product_name: str, barcode_type: str = "Code128") -> bytes:
        """Generate product barcode sticker PDF."""
        pass
