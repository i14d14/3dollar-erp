# Agent Guidelines & Operating Protocols

## 1. Living SSOT Protocol (STATUS.md Governance)

All agents working on this project must strictly adhere to dynamic state tracking:

1. **Pre-Execution Check (Read First)**:
   - Before proposing plans or executing commands, always inspect [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md) to determine the current milestone, active tasks, and unresolved blockers.
2. **Atomic State Synchronization**:
   - Immediately upon completing and verifying any task or sub-milestone, update [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md) in the same turn:
     - Mark the corresponding checkbox as completed (`- [x]`).
     - Re-calculate and update the overall completion percentage.
     - Append a concise entry to the **Verification Log** table with timestamp, milestone, verification summary, and PASS status.
3. **Never Allow Drift**:
   - Working tree changes must never drift ahead of [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md). The file must reflect active operational ground truth at all times.

---

## 2. Architectural Guardrails & 4-Layer Hierarchy

Enforce the 4-layer dependency model defined in [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md):

```
Layer 4: AI Wrapper (Data Intake & Analytics)
   |
Layer 3: Channel & UI (LINE Bot Ordering, Support, Attendance)
   |
Layer 2: Extended Core (DanLee CRM & TanJee Accounting)
   |
Layer 1: Core Engine (Dinkoko ERP - Inventory, Orders, Invoicing)
```

### Invariants:
* **Unidirectional Dependency Flow**: Lower layers must NEVER import or depend upon higher layers.
  - Layer 1 (Dinkoko ERP) has zero outgoing dependencies on CRM, Accounting, LINE Bots, or AI wrappers.
  - Layer 2 (CRM / Accounting) depends on Layer 1 via domain events or explicit service boundaries.
  - Layer 3 (LINE Bots) interacts with ERP/CRM strictly through public service APIs / DTOs.
  - Layer 4 (AI Wrappers) acts as non-blocking sidecars or data transformation pipelines.
* **Architecture Fitness Functions**: Run `dependency-cruiser` to continuously enforce layer boundaries and prevent circular dependencies.

---

## 3. Native File Access Protocols

Follow the file access matrix specified in [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md):
* **Excel / CSV**: Use `openpyxl` for reading and manipulating workbooks; use `xlsxwriter` for streaming generation of complex formatted sheets (BOM comparisons, financial statements).
* **PDF**: Use `pymupdf` (`fitz`) for native text-layer extraction (electronic invoices, contracts) and PDF inspection. Do not treat native PDFs as raster images unless image-only OCR is explicitly required.
* **DOCX**: Use `python-docx` for reading Word templates and replacing document variables.

---

## 4. Platform & Tooling Guardrails

* **OS and Shell**: Windows host with Windows PowerShell. Always load [`powershell-docs`](file:///C:/Users/pigmao/.agents/skills/powershell-docs/SKILL.md) before shell operations. Strictly prohibit Linux-specific commands.
* **Encoding**: Explicit UTF-8 across all scripts (`sys.stdout.reconfigure(encoding='utf-8')`). Never redirect via PowerShell 5.1 `>` to prevent UTF-16LE mojibake.
* **Packages and Pip**: Standard library first. Never run `pip install` without explicit user permission.