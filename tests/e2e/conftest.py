from __future__ import annotations
import pytest
from playwright.sync_api import BrowserContext, Browser, Page

# ---------------------------------------------------------------------------
# Global Playwright Fail-Fast Timeout Injection (Anti-Hang Invariant)
# Enforces a strict 2000ms upper bound on all page operations across pytest,
# preventing idle 30-second hang on missing elements or mismatched events.
# ---------------------------------------------------------------------------

_orig_context_new_page = BrowserContext.new_page
_orig_browser_new_page = Browser.new_page


def _patched_context_new_page(self, *args, **kwargs) -> Page:
    page = _orig_context_new_page(self, *args, **kwargs)
    page.set_default_timeout(2000)
    page.set_default_navigation_timeout(5000)
    return page


def _patched_browser_new_page(self, *args, **kwargs) -> Page:
    page = _orig_browser_new_page(self, *args, **kwargs)
    page.set_default_timeout(2000)
    page.set_default_navigation_timeout(5000)
    return page


BrowserContext.new_page = _patched_context_new_page
Browser.new_page = _patched_browser_new_page


@pytest.fixture(autouse=True)
def configure_playwright_timeouts(request):
    """Automatically enforce 2000ms fail-fast timeout on any pytest-playwright page fixture."""
    if "page" in request.fixturenames:
        page: Page = request.getfixturevalue("page")
        page.set_default_timeout(2000)
        page.set_default_navigation_timeout(5000)
