"""UI Manifest Contract Fitness Test.

Architectural fitness function verifying that:
1. tests/ui_manifest.yaml is valid, unique, and well-formed.
2. Every declared data-testid in the manifest physically exists in the rendered HTML templates.
3. Front-end refactoring cannot silently remove or mutate test contracts without breaking CI.
"""

from __future__ import annotations

from pathlib import Path
import re
import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT_DIR / "tests" / "ui_manifest.yaml"
TEMPLATES_DIR = ROOT_DIR / "src" / "channel_ui" / "web" / "templates"


@pytest.fixture(scope="module")
def manifest_data() -> dict:
    """Load and parse the UI Manifest YAML file."""
    assert MANIFEST_PATH.is_file(), f"UI Manifest not found at {MANIFEST_PATH}"
    content = MANIFEST_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    assert isinstance(data, dict), "UI Manifest must be a YAML dictionary"
    assert "modules" in data, "UI Manifest must define a top-level 'modules' key"
    return data


@pytest.fixture(scope="module")
def template_testids() -> set[str]:
    """Scan all HTML templates and extract all declared data-testid values."""
    assert TEMPLATES_DIR.is_dir(), f"Templates directory not found at {TEMPLATES_DIR}"
    testids: set[str] = set()
    pattern = re.compile(r'data-testid=["\']([a-zA-Z0-9_\-]+)["\']')

    for html_file in TEMPLATES_DIR.rglob("*.html"):
        text = html_file.read_text(encoding="utf-8", errors="ignore")
        matches = pattern.findall(text)
        testids.update(matches)

    return testids


def test_manifest_uniqueness(manifest_data: dict):
    """Verify that there are no duplicate testid definitions across modules."""
    seen_ids: dict[str, str] = {}
    duplicates: list[str] = []

    for mod_name, mod_info in manifest_data["modules"].items():
        for elem in mod_info.get("elements", []):
            tid = elem.get("testid")
            assert tid, f"Element in module '{mod_name}' is missing 'testid'"
            if tid in seen_ids:
                duplicates.append(f"'{tid}' (in {seen_ids[tid]} and {mod_name})")
            seen_ids[tid] = mod_name

    assert not duplicates, f"Duplicate data-testid found in manifest: {', '.join(duplicates)}"


def test_manifest_contract_against_templates(manifest_data: dict, template_testids: set[str]):
    """Verify that every testid defined in ui_manifest.yaml exists in HTML templates."""
    missing: list[dict[str, str]] = []

    for mod_name, mod_info in manifest_data["modules"].items():
        for elem in mod_info.get("elements", []):
            tid = elem["testid"]
            if tid not in template_testids:
                missing.append({
                    "module": mod_name,
                    "testid": tid,
                    "type": elem.get("type", "unknown"),
                    "description": elem.get("description", ""),
                })

    if missing:
        error_lines = [
            f"Contract violation! {len(missing)} data-testid(s) in ui_manifest.yaml not found in templates:"
        ]
        for m in missing:
            error_lines.append(f"  - [{m['module']}] testid='{m['testid']}' ({m['type']}): {m['description']}")
        pytest.fail("\n".join(error_lines))


def test_manifest_element_schema(manifest_data: dict):
    """Verify that every element conforms to standard naming and schema rules."""
    valid_types = {
        "button", "input", "select", "link", "table", "tbody", "tr",
        "container", "card", "text", "column", "modal", "form"
    }

    for mod_name, mod_info in manifest_data["modules"].items():
        assert "route" in mod_info, f"Module '{mod_name}' missing 'route'"
        for elem in mod_info.get("elements", []):
            tid = elem.get("testid", "")
            elem_type = elem.get("type", "")
            desc = elem.get("description", "")

            # Verify naming style: lowercase kebab-case
            assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", tid), (
                f"Element testid '{tid}' in module '{mod_name}' must be lowercase kebab-case"
            )
            assert elem_type in valid_types, (
                f"Element '{tid}' has invalid type '{elem_type}'. Expected one of {sorted(valid_types)}"
            )
            assert desc, f"Element '{tid}' in module '{mod_name}' must have a description"
