from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from starlette.requests import Request
from starlette.testclient import TestClient
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.app import create_app
from src.channel_ui.web.toast_helper import render_toast_oob
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestToastInfrastructure(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_toast.db"
        self.db = Database(self.db_path)
        self.db.init_db()
        self.event_bus = EventBus()
        self.app = create_app(db=self.db, event_bus=self.event_bus)
        self.client = TestClient(self.app)
        template_dir = Path(__file__).resolve().parents[2] / "src" / "channel_ui" / "web" / "templates"
        self.templates = Jinja2Templates(directory=str(template_dir))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_toast_partial_rendering_success_with_undo(self) -> None:
        scope = {"type": "http", "method": "GET", "path": "/"}
        request = Request(scope)

        html = render_toast_oob(
            templates=self.templates,
            request=request,
            message="多倉調撥成功！已調撥 10 件至門市倉",
            type="success",
            undo_url="/inventory/transfer/undo",
            undo_label="撤回調撥",
            undo_target="#stock-table-container",
            undo_swap="outerHTML",
            undo_vals={"ref_id": "TRF-TEST-001"},
            ttl_seconds=6,
        )

        # Verify HTMX OOB wrapper
        self.assertIn('id="toast-container"', html)
        self.assertIn('hx-swap-oob="innerHTML:#toast-container"', html)

        # Verify card classes and attributes
        self.assertIn('class="toast-card', html)
        self.assertIn('bg-emerald-50', html)
        self.assertIn('data-ttl="6000"', html)
        self.assertIn('style="--toast-ttl: 6s;"', html)
        self.assertIn("✅", html)
        self.assertIn("多倉調撥成功！已調撥 10 件至門市倉", html)

        # Verify undo button
        self.assertIn('hx-post="/inventory/transfer/undo"', html)
        self.assertIn('hx-target="#stock-table-container"', html)
        self.assertIn('hx-swap="outerHTML"', html)
        self.assertIn('hx-vals=\'{"ref_id": "TRF-TEST-001"}\'', html)
        self.assertIn("撤回調撥", html)

        # Verify dismiss button
        self.assertIn("data-toast-dismiss", html)

    def test_toast_partial_rendering_error_without_undo(self) -> None:
        scope = {"type": "http", "method": "GET", "path": "/"}
        request = Request(scope)

        html = render_toast_oob(
            templates=self.templates,
            request=request,
            message="可用庫存不足，無法執行調撥",
            type="error",
            ttl_seconds=8,
        )

        self.assertIn('bg-rose-50', html)
        self.assertIn('data-ttl="8000"', html)
        self.assertIn("🚨", html)
        self.assertIn("可用庫存不足，無法執行調撥", html)
        self.assertNotIn("hx-post=", html)
        self.assertNotIn("撤回", html)
        self.assertIn("data-toast-dismiss", html)

    def test_toast_partial_rendering_info(self) -> None:
        scope = {"type": "http", "method": "GET", "path": "/"}
        request = Request(scope)

        html = render_toast_oob(
            templates=self.templates,
            request=request,
            message="系統維護通知",
            type="info",
            ttl_seconds=5,
        )

        self.assertIn('bg-indigo-50', html)
        self.assertIn('data-ttl="5000"', html)
        self.assertIn("ℹ️", html)
        self.assertIn("系統維護通知", html)

    def test_htmx_exception_handler_returns_oob_toast(self) -> None:
        # Trigger an invalid transfer to induce a 400 error via HTMX
        resp = self.client.post(
            "/inventory/transfer",
            data={
                "from_warehouse_id": "NON_EXISTENT",
                "to_warehouse_id": "WH_STORE",
                "sku": "UNKNOWN",
                "qty": "10",
            },
            headers={"HX-Request": "true"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.headers.get("HX-Reswap"), "none")
        self.assertIn('id="toast-container"', resp.text)
        self.assertIn('hx-swap-oob="innerHTML:#toast-container"', resp.text)
        self.assertIn("toast-card", resp.text)
        self.assertIn("bg-rose-50", resp.text)
        self.assertIn("data-toast-dismiss", resp.text)
        self.assertIn("data-ttl=", resp.text)
