from __future__ import annotations
import datetime
import random
import uuid
from src.core.ports.shipping_carrier_port import (
    ShippingCarrierPort,
    WaybillRequest,
    WaybillResult,
)


class InternalShippingCarrierProvider(ShippingCarrierPort):
    """Internal standalone carrier provider generating custom tracking numbers, barcodes, and QR codes.

    Can be swapped seamlessly with third-party carrier providers (e.g. ECPay Logistics, TCat, SF Express).
    """

    def __init__(self, carrier_name: str = "3Dollar Express (三圓標準物流)") -> None:
        self.carrier_name = carrier_name

    def _generate_tracking_number(self) -> str:
        today_str = datetime.date.today().strftime("%Y%m%d")
        rand_suffix = f"{random.randint(100000, 999999)}"
        return f"TRK-{today_str}-{rand_suffix}"

    def dispatch_waybill(self, request: WaybillRequest) -> WaybillResult:
        waybill_id = f"WB-{uuid.uuid4().hex[:8].upper()}"
        tracking_num = self._generate_tracking_number()
        dispatched_at = datetime.datetime.now()

        # Generate barcode payload (Code128 format) & QR code payload
        barcode_payload = tracking_num
        qrcode_payload = (
            f"CARRIER:{self.carrier_name}|WAYBILL:{waybill_id}|TRACK:{tracking_num}|"
            f"ORDER:{request.order_id}|RECIPIENT:{request.recipient_name}|"
            f"TIME:{dispatched_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        return WaybillResult(
            waybill_id=waybill_id,
            tracking_number=tracking_num,
            carrier_name=self.carrier_name,
            barcode_payload=barcode_payload,
            qrcode_payload=qrcode_payload,
            dispatched_at=dispatched_at,
        )
