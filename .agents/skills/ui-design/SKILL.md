---
name: ui-design
description: >-
  Minimalist UI design and front-end interaction guidelines.
  Use when designing, building, or refactoring front-end UI layouts, components, notifications, modals, forms, and feedback mechanisms.
  Do not use for backend-only database, accounting, or domain service logic.
---

# Minimalist UI Design Guidelines

Authoritative design principles and user preferences for front-end interface development.

---

## 1. Notification & Toast Lifecycle (TTL Protocol)

* **Success Notifications (`success`)**:
  - **Low cognitive load, zero action required**.
  - **3–5 seconds TTL**: Must automatically dismiss or fade out after 3–5 seconds to prevent visual clutter.
  - Provide a subtle manual close button (`×`) for early dismissal.

* **Critical Errors & Failures (`error` / `failure`)**:
  - **High cognitive load, corrective action mandatory**.
  - **No auto-dismiss by default** (or minimum 10+ seconds TTL): Operators require sufficient time to read the failure cause and fix invalid inputs. Forced auto-dismiss induces user anxiety.
  - Require explicit manual dismissal (`×`) or auto-clear on subsequent valid submission.
  - Must remain at the highest viewport layer (`z-[9999]`) floating above all modals and backdrops.

---

## 2. Modal Dialog Lifecycle & Form Ergonomics

* **Success Transition**: Automatically close modal on HTTP 2xx success, reset form inputs, and surface success toast on the underlying view.
* **Error Resilience**: Keep modal open on HTTP 4xx validation errors; preserve all user-entered field values.
* **Browser Autofill Handling**: Standard semantic HTML inputs (`type="text"`, `type="email"`, etc.) should be used directly without complex autofill hacks. Browser autofill heuristics (Chromium/Edge personal contact suggestions) are explicitly accepted as known browser-level behavior. Do NOT attempt complex workarounds (such as `readonly` toggles or hidden decoy fields) unless the user explicitly requests to revisit autofill. If autofill occurs or behaves abnormally, ignore it until explicit user instruction.

---

## 3. Custom UI Preferences (Living Log)

*Reserved for user-specific design preferences and progressive additions.*
