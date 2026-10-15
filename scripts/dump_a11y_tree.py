#!/usr/bin/env python3
"""Accessibility & ARIA Tree Quick Explorer for Playwright.

Extracts the W3C A11y / ARIA Tree from a target URL or local HTML file in <1 second.
Leverages modern Playwright's aria_snapshot() and data-testid scanning to provide
a noise-free, semantic inventory of all actionable UI elements and recommended locators.

Usage:
    python scripts/dump_a11y_tree.py --url http://127.0.0.1:8000/orders
    python scripts/dump_a11y_tree.py --file path/to/page.html
    python scripts/dump_a11y_tree.py --url http://127.0.0.1:8000/ --output snapshot.txt
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure UTF-8 stdout on Windows PowerShell
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def dump_a11y_tree(target_url: str, output_path: str | None = None, timeout_ms: int = 5000):
    """Launch headless Playwright, snapshot ARIA tree and testids, and output result."""
    from playwright.sync_api import sync_playwright

    print(f"[*] Probing Accessibility & ARIA Snapshot for: {target_url}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        page.set_default_navigation_timeout(timeout_ms)

        try:
            page.goto(target_url, wait_until="domcontentloaded")

            # 1. Capture modern Playwright ARIA snapshot
            aria_tree = ""
            try:
                aria_tree = page.locator(":root").aria_snapshot()
            except Exception:
                try:
                    aria_tree = page.locator("body").aria_snapshot()
                except Exception as exc:
                    aria_tree = f"[!] Could not capture aria_snapshot: {exc}"

            # 2. Capture all data-testid elements
            testids: list[dict[str, str]] = []
            try:
                elements = page.locator("[data-testid]").all()
                for el in elements:
                    tid = el.get_attribute("data-testid") or ""
                    tag = el.evaluate("e => e.tagName.toLowerCase()")
                    text = (el.text_content() or "").strip()
                    # Truncate text if too long
                    clean_text = " ".join(text.split())
                    if len(clean_text) > 30:
                        clean_text = clean_text[:27] + "..."
                    testids.append({
                        "testid": tid,
                        "tag": tag,
                        "text": clean_text
                    })
            except Exception:
                pass

        finally:
            browser.close()

    # Format output report
    output_lines = [
        "=" * 65,
        f" ACCESSIBILITY (ARIA) TREE & TEST CONTRACT INVENTORY",
        "=" * 65,
        "",
        "--- 1. W3C ARIA SEMANTIC TREE (aria_snapshot) ---",
        aria_tree.strip(),
        "",
        "--- 2. DECLARED data-testid ELEMENTS ---"
    ]

    if testids:
        for t in testids:
            desc = f' (text: "{t["text"]}")' if t["text"] else ""
            output_lines.append(
                f'  • [{t["tag"]}] data-testid="{t["testid"]}"{desc}\n'
                f'    --> page.get_by_test_id("{t["testid"]}")'
            )
    else:
        output_lines.append("  (No data-testid attributes detected on this page)")

    output_lines.append("=" * 65)
    result_text = "\n".join(output_lines)

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(result_text, encoding="utf-8")
        print(f"[+] Snapshot successfully saved to: {out_file}")
    else:
        print("\n" + result_text + "\n")


def main():
    parser = argparse.ArgumentParser(description="Quick Accessibility Tree & Test Contract Explorer for Playwright")
    parser.add_argument("--url", default="http://127.0.0.1:8000/", help="Target URL to inspect (default: http://127.0.0.1:8000/)")
    parser.add_argument("--file", help="Local HTML file path to inspect via file:// URI")
    parser.add_argument("--output", "-o", help="Optional output text file path")
    parser.add_argument("--timeout", type=int, default=5000, help="Navigation timeout in milliseconds (default: 5000)")

    args = parser.parse_args()

    if args.file:
        file_path = Path(args.file).resolve()
        if not file_path.is_file():
            print(f"Error: File not found at {file_path}", file=sys.stderr)
            sys.exit(1)
        target = file_path.as_uri()
    else:
        target = args.url

    try:
        dump_a11y_tree(
            target_url=target,
            output_path=args.output,
            timeout_ms=args.timeout,
        )
    except Exception as exc:
        print(f"[!] Error inspecting target: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
