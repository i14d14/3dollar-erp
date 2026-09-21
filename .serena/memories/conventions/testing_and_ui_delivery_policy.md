# Testing and UI Delivery Policy

1. **Mandatory UI Vertical Slice per Batch**:
   - Dinkoko ERP is a user-facing UI application.
   - Every implementation batch must deliver human-operable front-end UI components (HTML templates, modals, buttons, forms, input fields, and routes) in lockstep with backend services and APIs.
   - Backend APIs must never be delivered in isolation without the corresponding UI slice.

2. **On-Demand Playwright E2E Testing**:
   - Autonomous Playwright browser testing is resource-heavy and slow.
   - Do NOT run autonomous Playwright test suites (e.g. `test_playwright_*.py`) automatically after every batch or task.
   - Run fast unit tests, API integration tests, and architecture boundary checks (`check_boundaries.py`) autonomously.
   - Playwright E2E browser tests are executed strictly on-demand when the user explicitly instructs to do so.