# TODO Rules (Must) — Priority & Category Taxonomy

**Last updated:** 2026-02-19

This document defines the mandatory formatting rules for TODO items and the category taxonomy.
Goal: keep the backlog actionable for humans and code AIs (Codex), and prevent “drift” in priorities and boundaries.

---

## 1) Mandatory format

Every TODO item MUST follow this format:

- [ ] **(P0|P1|P2|P3)** **[CATEGORY]** *(optional: additional category tags, max 3)*  <short task title>

Examples:

- [ ] (P0) [API] [DATA] Fix SQLite `database is locked` on `/api/file` and `/api/original`
- [ ] (P1) [UI] [UX] Modal: show keyboard shortcut hint bar for media controls
- [ ] (P2) [OPS] [SEC] Docker/compose generator: default bind 127.0.0.1; LAN requires explicit flag

---

## 2) Priority definitions (P0–P3)

- **P0 (Critical):** crashes, data corruption, security exposure, major broken flows, high-frequency errors.
- **P1 (High):** missing core UX/features that strongly affect daily use (player controls, navigation, keybind scope).
- **P2 (Medium):** improvements, refactors that reduce future risk, moderate UX polish, secondary features.
- **P3 (Low/Later):** long-term ideas, experiments, non-urgent enhancements, “nice-to-have”.

### P0/P1 acceptance criteria rule (strongly recommended)
For P0/P1 items, add **short acceptance criteria** under the item (3 lines max):

- Repro:
- Expected:
- Minimal check:

Example:

- [ ] (P0) [API] [DATA] Fix SQLite `database is locked` on `/api/file` and `/api/original`
  - Repro: Open modal, navigate rapidly, trigger multiple file/original fetches
  - Expected: No lock errors; requests succeed or retry invisibly
  - Minimal check: 5 minutes stress test + smoke tests pass

---

## 3) Category tags (choose 1–2, max 3)

Use 1–2 tags in principle (max 3). Prefer tags that clarify **boundaries** and **risk surfaces**.

### Core categories (existing)
- **[UI]**: layout, modal/viewer behavior, components, styling, keyboard handling on the frontend
- **[API]**: routes, handlers, response formats, server-side interface contracts
- **[DATA]**: DB, indexing, scanning, ZIP handling, metadata extraction, caching strategy
- **[PERF]**: performance, latency, freezes, memory, caching optimizations, large dataset behavior
- **[OPS]**: deployment, runtime, packaging, LAN operation, Docker, releases, self-update
- **[TEST]**: unit/integration/e2e tests, harnesses, CI-like flows, repro scripts
- **[DOC]**: documentation, specs, READMEs, guidelines, changelogs
- **[MISC]**: anything that doesn't fit (avoid if a better tag exists)

### Boundary-focused categories (recommended additions)
These improve AI handoffs and reduce regressions by making constraints explicit.

- **[SEC] Security / Exposure**
  - LAN binding defaults, authentication/PIN, external open, path traversal, CORS/headers, secret handling
  - Use when the change affects: `0.0.0.0` bind, auth gates, file serving, ZIP extraction safety

- **[UX] Discoverability / Workflow**
  - status indicators, loading states, shortcut hints, error messaging, onboarding/tooltips
  - Use when the goal is “make it obvious / prevent user confusion”, not pure UI layout

- **[COMPAT] Compatibility / Migration**
  - backwards compatibility, legacy fields, versioned APIs, deprecations, DB migrations
  - Use when changing shapes/behaviors that older clients or saved states might depend on

- **[ARCH] Architecture / Common Layer**
  - module boundaries, shared helpers, responsibility splits, initialization unification, service extraction
  - Use when the work is “structure-first” (reduce future confusion) rather than feature-first

---

## 4) Tagging heuristics (quick rules)

- If it changes **default LAN exposure / auth / file serving** → include **[SEC]**
- If it changes **API shape / response keys / versioning** → include **[COMPAT]** (often with [API])
- If it changes **module boundaries / common helper layers** → include **[ARCH]**
- If it adds **loading states / hint text / guidance** → include **[UX]**

---

## 5) Session execution rule (recommended)

- Each session should close **exactly one P0** before moving on.
- After closing a P0:
  - update TODO checkbox
  - add a short note to CHANGELOG / docs if it affects behavior or contracts
  - add/extend minimal tests to prevent regressions

---

## 6) Copy-paste snippet for TODO.md header

Use this in `TODO.md` near the top:

- Every TODO item MUST include `(<Priority>) [Category]`.
- Priority: `P0/P1/P2/P3` only.
- Category: 1–2 tags (max 3): `[UI] [API] [DATA] [PERF] [OPS] [TEST] [DOC] [MISC] [SEC] [UX] [COMPAT] [ARCH]`.
- P0/P1 items should include short acceptance criteria (Repro → Expected → Minimal check).
- Per session, close exactly **one** P0 before moving on.
