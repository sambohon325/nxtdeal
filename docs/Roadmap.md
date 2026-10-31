# DealerOS Roadmap

> Updated 2026-07-12. This replaces an earlier stale draft that listed different phase
> names ("Artifact Framework", "Knowledge Ledger", etc.) than what was actually built. See
> `CLAUDE.md` and `BUILD_QUEUE.md` at the repo root for implementation-level detail and the
> live task backlog — this file is the high-level status summary.

## Phase 1 — Graph Foundation ✅

## Phase 2 — Business Objects ✅

## Phase 3 — Dashboards ✅

## Phase 4 — Query Engine ✅

## Phase 5 — Persistence ✅

## Phase 6 — API Platform ✅

## Phase 7 — Workflow Engine ✅

Workflow Definitions, Workflow Execution, Workflow History, Workflow Instances, Workflow
Repository, Lead Lifecycle, Workflow Dashboard, Workflow API, Workflow Analytics, Workflow
Persistence.

## Phase 8 — Audit Logging ✅

Core audit log, storage, and API wired into `api/app.py`; hooked into lead assignment,
escalation reassignment, and lead workflow creation/transitions. Test suite passing
(`backend/tests/test_audit.py`). Live-verified end to end 2026-07-13: backend boots clean,
`/dashboard/audit` returns real data, events survive a server restart.

## Phase 9 — Authentication 🔄 in progress

Core session-token auth built and live-verified (`core/auth.py`/`auth_storage.py`/
`auth_api.py`, `POST /auth/login`, `GET /auth/whoami`). Remaining: no way to create
credentials yet (register endpoint or seed script — decision pending), route protection
not wired into `api/app.py`'s other endpoints yet. See `BUILD_QUEUE.md`.

## Phase 10 — UI Platform ⬜

## Phase 11 — AI Operating System ⬜

---

Source vision/philosophy: `Vision.md`. Architecture detail: `Architecture.md`. Task-level
backlog: `../BUILD_QUEUE.md`.
