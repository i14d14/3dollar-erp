#!/usr/bin/env python3
"""Architecture Fitness Function: Enforce strict unidirectional layered dependencies.

Rules:
1. src/core (Layer 1) MUST NOT import: extended_core, channel_ui, ai_wrapper
2. src/extended_core (Layer 2) MUST NOT import: channel_ui, ai_wrapper
3. src/channel_ui (Layer 3) MUST NOT import: ai_wrapper
4. src/shared (Infrastructure/Kernel) MUST NOT import any higher domain layers.
"""
from __future__ import annotations
import ast
import os
import sys
from pathlib import Path
from typing import List, Tuple

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"

FORBIDDEN_RULES = {
    "core": ["extended_core", "channel_ui", "ai_wrapper"],
    "extended_core": ["channel_ui", "ai_wrapper"],
    "channel_ui": ["ai_wrapper"],
    "shared": ["core", "extended_core", "channel_ui", "ai_wrapper"],
}

class ImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: List[Tuple[int, str]] = []
        self.detailed_imports: List[Tuple[int, Optional[str], List[str]]] = []
        self.attribute_accesses: List[Tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append((node.lineno, alias.name))
            self.detailed_imports.append((node.lineno, None, [alias.name]))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.append((node.lineno, node.module))
            self.detailed_imports.append((node.lineno, node.module, [alias.name for alias in node.names]))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "default_event_bus":
            self.attribute_accesses.append((node.lineno, "default_event_bus"))
        self.generic_visit(node)

def check_file(file_path: Path, forbidden_modules: List[str]) -> List[str]:
    violations = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except Exception as e:
        return [f"Could not parse {file_path}: {e}"]

    visitor = ImportVisitor()
    visitor.visit(tree)

    for lineno, module_name in visitor.imports:
        # Check against forbidden prefixes
        for forbidden in forbidden_modules:
            if module_name == forbidden or module_name.startswith(f"{forbidden}.") or \
               module_name == f"src.{forbidden}" or module_name.startswith(f"src.{forbidden}."):
                violations.append(
                    f"{file_path}:{lineno} - Architecture violation: forbidden import of '{module_name}'"
                )

    # Architectural Rule: Forbid default_event_bus in core services, web routes, line_bot, and extended core
    rel_path = file_path.relative_to(SRC_ROOT).as_posix()
    forbidden_bus_prefixes = ["core/services", "channel_ui/web/routes", "channel_ui/line_bot", "extended_core"]
    if any(rel_path.startswith(p) for p in forbidden_bus_prefixes):
        for lineno, module, symbols in visitor.detailed_imports:
            if "default_event_bus" in symbols:
                violations.append(
                    f"{file_path}:{lineno} - Architecture violation: 'default_event_bus' import is strictly forbidden in '{rel_path}'. Event bus must be explicitly injected."
                )
        for lineno, attr in visitor.attribute_accesses:
            violations.append(
                f"{file_path}:{lineno} - Architecture violation: direct access to '{attr}' is strictly forbidden in '{rel_path}'. Event bus must be explicitly injected."
            )

    return violations

def run_checks() -> int:
    if not SRC_ROOT.exists():
        print(f"Error: {SRC_ROOT} does not exist", file=sys.stderr)
        return 1

    all_violations: List[str] = []

    for layer_dir, forbidden in FORBIDDEN_RULES.items():
        layer_path = SRC_ROOT / layer_dir
        if not layer_path.exists():
            continue
        for py_file in layer_path.rglob("*.py"):
            violations = check_file(py_file, forbidden)
            all_violations.extend(violations)

    if all_violations:
        print(f"❌ Found {len(all_violations)} architecture layer boundary violations:")
        for v in all_violations:
            print(f"  - {v}")
        return 1

    print("✅ All architecture fitness checks passed! Strict unidirectional boundaries verified.")
    return 0

if __name__ == "__main__":
    sys.exit(run_checks())
