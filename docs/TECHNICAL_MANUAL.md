> Domain routing: the NXTDeal retirement configuration and deployment gates are in `ops/domains/README.md`. Legacy domains are redirect sources only; rollout status must be verified there before claiming migration complete.

# DealerOS Technical Manual

## Dealer-owned storage and recovery

`core/dealer_cloud.py` owns tenant-local cloud settings, durable scheduling/leases, encrypted archive manifests and verified rclone transfers. `api/routers/dealer_cloud.py` enforces existing staff roles, explicit photo-publication consent and bounded public photo reads. `DealerCloudStorage.tsx` integrates with Administration Data Management and Merchandising. `scripts/recover_dealer_cloud_backup.py` decrypts/checks into a new offline directory only. This candidate keeps existing graph authority and feed image URLs. Provider authorization is operator-assisted and not yet verified live; the worker defaults off. Full contracts, recovery exclusions, environment setup and activation gates: `docs/dealeros-next/DEALER-OWNED-STORAGE.md`.

This is the living reference for how DealerOS actually works today. It's meant to be read by
someone who wants to understand the system, not by a session picking up the next backlog item
(that's `CLAUDE.md` + `BUILD_QUEUE.md`). Those two files remain the operational source of
truth and take precedence if anything here ever drifts out of sync with them.

**This file is maintained automatically.** Every session (interactive or scheduled) that
ships a feature updates the relevant section below — see "Keeping This Current" at the
bottom.

---

## 1. What DealerOS Is

A graph-native dealership operating system: instead of separate CRM / DMS / Finance / Service
systems each keeping their own copy of reality, every entity (customer, vehicle, employee,
lead, transaction, document, workflow) lives as a node in one shared graph. Departments read
and write a common source of truth instead of reconciling separate databases. Full philosophy
lives in `docs/Vision.md`.

Live product: dealeros.xyz (marketing/sign-in) and dealeros.xyz/workspace (the operational
assistant — chat plus department dashboards).

## 2. System Shape, End to End

```
Browser (Next.js frontend, 4 chat-first pages)
        |
        |  POST /ai/chat, GET /dashboard/*, GET/POST /<domain>/*
        v
FastAPI backend (api/app.py) — one process, one set of route handlers
        |
        |  imports plain functions from core/*_api.py
        v
core/*.py business logic — dataclass entities + module-level singleton repositories
        |
        |  save_*/load_* (JSON, indent=4)
        v
backend/storage/*.json  (graph.json is the database; everything else is legacy/orphaned)
```

There is no ORM, no external database, and no message queue. The entire graph is loaded into
memory on process start and mutated in place; writes are flushed back to `storage/graph.json`
via atomic replace (temp file + `os.replace()`, hardened in scheduled sessions 42-43 after a
truncation bug was found).

## 3. The Graph / Data Model

Every entity is a dataclass (`core/entities.py`) with a generated ID (`core/id_generator.py`:
`PREFIX-00001` style, one counter per prefix, recovered from the loaded graph on boot since
session 47's fix). Relationships are typed edges (`core/relationship_types.py`) stored
alongside entities in the same ledger (`core/ledger.py`'s `DealerLedger`), not a separate
table — this is what "graph-native" means in practice here.

Entity types currently defined (`core/entity_types.py`):

| Entity | Notes |
|---|---|
| Vehicle | franchise new/CPO + BHPH used; `Price`/`Cost`/`Condition`/`Lot` |
| Customer | |
| Lead | pipeline state lives as attributes on the Lead itself (`PipelineState`, `PipelineCreatedAt`, `PipelineStateSince`) |
| FinanceContract | created both by historical import and by funding a Deal |
| Lender | |
| ServiceRecord | `Technician` resolves to a real Employee id (fixed session 39) |
| Document | backs the chat file-attachment feature (session 47); raw bytes in the active tenant's `uploads/` dir (session 55, via `storage_paths.uploads_dir()`) |
| Image | |
| Campaign | Bumper Retention / Inventory Ads / Finance Renewal / Accessory Accelerator — one generic engine |
| Employee | ~45-person roster spanning every department |
| Vendor | |
| Channel / Message | graph-native messaging, real-time via `/ws/messaging` |
| Asset | marketing asset design/approval workflow |
| Website | fixed page set (home/inventory/about/contact), inventory grid queries the graph live at fetch time |
| Deal | multi-scenario desking, in-house BHPH + outside-lender financing, contract, funding |
| Part / PartSale | backs Parts KPIs in Bumper BI |
| BumperSnapshot | daily KPI snapshot, powers real trend deltas |
| BotCoverage / BotTaskEvent | agentic per-department task bot |
| Connection | data-connections / integration platform |
| EmployeeValueSnapshot | per-employee $ attribution |
| ComplianceAlert | compliance engine findings |
| NetworkPeerSnapshot | simulated peer-dealer benchmarking |
| KnowledgeArticle | role-gated knowledge base |
| FieldNote | generic dated department log (session 47) |
| WorkflowInstance | one in-progress/completed run of one of the catalog job workflows (session 53); optionally linked to another entity via `TRACKS` |
| LeadTask | user-created follow-up task tied to a Lead, with `due_at`/`completed` (session 92) |
| Appointment | one generic Sales/Service appointment (a customer/lead, a time, an assigned employee, a `department` attribute + status lifecycle) (session 96) |
| VehicleHold | short-lived reservation on an unsold Vehicle, `expires_at` computed on read (session 99) |
| UpRotation | singleton floor-rotation board for the Up System's round-robin (session 100) |
| ManagerTO | timed sales-to-manager turn-over: `requested→claimed→resolved`, linked to a Lead/Deal (session 101) |
| DemoDrive | test-drive log: prospect + vehicle + salesperson, license-verify gate, out/in odometer, `out→returned` lifecycle (session 102) |

Relationships used across the codebase include `INTERESTED_IN` (lead→vehicle), `ASSIGNED_TO`
(lead↔employee), `HAS_SERVICE_RECORD` (vehicle→service record), `AUTHORIZED`
(customer→service record).

## 4. Backend Module Map (`backend/core/`)

Grouped by domain, not alphabetically — this mirrors how the codebase actually grew.

**Graph core / infra**: `entities.py`, `entity_types.py`, `relationships.py`,
`relationship_types.py`, `ledger.py`, `registry.py` (VIN/lead-id/etc → entity-id lookups),
`id_generator.py`, `repository.py`, `storage.py` (load/save graph.json, atomic write,
counter recovery), `schema.py`, `queries.py`, `indexes.py`, `validation.py`,
`entity_filter.py`.

**Auth & access**: `auth.py`/`auth_api.py`/`auth_storage.py` (session-token auth, no
external IdP), `permissions.py` (`ENTITY_ACCESS`, `DASHBOARD_ACCESS`, roles: ADMIN,
OPERATIONS, SALES, MARKETING, SERVICE, FINANCE), `security.py` (`can_access_entity`).

**Lead lifecycle / pipeline**: `pipeline_state.py`, `pipeline.py`, `pipeline_analytics.py`,
`pipeline_metrics.py`, `pipeline_velocity.py`, `lead_assignment.py`, `lead_routing.py`,
`lead_aging.py`, `lead_lifecycle.py`, `lead_workflows.py`, `lead_intake.py`/`_api.py`
(quick-add, session 47), `stalled_leads.py`, `follow_up_queue.py`/`follow_up_dashboard.py`,
`escalation.py`/`escalation_routing.py`/`escalation_dashboard.py` (+ their `_api.py`s),
`routing_api.py`, `time_to_close.py`.

**Dashboards / analytics**: `salesperson_dashboard.py`, `manager_dashboard.py`/
`manager_analytics.py`, `workload_dashboard.py`, `velocity_dashboard.py`,
`workflow_dashboard.py`, `leaderboard.py`, `employee_performance.py` (+ matching `_api.py`
files).

**Quick-entry intake (session 47)**: `field_notes.py`, `lead_intake.py`,
`vehicle_intake.py`, `service_intake.py`, `documents.py` — each with a matching `_api.py`.
Purpose: give field-work-heavy roles a native form instead of a chat sentence, while
producing entities shaped identically to CSV-imported data (see `imports/`).

**Inline entity edit (2026-07-15)**: `entity_update_api.py` (`update_entity_api(role,
actor, entity_id, patch)`) — the write-side counterpart to `/entity/{id}`, backing
`POST /entity/{entity_id}/update`. Reuses `can_access_entity()` so editing never exceeds
viewing; `id`/`entity_type` permanently protected; merges the patch onto live attributes,
persists via `save_graph(GRAPH_PATH)`, and audit-logs a before/after diff. Covered by
`tests/test_entity_update.py` (session 72).

**AI assistant**: `ai_assistant.py` (`ask_ai()`, real OpenAI `gpt-4o-mini` call),
`ai_tools.py` (read-only, role-filtered graph tools: search/get-by-id/get-related, reusing
`can_access_entity`), `ai_api.py` (`ask()` — keyword fast-path for workload/leaderboard/
escalation queries before falling through to the LLM), `help_api.py` (a deliberately
separate, non-tool-calling `/help/ask` backing the floating help widget).

**NXTDeal suite integration**: `assets.py`/`assets_api.py` (marketing asset approval),
`campaigns.py`/`campaigns_api.py` (customer-lifecycle campaign engine, gates on linked
asset being approved), `websites.py`/`websites_api.py` (website/inventory builder —
overhauled session 85 into a real drag-and-drop builder: layout templates for
independent/OEM dealers, per-section AI regenerate, an image library, per-page SEO, a
live traditional/DriveFinder mode toggle, and real page-view analytics),
`personal_sites.py`/`personal_sites_api.py` (session 85 — one self-service personal
landing page per employee, live-borrowing its parent Website's branding), and
`website_chat.py`/`website_chat_api.py` (session 85 — REST+polling live chat,
one-click promote to a real CRM Lead; deliberately not a new public WebSocket, see
`core/website_chat.py`'s module docstring).

**NOTE:** the per-department Top Menu module map below (session 60–61 entries) has not
been kept current past session 61 — sessions 62–84 added `marketing_menu.py`/
`inventory_menu.py`/`finance_menu.py`/`administration_menu.py`/`readiness_menu.py`/
`network_menu.py` (closing out all 9 departments), plus Marketing's `crm`/`email_sms`/
`social_reputation`/`advertising`/`events` Menu Bar items and their own `core/*.py`
modules, none of which are reflected below yet. Treat `CLAUDE.md`'s per-session log as
authoritative over this section until a future session does a full pass to catch this
document up.

**DMS**: `deals.py`/`deals_api.py` — Deal Desk: desking, in-house BHPH + outside-lender
financing, contract, funding (funding creates a real FinanceContract).

**Bumper BI**: `bumper_bi.py` (5 KPI compute functions: Sales/Service/Parts/F&I/Executive),
`bumper_snapshots.py` (daily snapshot mechanism for trend deltas), `bumper_bi_api.py`
(ACL: ADMIN/OPERATIONS/FINANCE only).

**Agentic bot layer**: `bot_tasks.py` (per-department x per-seniority-tier catalog, real
graph gap-checks), `bot_learning.py` (act/dismiss heuristic prioritization),
`bot_coverage.py` (admin-activated "run bot as absent employee"), `bot_actions.py` (small
whitelist of safe auto-executable actions), `bot_scheduler.py` (asyncio background loop,
started/stopped via FastAPI lifespan). Task discovery is live-only (`GET /bot/tasks`) — not
delivered as DMs (removed session 37, was redundant with the bot button).

**Prediction / readiness / integration platform**: `prediction.py` (horizon-based
confidence-blend engine — real ledger dates blended against documented industry baselines,
tagged `basis="ledger"/"blended"/"industry_estimate"`; gates "ready to go live" on a 90%
confidence threshold), `data_connections.py`/`data_connections_api.py` (real CSV ingestion +
urllib-based API connection tester, ADMIN/OPERATIONS-only).

**Employee value**: `employee_value.py`/`employee_value_api.py` — real $ attribution via
`Deal.created_by`/`Vehicle.Price-Cost` (sales) and `ServiceRecord.Technician` (service),
`industry_estimate` fallback elsewhere; every result carries an `EFFECTIVENESS_DISCLAIMER`
(reassigning duties, not headcount reduction) — ADMIN/OPERATIONS-only.

**Compliance**: `compliance_rules.py` (7 real cited federal rules — TILA/Reg Z, FACTA Red
Flags, ECOA/Reg B, CAN-SPAM/TCPA, GLBA Safeguards, Reg Z advertising),
`compliance.py` (`enforce_gate()` blocks deal funding / campaign activation / asset+website
publish / connection creation until violations are fixed), `compliance_scheduler.py`
(full scan every 12h, notifies ADMIN/OPERATIONS + manager tier by DM), `compliance_api.py`.

**Network intelligence**: `network_benchmark.py` (blind-labeled simulated peer dealers,
percentile rank against fixed baseline anchors), `network_audit.py` (rules-engine
recommendation feed tying together Bumper BI + network percentile + employee-value
automation coverage + readiness), `network_api.py` — ADMIN/OPERATIONS/FINANCE.

**Knowledge base**: `knowledge_base.py` (16 seeded starter articles, per-article
`visible_roles`), `knowledge_base_api.py`.

**Messaging**: `messaging.py`/`messaging_api.py` (channels/DMs), `ws_manager.py`
(`ConnectionManager` — in-memory, single-process; would need Redis-style pub/sub to scale
across processes, not attempted).

**Audit**: `audit.py`/`audit_api.py`/`audit_storage.py` — atomic-write hardened (session
42), ADMIN-only dashboard. Also carries a tamper-evident hash chain
(`prev_hash`/`event_hash`, `verify_chain_integrity()`) as of the security-hardening
initiative (Task #4).

**Security-hardening initiative (2026-07-20/21, `CLAUDE.md` is authoritative for full
detail)**: a standing 14-task effort. Modules shipped so far: `mfa.py` (TOTP + backup
codes, wired into `auth_api.py`'s 2-step login — Task #3); `ai_audit.py` (durable,
per-call `AiActionLog` on top of `ai_management.py`'s in-memory counters — Task #5);
`ai_kill_switch.py`/`ai_kill_switch_api.py` (dealer-wide/department/bot/workflow-scoped
kill switches over `ai_management.py`'s 13-feature catalog; `is_ai_globally_enabled()`
is checked first inside `is_feature_enabled()`; `is_workflow_automation_enabled()` gates
`workflow_automation.py`'s `evaluate_rules()` — Task #6); `bot_permissions.py`/`_api.py`
(default-DENY `BotCapabilityGrant` capability system, 3-scope most-specific-wins
precedence, ADMIN-only to mutate — Task #7); and **`ai_execution_tier.py`/`_api.py`
(Task #8, verified 2026-07-21)** — a pure COMPOSITION layer over
`ai_management.py`'s `AI_FEATURE_CATALOG` classifying every real AI/automation surface
Informational / Assisted / Autonomous (a separate `FEATURE_EXECUTION_TIERS` dict with
per-entry rationale, not an in-place catalog edit; fail-safe default = Autonomous;
`requires_approval_chain()` True only for Autonomous; `list_execution_tier_catalog()`
merges the 13 catalog entries + 2 non-catalog surfaces = 15 total). Its flagship
reclassification: `workflow_automation.py`'s rule engine is now the first real
Autonomous action gated behind an Approval Chain — `create_rule()` starts a rule
INACTIVE and opens a real `ApprovalRequest` on `permissions_registry.py`'s new
`autonomous_ai_rule_activation` chain (one `TIER_MANAGER` step); `set_rule_active()`
refuses to arm the rule until that request's live status is `approved`.

**Department job-workflow engine (session 53)**: `workflow_catalog.py` (`WORKFLOW_CATALOG`
— a static 36-entry catalog, 4 real job responsibilities per department x 9 departments,
encoded directly from a document Sam attached; each entry has an ordered `stages` list
taken from the doc's "Workflow Steps" line, plus `entity_type`/`entity_label` as UI hints
only, not enforced), `workflow_tracking.py` (the one generic multi-stage engine —
start/advance/cancel/list a `WorkflowInstance`, resolving a linked entity permissively via
every `EntityRegistry.find_*` lookup in sequence), `workflow_tracking_api.py` (thin `_api.py`
layer). Not to be confused with the orphaned pre-unification modules just below — this is
graph-native from the start (an ordinary `Entity`, `TRACKS` relationship, no separate store).

**Sales "completely missing" workflows (sessions 100-102)**: bespoke modules filling
Sam's session-92 list of dealership workflows that had no data model at all, each a real
graph-native module + `_api.py` ACL layer (ADMIN/OPERATIONS/SALES), surfaced as a Sales
catalog workflow button with a matching `workflow_tab_data.py` REAL_SOURCES read panel:
`up_system.py` (round-robin floor Up board, singleton `UpRotation` + Lead attributes),
`bdc.py` (internet-lead speed-to-lead, a live filter over Leads, no new entity),
`manager_to.py` (sales→manager turn-over queue, `ManagerTO` entity, session 101 — wired
into UpSystemBoard + SalesOverviewBoard, not a standalone screen), and `demo_drive.py`
(session 102 — `DemoDrive` entity; a real test-drive log with an *enforced* license-verify
gate before a drive can start, out/in odometer → real miles/duration on return, `out→
returned` lifecycle; distinct from `appointments.py` which is a scheduled future slot).

CommandCenter navigation: the greeting is restricted to the home screen. A compact Show timeline disclosure controls the existing shared timeline; a non-current period remains visible when collapsed. Generic department sections and specialist workflows use a left rail matching the Sales/Marketing navigation, including each department’s Reporting view. The catalog and existing menu actions remain authoritative.

**Sales CRM (October 5, 2026)**: `components/sales/SalesCrmWorkspace.tsx` groups the canonical Sales tools with filterable, paginated lead/customer records and table/pipeline views. `api/routers/sales_crm.py` exposes read projections and per-employee `SalesCrmView` preferences (`CRMVIEW` IDs), plus `SalesCrmAccount` household/business/fleet groups (`CRMACC` IDs). Account members reference existing Lead/Customer IDs, and edits use revision conflicts. Lead stages, tasks, appointments, communication logs and desking reuse their existing mutation APIs. No parallel customer store or automatic message delivery. See `docs/dealeros-next/SALES-CRM-PARITY.md` for verified scope and remaining parity limits.

Sales CRM advanced tools: `api/routers/sales_crm_advanced.py` exposes `/sales/crm/segments` (typed OR/AND rules and preview), `/duplicates` (preview then manager merge), `/sequences` (definitions/enrollment) and `/enrollments/{id}/status`. Graph types: `SalesCrmSegment`/CRMSEG, `SalesCrmSequence`/CRMSEQ, `SalesCrmEnrollment`/CRMENR, `SalesCrmMergeAudit`/CRMMRG and archived `SalesCrmMergedRecord`. Sequence message drafts are existing MarketingChannelAction entities with CRMMSG IDs. `core/sales_sequence_scheduler.py` runs every 60 seconds from API lifespan and prepares tasks/approval drafts, never sends. Persisted output IDs prevent repeated scheduling, and delivery acceptance never completes a step. Marketing dispatch rechecks active enrollment/exit conditions. `components/sales/CrmAdvanced.tsx` provides the three Sales views. See the parity document for consent, identity-link merge blocks, permissions, pause/resume semantics and single-process limits.


**Top Menu navigation layer (session 60, extended sessions 60–61)**: a DMS/CRM-style
menu bar under the department color bar, distinct from the 4 job-workflow buttons. Same
one-catalog/one-engine shape as the workflow engine above: `menu_catalog.py`
(`MENU_CATALOG` — department → 8-item `{key, label, description}` list, always
"Overview | … | Reporting"), `menu_data.py` (`MENU_SOURCES` — department → item_key →
fetch function, plus a `QUERY_CAPABLE` set marking the items that take a search box),
`menu_api.py` (thin `_api.py` layer). Each department's real data lives in its own
`core/<dept>_menu.py` module of 8 `fetch(role[, query])` functions, each reusing an
already-role-filtered function where one genuinely matches, computing a small new
aggregate where the graph has the data but nobody queried it this way, and returning an
honest `not_yet_tracked` note (never a fabricated number) where the PDF asks for
something with no backing model. Catalogued so far: `operations_menu.py`,
`sales_menu.py` (both session 60), `service_menu.py` (session 61 — Service & Parts:
Overview/Appointments/Repair Orders/Customers/Shop Control/Parts/Warranty/Reporting,
backed by ServiceRecord/Part/PartSale/Recall). The department key is the value
`app/workspace/page.tsx` passes for the tab (`"Service"`, not "Service & Parts").
Remaining 5 departments (Marketing/Inventory/Finance/Administration/Network/Readiness)
need only a new `core/<dept>_menu.py` + two dict entries each — no engine/route/frontend
change.

**Security-hardening modules (2026-07-20, Tasks #9-14)**: `differential_privacy.py`
(Laplace-mechanism noise, wired into `network_snapshot.py`'s pipeline before bucketing),
`pii_scan.py` (reusable `assert_no_pii()` scanner + blocking snapshot pre-flight),
`pci_dss_guard.py`/`_api.py` (card-data guard + posture self-check), `crypto_agility.py`/
`crypto_agility_api.py` (versioned-prefix hash/signature agility + inventory scan),
`secrets.py`/`secrets_api.py` (`get_secret()` chokepoint + dev-fallback warnings), and
`sso.py`/`sso_config.py`/`sso_config_api.py` (OIDC auth-code-flow client + per-tenant IdP
config; routed via `api/routers/sso.py`). These join the earlier Tasks #1-8 modules
(`mfa.py`, `audit` integrity, `ai_audit.py`, `ai_kill_switch.py`, `bot_permissions.py`,
`ai_execution_tier.py`). All 14 tasks are backend-complete; none have frontend admin panels
yet.

**Orphaned, do not build on**: `workflow_repository.py`, `workflow_instances.py`,
`workflow_storage.py`, `assignment_storage.py` — pre-graph-unification modules, superseded
2026-07-13 by pipeline state/assignment living directly on graph entities/relationships.
Kept only because ~10 loose `test_*.py` scripts still exercise them in isolation.

## 5. API Surface (`backend/api/app.py`)

One flat FastAPI app, no router classes, no versioning. Route handlers call straight into
`core/*_api.py` functions. Every route requires a valid session token except `/`,
`/auth/login`, and the other `/auth/*` endpoints. Grouped by domain:

- **Auth**: `/auth/login`, `/auth/whoami`, `/auth/admin/credentials`
- **Graph search**: `/search`, `/entity/{id}`, `/profile/{entity_id}`, `/question`,
  `POST /entity/{entity_id}/update` (inline attribute edit — `core/entity_update_api.py`,
  gated by the same `can_access_entity()` as reads, `id`/`entity_type` protected,
  audit-logged before/after diff)
- **AI**: `/ai/chat`, `/help/ask`
- **Dashboards**: `/dashboard/*` (sales, service, finance, executive, pipeline, followup,
  velocity, salesperson, manager, leaderboard, workload, escalations) — per-department ACL
- **Leads**: `/lead/assign`, `/lead/escalate`, `POST /leads` (quick intake)
- **Quick-entry (session 47)**: `POST /notes`, `GET /notes`, `POST /vehicles`,
  `POST /service-records`, `POST /documents/upload`
- **Messaging**: `/messaging/*`, `ws /ws/messaging`
- **Marketing suite**: `/assets/*`, `/campaigns/*`, `/websites/*`
- **DMS**: `/deals/*`
- **Department Intelligence** (renamed from "Bumper BI" session 70): `/intelligence/departments`,
  `/intelligence/{department}`
- **Bot**: `/bot/tasks`, `/bot/tasks/feedback`, `/bot/coverage*`, `/bot/coverage/{id}/end`
- **Readiness / integration platform**: `/readiness/predictions`,
  `/readiness/timeline/{department}`, `/connections*` (create/list/upload-csv/test)
- **Employee value**: `/employees/value`, `/employees/{id}/value`
- **Compliance**: `/compliance/rules`, `/compliance/alerts*`,
  `/compliance/alerts/{id}/resolve|override`, `/compliance/scan`
- **Network**: `/network/departments`, `/network/benchmark*`, `/network/audit`,
  `/network/anonymous-snapshot` (server-to-server, Hub-only, `X-DealerOS-Network-Key`)

  > **Wiring note (session 89, 2026-07-16):** the Department Intelligence, Bot, Readiness/
  > Connections, Employee Value, Compliance, and Network route *decorators* in this
  > sub-list were only actually added to `api/app.py` in session 89 — the `core/*_api.py`
  > functions had existed and been imported since sessions 35-38, but had no `@app` route
  > exposing them, so these were unreachable over HTTP until session 89 (25 handlers wired
  > in one pass; frontend already called every one of these URLs). See BUILD_QUEUE.md's
  > session-89 entry.
- **Knowledge base**: `/knowledge/articles*`
- **Audit**: `/dashboard/audit` (ADMIN-only)
- **Security hardening** (2026-07-20/21): `/auth/mfa/*` (enroll/verify/disable — Task #3),
  `/audit/verify-integrity` (Task #4, ADMIN), `/ai-audit/*` (dashboard/actions/flush —
  Task #5), `/ai-kill-switch/*` (overview/explain/dealer-wide/department/bot/workflow-
  automation — Task #6) plus tenant-side `/network/ai-kill-switch-status|push`,
  `/bot-permissions/*` (catalog/effective/grants — Task #7), and
  **`GET /ai-execution-tier/overview` + `GET /ai-execution-tier/features/{feature_key}`**
  (Task #8 — the Informational/Assisted/Autonomous classification catalog,
  ADMIN/OPERATIONS-only, backed by `core/ai_execution_tier_api.py` via
  `api/routers/ai_execution_tier.py`, one of the extracted routers registered with
  `app.include_router()`). No frontend admin panel exists for the execution-tier catalog
  yet — deferred, same as Task #7's.
  Tasks #9-14 (all built 2026-07-20, verified end-to-end 2026-07-22 — see the note below):
  **Task #9 (differential privacy)** has no route of its own — `core/differential_privacy.py`'s
  `apply_dp_noise_to_kpi()` is a transform wired *inside* `core/network_snapshot.py`'s
  pipeline, adding calibrated Laplace-mechanism noise to each KPI *before* the existing
  bucket-rounding. **Task #10 (generalized PII scanner)** `core/pii_scan.py`'s
  `assert_no_pii()` is a blocking pre-flight re-scan at the end of the same snapshot
  pipeline (raises `PiiDetectedError`), plus a reusable scanner for any surface. **Task #11
  (PCI-DSS readiness)** `POST /pci-dss/posture-scan` (`core/pci_dss_guard.py` +
  `_guard_api.py`). **Task #12 (post-quantum crypto readiness)** `GET /crypto-agility/posture`
  + `POST /crypto-agility/inventory-scan` (`core/crypto_agility.py` — a versioned-prefix
  hash/signature agility layer). **Task #13 (secrets-management abstraction)**
  `GET /secrets/posture` (`core/secrets.py`'s `get_secret()` chokepoint + a startup
  `warn_on_dev_fallbacks()` stderr warning for hardcoded dev-fallback secrets). **Task #14
  (SSO scaffolding)** an OIDC authorization-code-flow client + per-tenant IdP config, via
  `core/sso.py`/`sso_config.py`/`sso_config_api.py` behind `api/routers/sso.py`
  (`/sso/login-options|begin|callback`, `/security/sso/config{,/enabled,/discover}`). No
  frontend admin panels exist for any of #9-14 yet — deferred, same posture as #7/#8. **This
  closes the standing 14-task security-hardening initiative on the backend.**
- **Department job-workflows (session 53)**: `GET /workflows/catalog`,
  `POST /workflows/start`, `POST /workflows/{instance_id}/advance`,
  `POST /workflows/{instance_id}/cancel`, `GET /workflows` — any authenticated role
- **Top Menu (session 60)**: `GET /menu/catalog?department=X`,
  `GET /menu/data?department=X&item_key=Y&query=Z` — one generic pair serving every
  department's every menu item; catalogued for Operations/Sales (session 60) and
  Service (session 61), returns an empty catalog / "not wired" for the rest
- **Sales "missing workflows" (sessions 100-102)**: `/up-system/*` (floor-rotation Up
  board), `/bdc/*` (internet-lead speed-to-lead queue), `/manager-to/*` (sales→manager
  turn-over queue), `/demo-drives/*` (test-drive log: `POST /demo-drives` start with an
  enforced license-verify gate, `GET /demo-drives{,/active,/dashboard}`,
  `POST /demo-drives/{id}/return|cancel`) — all ADMIN/OPERATIONS/SALES-gated. These are
  bespoke action surfaces on top of Sales' catalog workflow buttons, each also exposed as
  a `workflow_tab_data.py` REAL_SOURCES read panel

Route count last verified session 47 (99 total); has grown since (session 53 added 5 more)
— re-run `grep -c "@app.\(get\|post\|websocket\)" api/app.py` for a current count rather
than trusting either number as-is.

Two asyncio background jobs run via a `lifespan=` context manager (migrated off deprecated
`@app.on_event` in session 45): the bot scheduler and the compliance scheduler.

## 6. Frontend (`frontend/`, Next.js App Router)

Deployed pages, all chat-first and sharing one implementation pattern: `/` (marketing/
sign-in), `/workspace`, `/admin`, `/network`, `/readiness`, `/profile/[id]` (entity 360
view), `/panel` (pop-out workspace window), `/change-password`.

**The chat-first pattern.** Every "special" view — dashboards, entity profiles, employee
roster, audit log, compliance layer, readiness score, network benchmark, marketing/
campaign/website/deal forms — is requested via a chat sentence to `POST /ai/chat` and
rendered in a right-hand workspace panel. Nothing is auto-loaded or form-driven by default,
**except** the native per-department quick-action buttons added in session 47, which are a
deliberate exception: those are for input that's genuinely faster as a form than a sentence.

**Shared pieces (extend these, don't reimplement per-page):**

- `lib/useArtifactPanel.ts` — all panel state + every artifact loader, used by all 4 pages
- `components/ArtifactView.tsx` — renders whichever artifact came back
- `components/KnowledgeSidebar.tsx` + `lib/pins.ts` — pinned-results sidebar (localStorage
  key `dealeros_pins`, shared across pages)
- `components/EntityProfile.tsx` — shared profile rendering (`/profile/[id]` + workspace panel)
- `lib/useMessaging.ts` + `components/CommunicationsPanel.tsx` + `components/ChatDock.tsx` +
  `components/MessageContent.tsx` — one websocket per page load, channel/DM list, floating
  messenger, entity-mention linking
- `components/OnboardingTour.tsx` + `lib/tourSteps.ts` — generic spotlight tour
- `components/HelpWidget.tsx` + `lib/screenContext.ts` — floating "?" help (yellow),
  Getting Started + Ask AI tabs
- `components/KnowledgeBaseWidget.tsx` — floating "📚" search/browse (blue, left of HelpWidget)
- `components/BotWidget.tsx` — agentic task suggestions, polls `GET /bot/tasks` live
- `components/ReadinessIntegrationPanel.tsx` / `components/NetworkBenchmarkPanel.tsx` —
  always-visible (not chat-gated) panels mounted directly in `/readiness` and `/network`
- `components/Icons.tsx` — shared icon set (`NeuralIcon`, `PinIcon`)
- `components/ResizeHandle.tsx` + `lib/useResizablePanel.ts` — draggable workspace/chat
  divider (session 41)
- `components/DepartmentDashboard.tsx` — DEPRECATED (session 54): used to render the 4
  generic OS-style *read* dashboard buttons ("Sales & Deal Desk"/"Service & Parts"/
  "Marketing & Web"/"Finance & Executive", session 41). Sam: "delete the ... buttons"
  once `DepartmentWorkflowButtons.tsx` made them redundant — removed from all 4 pages'
  render trees; the file itself is an inert `export {}` stub, not a true delete (this
  session's tooling had no filesystem-delete capability on the repo's mount).
- `components/DepartmentQuickActions.tsx` — native per-department quick-entry buttons
  (session 47)
- `components/DepartmentWorkflowButtons.tsx` — the real per-department 4-button row
  (session 53, recolored session 54, rebuilt into a multi-window manager session 56):
  fully data-driven off `GET /workflows/catalog`, a 2-column grid of 4 launcher buttons
  (one per catalog workflow) that open `WorkflowWindow`s. Distinct from
  `DepartmentQuickActions.tsx`'s single free-form log button, which stays mounted
  alongside it. Each department's 4 buttons cycle through a `RIBBON_COLORS` array
  (`#3E6CB3`/`#46C0C8`/`#F4C300`/`#F44321` by position) — the exact 4 corporate-bar
  colors the deleted `DepartmentDashboard.tsx` used one-per-button.

  **Bespoke Sales workflow boards (sessions 100-102)** — most catalog workflows render
  only `LiveDataPanel`'s generic read view, but Sales' "completely missing" workflows get
  real action components mounted inside their window: `UpSystemBoard.tsx` (log an Up /
  toggle floor rotation), `BdcBoard.tsx` (internet-lead queue, "Log Contact" opens
  Prospects' `LeadRecordModal`), and `DemoDriveBoard.tsx` (session 102 — a keys-out board
  with a "Log a Drive" form whose license-verified checkbox is the enforced gate, plus
  inline per-drive Return with odometer/interest/feedback and Cancel; `lib/demoDrive.ts`).
  Manager TO (session 101) instead lives embedded in `UpSystemBoard`/`SalesOverviewBoard`
  rather than its own board.

  **Named-tab dispatch (`TAB_TO_SECTION` + `NamedTabContent`, session 103)** — every
  workflow window has an "Overview" tab (start/track/advance the WorkflowInstance) plus
  one tab per `core/workflow_catalog.py`'s `tabs` field. `TAB_TO_SECTION` maps a
  workflow key's real tab titles onto a `section` string, and `NamedTabContent`
  dispatches each `(workflowKey, section)` to the right bespoke board so every named tab
  shows genuinely different content instead of the same board repeated 5×. Any workflow
  key not in `TAB_TO_SECTION` still falls back to `PlaceholderTab`, unchanged.

  **Bespoke Operations workflow panel (`OperationsWorkflowPanel.tsx`, session 107 —
  Operations rebuild's ninth/final slice)** — the same treatment for Operations' 4
  catalog buttons (`operations.recon`/`deal_jacket_audit`/`inventory_reconciliation`/
  `interdept_sla`), all 20 named tabs. One shared component dispatches three panel
  shapes: Vehicle-typed (`VehiclePanel` — stock/inspection/recon-checklist/vendor/
  frontline via `lib/vehicleLifecycle.ts`, lot audit via `lib/operationsAlerts.ts`,
  aging + price-reduction/wholesale-review via `lib/inventoryAging.ts`, reconciliation
  via `lib/operationsTasks.ts`), Deal-typed (`DealAuditPanel` — customer verification +
  contract audit + compliance approve/reject/request-document via
  `lib/documentWorkflows.ts`, lender requirements via `lib/deals.ts`), and
  Interdepartmental SLA (`InterdeptPanel` — request intake → real OperationsTask,
  service scheduling → real recon board, completion verification → real closed tasks;
  entity optional). Reuses the Operations arc's own already-built engines, no new
  backend. Three tabs (Registration & Insurance, Parts Allocation, Financial Routing)
  are honest labeled gaps — no entity model exists for any of them.

  **`WorkflowWindow` (session 56)** — Sam: "each one needs to be a dashboard to work
  from, so it should open much larger, and act as its own workspace... have more than
  one (up to all 4) and be able to layer them, close them in different order." No
  longer a single centered full-screen-backdrop modal — each workflow opens as its own
  absolutely-positioned floating panel:
    - **Multi-window** — `DepartmentWorkflowButtons` tracks `windows: OpenWindow[]`
      (array order = z-stack, last = front). A launcher click opens a new window
      (cascading position, default `920x640`) or brings an already-open one to front;
      each window's × closes only that one, independent of the others.
    - **Draggable** (title bar) and **resizable** (bottom-right corner handle, `520x400`
      minimum) — both use the same window-level mousemove/mouseup drag-tracking pattern
      `lib/useResizablePanel.ts` established in session 41.
    - **3-zone layout**, per a second doc Sam attached ("deparment dash modals.docx",
      covering 8 of the 9 departments — not Sales): a left-hand nav with a synthetic
      "Overview" tab (the original real functionality — description/why-it-matters,
      stage-strip reference, start-new-instance form hitting `POST /workflows/start`,
      in-progress instances with `POST /workflows/{id}/advance` — plus the doc's 2
      "Core Functionality" widget descriptions per workflow, shown as clearly-labeled
      "planned — not yet wired to live data" cards) and one tab per
      `core/workflow_catalog.py`'s new `tabs` field (an honest "not yet wired"
      placeholder panel — none of the ~72 bespoke widgets the doc describes have real
      backend logic yet, per Sam's scoping answer: "real where cheap, honest
      placeholder elsewhere"), a central workspace grid, and a bottom toolbar
      (Cancel / Save Draft / Approve & Sync to Graph).
    - **Toolbar wired to lifted state, not a tab-switcher** — the Overview tab's state
      (instances/form fields/loading/error) lives in `WorkflowWindow` itself, passed
      down as props, specifically so Approve & Sync to Graph (calls the same real
      `POST /workflows/start`) and Save Draft (client-only "kept locally"
      confirmation — no backend draft concept exists) work from whichever tab is
      selected when clicked, not only when the Overview tab's own inline form happens
      to be open.
- `components/SuggestedPromptsFlyout.tsx` — collapsed "Suggested prompts" fan-up banner
  (session 47)
- `components/ChatAttachmentButton.tsx` — "+" file attachment in chat, uploads immediately
  to `POST /documents/upload` (session 47)

**Current workspace panel layout, top to bottom** (updated session 54): resize handle →
`DepartmentWorkflowButtons` (4 real, multi-colored per-department job-workflow launcher
buttons — clicking one opens a floating `WorkflowWindow`, session 56, not inline content)
→ native per-department quick actions → thin divider (`h-px bg-zinc-800`) → "Workspace"
label/pop-out/pin row → artifact content → chat log → suggested-prompts flyout →
attachment button + chat input. The old 4 generic OS-dashboard buttons (session 41) that
used to sit between the quick actions and the divider were removed session 54.
`/admin`/`/readiness`/`/network` each mount `DepartmentWorkflowButtons` with a fixed
department string (no tab switcher, since each of those pages already represents one
department) — nothing else sits below it on those 3 pages now. `WorkflowWindow`s
themselves render outside this panel's flow (`position: fixed`, viewport-relative), so
they float above the whole page rather than being confined to the workspace panel's
width.

**Suggested chat prompts (session 53):** each page's suggested-prompts list — `/workspace`'s
per-department `suggestedPrompts` map, `/admin`'s `ADMIN_SUGGESTED_PROMPTS`, `/readiness`'s
and `/network`'s `SUGGESTED_PROMPTS` — gained 4 new entries per department, one per catalog
workflow, phrased as plain-language questions (the chat-only "easy answer" path for the same
4 jobs `DepartmentWorkflowButtons` handles as a tracked, multi-stage workflow). Answered by
the existing `ai_assistant.py` tool-calling graph access — no new backend Q&A logic.

`dealeros-ui/` is a separate Vite+React+Redux app, NOT the deployed frontend — confirmed
still relevant by Sam, left untouched, do not build on both frontends at once.

**Multi-tenant deployment config (session 51):** `next.config.ts`'s `basePath` (from
`DEALEROS_BASE_PATH`) and `middleware.ts` (marketing-mode path guard) exist so this same
codebase can be deployed once per dealer plus once for marketing — see §11 and
`docs/DEPLOYMENT.md` for the full Coolify topology.

## 7. Data Architecture (Today vs. Planned)

Today: one JSON file, `storage/graph.json`, loaded fully into memory at process start,
mutated in place, flushed back via atomic replace only when `save_graph()` is explicitly
called. This is genuinely the single source of truth as of the 2026-07-13 workflow-engine
unification — lead pipeline state and employee↔lead assignment used to live in separate
JSON stores and were folded onto the graph itself.

Planned (per `docs/Vision.md`, not started): SQLite, then PostgreSQL. No ORM or DB
dependency should be introduced without discussing it first.

## 8. Conventions (see `CLAUDE.md` for the authoritative version)

Dataclass entities, no Pydantic outside FastAPI request bodies. One singleton repository
instance per module. Persistence always in a matching `*_storage.py` with symmetrical
`save_*`/`load_*`, JSON, `indent=4`. API wiring is direct function imports into
`api/app.py`, no service layer. IDs from `core/id_generator.py`'s `IDGenerator`
(prefix + zero-padded counter). Heavy vertical-whitespace formatting (one arg per line,
blank line before `return`) is the house style in `core/` — match it in files you touch,
don't reformat whole files.

## 9. Known Gaps (see `CLAUDE.md`'s "Known Gaps" for the up-to-date, numbered list)

At a glance: `core/security.py`/`permissions.py` exist and work but nothing decides *which*
role a request acts as beyond the session-token auth now in place; `docs/Roadmap.md` had
drifted stale against actual shipped phases (being corrected as phases complete); most of
the codebase has no automated tests — 76 loose `test_*.py` print-scripts at `backend/`
root predate the real `backend/tests/` pytest suite, left alone unless already being
touched (the real suite grows incrementally as modules are edited; session 71 added
`tests/test_navigation_catalogs.py`, 19 tests, giving the sessions 60–68 navigation
catalogs — `core/menu_catalog.py`'s 9×8 Top Menu grid and `core/workflow_catalog.py`'s
36×(5,5) workflow-modal grid, including session 68's dropped-`core_functionality` and
Marketing-repurpose invariants — their first committed coverage; session 72 added
`tests/test_entity_update.py`, 14 tests, covering `core/entity_update_api.py`'s inline
entity-edit gate — role gating via `can_access_entity()`, protected `id`/`entity_type`
stripping, the before/after audit diff, and the not-found/empty/non-dict rejections;
session 73 added `tests/test_workflow_tab_data.py`, 12 tests, covering
`core/workflow_tab_data.py`'s workflow-modal live-data engine — REAL_SOURCES completeness
(a 1:1 against the 36 catalog workflow keys, well-formed source blocks, session 68's
`marketing.reputation` intentional-empty gap) and `get_tab_data()`'s three reconstructed
role-gating branches (self_gated / admin_only / dashboard) plus linked-entity handling,
the exact control flow a FUSE-mount truncation had cut off mid-body earlier the same day);
session 74 added `tests/test_menu_data.py`, 16 tests, covering the Top Menu *dispatcher*
(`core/menu_data.py`'s `MENU_SOURCES`/`get_menu_data()` + `core/menu_api.py`'s wrappers,
sessions 60–67) — complementing session 71's static-catalog coverage: the 9×8=72
source↔catalog 1:1 grid, the exact 18-pair `QUERY_CAPABLE` set, and `get_menu_data()`'s
routing contract (unknown-dept/unknown-item/unwired-item error paths + the query-vs-non-query
call-shape split, exercised with sentinel fetches so no populated graph is needed);
session 75 added `hub/tests/test_hub_provisioning.py`, 24 tests, giving the NXTDeal Hub
(`hub/core/`, session 50) its first committed coverage — dealer id-generation/registry
lookups, `create_dealer` scaffolding + validation, `adopt_dealer` (registers without
touching storage), status/url mutation, `dealer_storage`'s atomic save/load +
truncation-tolerant `_recover_partial_array`, and the `dealers_api` response shaping;
this one runs green in the sandbox because the Hub modules don't import the
FUSE-truncated `*_menu.py`/`api.app` chain); session 76 added
`tests/test_lead_pipeline_analytics.py`, 15 tests, giving the graph-backed lead-pipeline
analytics *readers* (`core/lead_aging.py`/`stalled_leads.py`/`follow_up_queue.py`/
`time_to_close.py` — rewritten in the 2026-07-13 "one graph" unification to derive aging/
stall/follow-up/time-to-close from the Lead entity's `Pipeline*` attributes) their first
committed coverage, complementing `test_pipeline_state.py`'s coverage of the *writer*:
the inclusive 7-day stall threshold, reset-on-transition aging, SOLD-only close timing,
and avg-ignores-unsold math, all seeded with explicit pipeline timestamps so it's
deterministic and green in the sandbox; session 77 added
`tests/test_lead_routing_escalation.py`, 17 tests, covering the sibling routing/dashboard
cluster (`core/lead_routing.py` least-busy auto-assignment behind `/lead/assign`,
`escalation.py`/`escalation_routing.py` age-threshold escalation + least-busy reassignment
behind `/lead/escalate`, `employee_performance.py` conversion rate, `leaderboard.py`,
`workload_dashboard.py` — all rewritten in the 2026-07-13 "one graph" unification and
backing the workload/leaderboard/escalation dashboards), locking least-busy selection
(active/non-terminal leads only, empty-pool ValueError), the escalation dict shape +
inclusive 14-day threshold, conversion-rate rounding, and the leaderboard/workload sort
order; seeded with explicit ASSIGNED_TO relationships + pipeline states so it's
deterministic and green in the sandbox (17 passed; 43 with the rest of the lead-pipeline
cluster); session 78 added `tests/test_queries.py`, 29 tests, giving the Phase-4 graph
Query Engine (`core/queries.py`) its first committed coverage — the primitive lookups
(`get_entity`/`get_entity_relationships`/`get_connected_entities`/`find_entities_by_type`),
all five `*_360` profile builders (`customer`/`vehicle`/`employee`/`manager`/`team`,
including the exact relationship-direction contract each traverses — FINANCED_BY→COVERS,
OWNS/COVERS-source, MANAGED_BY, ASSIGNED_TO — and the missing-target skip), the four count
dashboards (`sales`/`service`/`finance`/`executive`), `search_graph`'s case-insensitive
substring + single-hit dedupe, `get_graph_view`'s IN/OUT tagging, `get_graph_tree`'s
depth-limit + cycle avoidance, and `ask_question`'s keyword router (finance/lender/vehicle/
service branches + plain-search fallback); seeded by hand into the singleton ledger so it's
deterministic and green in the sandbox (29 passed; 72 with the rest of the ledger-backed
cluster); session 79 added `tests/test_kpi_snapshots.py`, 23 tests, giving the daily KPI
trend-delta engine (`core/kpi_snapshots.py`, session 35, renamed session 68/70) its first
committed coverage — the piece behind every department's Reporting-tab trend deltas
(`with_trend()`, called from `core/department_intelligence_api.py`) and the Network Trends
screen, the one part of the Department Intelligence stack still untested
(`test_department_intelligence.py` covered KPI compute, never the snapshot/trend side).
Locks `find_snapshot`'s department/date filtering + non-snapshot-entity skip,
`record_snapshot`'s idempotency-per-(department, calendar-day) and numeric-`value`-only
persistence, `most_recent_prior_snapshot`'s deliberate exclude-today + latest-by-date, and
`with_trend`'s three percent-change edge branches (prior-zero-current-nonzero → `None`/
undefined but `has_history` still True, both-zero → 0.0, `abs(prior)` as the denominator so
a negative-to-less-negative move reads as a gain) plus a brand-new-key → no-history path and
the no-input-mutation contract; "prior" snapshots are seeded with fixed clearly-past
`snapshot_date`s so they never collide with the real `date.today()` the module reads, so
it's deterministic and green in the sandbox (23 passed; 58 alongside queries +
pipeline_state); session 80 added `tests/test_pipeline_analytics_cluster.py`, 20 tests,
giving the pipeline-analytics readers their first committed coverage — `pipeline_metrics.py`
(the pure conversion/loss/active/closed dict math), `pipeline_velocity.py` (avg
days-in-current-state grouped by state), `pipeline_analytics.py` (`get_pipeline_metrics`'s
composed summary), and `manager_analytics.py` (`get_employee_metrics`'s per-employee
active/closed/stalled/conversion rollup) — the pipeline/velocity/manager-dashboard side of
the "one graph" lead cluster that sessions 76/77 left uncovered (they hit aging/stall/
follow-up/time-to-close and routing/escalation/workload/leaderboard). Locks the percent
rounding (33.33), the six-active-state set, the ≥7-day stalled threshold, the composed
`average_time_to_close_days` over a fixed NEW→SOLD window, and the assigned-but-never-
pipelined lead counting toward `assigned_leads` yet skipped by the state loop; seeds Lead
entities + ASSIGNED_TO relationships straight into the ledger (relationships added directly,
not via `assign_lead()`, so no `save_graph`/disk write), deterministic and green in the
sandbox (20 passed; 63 alongside the rest of the lead-pipeline cluster); session 108 added
`tests/test_appointments.py`, 34 tests, giving `core/appointments.py` (the shared
Sales+Service Appointment/calendar entity, session 96) its first committed coverage — a
load-bearing module (`AppointmentsBoard`/`ServiceAppointmentsBoard` and
`sales_overview.py`'s My Tasks Widget all read it) that closed this codebase's single
most-repeated `not_yet_tracked` gap yet had zero tests. Locks `create_appointment`'s
validation (unknown department, wrong-department appointment type, missing scheduled_start,
missing/mistyped customer or lead), the `update_status` lifecycle (happy path +
status_history append + all three terminal states — completed/cancelled/no_show — locking
the record + unknown-status rejection), `reschedule_appointment` (resets to scheduled,
requires new_start, rejects a terminal record), `list_appointments` filtering
(department/assigned_to/status/linked_entity) + scheduled_start sort, and the three
date-range helpers (`list_todays`, `list_this_week`'s inclusive ±0/+7-day boundaries,
`list_upcoming_within`'s horizon + open-status filter + past-exclusion +
unparseable-timestamp skip); seeds Customer/Lead entities directly and stubs `save_graph`
so the real graph.json is never touched, deterministic and green in the sandbox (34 passed
in 0.50s); the 2026-07-22 scheduled builder added `tests/test_compliance_rules.py`, 62
tests, giving `core/compliance_rules.py` (the session-38 federal compliance rule catalog
that `core/compliance.py`'s `evaluate()`/`enforce_gate()` run every gated action against)
its first committed coverage — an almost-pure-logic module (its only external dependency is
a lazy `from core.dealeros import ledger` inside the two entity-resolving checks) that was
load-bearing but untested. Locks all eight `check(entity)` contracts: Reg Z contract
disclosure (12 CFR 1026.18 — no-contract / missing-field / zero-as-missing / missing-
disclosures / fully-populated), Red Flags identity (16 CFR 681.2 — no/unknown/wrong-type
customer, missing identity field, no contact method, email-alone satisfies, complete),
OFAC/SDN screening (E.O. 13224 — none / not-screened / not-cleared / cleared), ECOA adverse
action (12 CFR 1002.9 — not-applicable-unless-declined, declined-without-reason, declined-
with-reason), CAN-SPAM/TCPA consent (empty/all-clear/one-flagged/count-all + the five truthy
`DoNotContact` variants + missing-audience-entity skip), GLBA Safeguards encryption (16 CFR
314.4 — non-api not-applicable, https passes, http/leading-whitespace/case flags, empty
endpoint silent), and both Reg Z advertising-disclosure heuristics (12 CFR 1026.24 — the
`_mentions_rate_or_percentage` `%`/`APR` keyword scanner, asset rate-without-disclaimer /
blank-disclaimer / with-disclaimer / no-rate, website per-page rate-without-text_block /
short-body-doesn't-count / with-disclaimer / only-offending-pages-listed), plus the
`RULE_CATALOG` structural invariants (8 rules, unique ids, high/medium severity, documented
categories, callable checks) and `rules_for_action`/`all_rules` dispatch (deal_fund→3 rules,
each action→its rule, unknown→[], returned list is a copy). Constructs Entity objects
directly and seeds the ledger via its `reset()`-in-place singleton, imports no
FUSE-truncated `*_menu`/`api.app` code, so it collects and runs green in the sandbox (62
passed in 2.57s, pytest 9.1.1). The 2026-07-23 scheduled builder added
`tests/test_email_templates.py`, 30 tests, giving `core/email_templates.py` (the session-79
Email/SMS builder engine behind the drag-and-drop email builder + SMS builder) its first
committed coverage — load-bearing because a template becomes a real send once attached to an
activated Campaign (`core/campaigns_api.py`), yet previously untested. Locks the static
block/channel catalogs (8 block types + field schema, 2 channels), `create_template`
defaults (per-channel name fallback, unknown-channel→email coercion, `ai_generated` bool
coercion, ledger persistence), `update_template`'s `_EDITABLE_FIELDS` allowlist enforcing
channel/created_by/created_at/id immutability + missing/None-patch handling, `list_templates`
creator/channel filtering + updated_at/id reverse sort, `render_email_html` (all 7 real block
types, the `_esc` HTML-escape, the deliberately-verbatim `html` block, unknown-block skip,
spacer default), `render_email_text` (heading-uppercase, image/button/divider formatting,
`html`-block tag-strip), and the real GSM-7/UCS-2 segmentation math in `sms_segment_info()`
(160/153 GSM-7 and 70/67 UCS-2 boundaries, emoji/accented-char Unicode detection, empty/None
bodies). Stubs `save_graph` in the module namespace + resets the ledger/id-counter singletons
per test; imports only the ledger chain, so it runs green in the sandbox (30 passed in 2.12s,
pytest 9.1.1). The 2026-07-24 scheduled builder added `tests/test_marketing_lists.py`, 40
tests, giving `core/marketing_lists.py` (the session-82 Marketing Lists engine) its first
committed coverage — load-bearing because a MarketingList is the curated, editable
Customer/Lead-id snapshot campaigns target, and both `core/smart_audiences.py`'s "Save as
List" and `core/dealership_events.py`'s invite audience build on it, yet previously untested.
Locks `create_list` defaults, `build_list_from_pool`'s `[m.id for m in members]`
materialization + `pool:<key>` source tag, `update_list`'s `_EDITABLE_FIELDS` allowlist
(name/description editable; source/created_by/member_ids/id immutable), `add_members`'
CUSTOMER/LEAD-only + dedupe + skip-unknown filtering with the `{list, added}` shape,
`remove_members`, `delete_list`'s archive-not-hard-delete convention, `list_lists`
archived/creator filtering + updated_at/id reverse sort, the real server-side pagination in
`get_list_members` (page/page_size clamp — cap 200, floor 1 — `total_pages` ceil, 25/50/100
page-size options, dangling-member-id skip, entity_type_filter), and both `_serialize_member`
shapes (Customer name+phone+email with blank-name→id fallback; Lead LeadID/source/
pipeline_state). Stubs `save_graph` in the module namespace + resets the ledger/id-counter
singletons per test; imports only the ledger chain (`campaigns.build_audience` monkeypatched
for the pool test), so it runs green in the sandbox (40 passed in 1.17s). The 2026-07-25
scheduled builder added `tests/test_dealership_events.py`, 38 tests, giving
`core/dealership_events.py` (the session-84 Events dash, NXTDeal-Bumper half) its first
committed coverage — load-bearing because a DealershipEvent's invite audience is optionally a
real `core/marketing_lists.py` MarketingList (`publish_event()` snapshots that list's current
membership into real `EventRSVP(status="invited")` records at publish time) and
`promote_rsvp_to_lead()` is the post-event CRM tie-in that creates a real `source="Event"`
Lead wired back to the originating Customer via a `GENERATED_LEAD` relationship. Locks the
full event lifecycle state machine (create draft → publish→scheduled incl. the list-membership
snapshot skipping non-Customer/Lead + dangling members → start→live → complete from
scheduled/live → cancel from draft/scheduled, plus every illegal-transition + missing-id
guard), `create_event` validation/defaults, `update_event`'s `_EVENT_EDITABLE_FIELDS`
allowlist + edit-only-while-draft/scheduled gate, `list_events` filtering + start_time reverse
sort, `create_rsvp` (invited-vs-confirmed status rule, blank-name→Guest, bad
customer_id/lead_id coercion, missing-event error), `update_rsvp_status` allowlist,
`list_event_rsvps` scoping/filter, `get_event_detail` status rollup, and
`promote_rsvp_to_lead` (Event-sourced Lead + customer-name-wins + GENERATED_LEAD relationship
+ already-promoted guard). Stubs `save_graph` in both the `dealership_events` and
`lead_intake` namespaces + resets the ledger/id-counter singletons per test; imports only the
ledger chain, so it runs green in the sandbox (38 passed in 2.25s; 142 passed alongside
marketing_lists + email_templates + appointments).
The 2026-07-25 scheduled builder added `tests/test_smart_audiences.py`, 58 tests, giving
`core/smart_audiences.py` (the session-113 Smart Audiences engine, Marketing Growth
Platform kickoff) its first committed coverage — continuing the Marketing-engine test arc
(email_templates → marketing_lists → dealership_events → this). A SmartAudience is a saved,
reusable segment DEFINITION (a no-code field/operator/value AND-chain, or one of eight named
presets) that is re-evaluated LIVE against the current graph on every read — never a frozen
snapshot (that's what a MarketingList is; a SmartAudience freezes into one via "Save as
List"). Locks the `_apply_operator` comparison kernel (7 operators + None fail-closed +
numeric-vs-string coercion + contains + uncastable→False), the `evaluate_conditions`
AND-chain (credit_score / vehicle any-owned-match / finance-type-via-Deal /
unknown-field-fail-closed / empty-matches-all), and all eight presets — the heuristics
computed here (truck-model keyword + dedupe, Condition+DateSold warranty-window math,
ContractDate+TermMonths lease-maturity math, CreditScore<660 subprime with tolerant string
parse, in_house-Deal→customer BHPH resolution) plus the three that delegate to real engines
elsewhere (`campaigns.build_audience` retention/finance_renewal, `marketing_database_mining`
positive-equity + `get_equity_candidate_for_customer`), monkeypatched so the test exercises
smart_audiences' OWN wiring. Also `list_presets`/`evaluate_preset`/`preview_preset`
(unknown-key error + 10-sample cap) / `preview_conditions`, `_serialize_member`, the CRUD
lifecycle (create/delete/list + `evaluate_audience`'s preset-vs-conditions dispatch +
live-reflects-new-data invariant), and the `smart_audiences_api` view-vs-mutate role gating.
Stubs `save_graph` + resets ledger/id singletons per test. NOTE: unlike the lighter
marketing modules, `smart_audiences` imports `workflow_tab_data` at module top, which
transitively pulls the `openai`/`httpx` chain — the sandbox run installed `openai`+`socksio`
to let it import (import-time only; no key/network). Runs green (58 passed in 3.91s; 200
passed alongside dealership_events + marketing_lists + email_templates + appointments).
The 2026-07-25 scheduled builder also added `tests/test_advertising.py`, 69 tests, giving
`core/advertising.py` + `core/advertising_api.py` (the session-83 Advertising dash —
Meta/Google ad campaigns with inventory integration) their first committed coverage,
continuing the Marketing-engine test arc (… → smart_audiences → this). An AdCampaign is an
ordinary `AD_CAMPAIGN` graph entity (distinct from `campaigns.py`'s email/SMS Campaign) tied
to the Employee who built it and optionally to real Vehicle entities via `linked_vehicle_ids`
(id-only, resolved LIVE at read time); "launching" is an honestly-labeled SIMULATED action
(real status/timestamps, no real ad spend), and the module also carried a real data-loss bug
fixed 2026-07-18 (it shipped with zero `save_graph()` calls). Locks the static catalogs
(meta/google platforms, the four objective keys), `generate_ad_recommendation`'s three
branches (feature-flag-disabled short-circuit, a fake-client JSON-parse success, and any
exception → `{"error"}` fall-through) + the brief-defaults it sends, `fallback_recommendation`'s
placeholder shape, `create_ad_campaign`'s validation (unknown platform/objective) + draft
defaults + blank-name fallback + `ai_generated` bool coercion + `_valid_vehicle_ids` filtering
+ single `save_graph` fire, `get_ad_campaign`'s hit/miss/wrong-type, `update_ad_campaign`'s
`_EDITABLE_FIELDS` allowlist (status/created_by/created_at immutable) + linked-vehicle
re-validation + None-patch guard, the full lifecycle state machine (launch draft/paused→active
with launched_at set once, pause active→paused, complete active/paused→completed, cancel
draft/paused→cancelled, plus every illegal-transition + missing-id guard), `list_ad_campaigns`
platform/status/creator filtering + created_at reverse sort, `resolve_linked_vehicles`' live
attr projection + bad-id skip, and the `advertising_api` ACL layer (`_can_manage` =
ADMIN/MARKETING only, the manage-gated launch/pause/complete, the creator-or-manager-gated
update/cancel, the AI error→fallback shaping, and every response's `performance_note`). Stubs
`save_graph` + `record_call_attempt` + resets ledger/id singletons per test; exercises the AI
path through a fake client (sandbox installs `openai` for the import-time
`from openai import OpenAI` only — no key/network). Runs green (69 passed in 3.14s; 269 passed
alongside the full marketing-arc suite).
The 2026-07-26 scheduled builder added `tests/test_operations_tasks.py`, 61 tests, giving
`core/operations_tasks.py` (the session-106 "Universal Operations Work Queue") its first
committed coverage. An OperationsTask is a first-class `OPERATIONS_TASK` graph entity with
its own open→in_progress→closed lifecycle (distinct from the additive-attribute Vehicle
Lifecycle convention — it's its own unit of work, optionally *about* an entity via a plain
`linked_entity_id`), and its SLA fields (`hours_open`/`sla_hours`/`is_overdue` vs the
per-priority `SLA_HOURS` table) are computed LIVE at read time via `_enrich`, the same
no-scheduler convention `vehicle_holds.py` uses. Sibling engines
(`document_workflows`/`inventory_aging`/`operations_scheduling`/`workflow_automation`)
create tasks through it, so its validation + persistence contract is load-bearing. Locks
the static catalogs/tables, the live SLA helpers (`_parse` None/bad/naive-utc/aware,
`_hours_open` freeze-at-closed_at, `_enrich` no-mutation + is-overdue-only-when-open-past-SLA),
`serialize_task`'s dict-passthrough vs Entity-flatten, `create_task`'s validation
(bad task_type/priority/owner_bucket → error, no save) + draft defaults + `derived` =
bool(source_entity_id) + save-once/`_skip_save` batching, `get_task` hit/miss/wrong-type,
`update_task`'s not-found + bad-value guards + started_at-stamp-once + close-stamp +
reopen-clears-close-stamp + assignee update, `close_task` (not-found/already-closed/
None-notes→""), `escalate_task` (not-found/closed/→urgent+appended-note), `list_tasks`'
five filters + priority-then-created_at sort, `get_stats`' rollup shape, the three bulk
actions, and `_existing_source_ids`' non-closed-only dedup key + `sync_derived_tasks`
turning the three read-only signals (wholesale disposition / lot audit / open compliance
alerts) into deduped trackable tasks (the two signal source modules
`core.workflow_tab_data`/`core.compliance_api` stubbed via `sys.modules` so it exercises
operations_tasks' own sync wiring without the openai/menu chain; high-severity alerts →
urgent). Stubs `save_graph` + resets ledger/id singletons per test; imports only the ledger
chain, so it runs green in the sandbox (61 passed in 4.29s; 173 passed alongside
appointments + marketing_lists + dealership_events).
`ws_manager.py` is in-memory/single-process only.

Boot-fragility note (found session 69): `core/ai_assistant.py` constructs its `OpenAI()`
client at module *import* time, and `core/ai_api.py` imports it unconditionally, so any
failure to build that client — missing/expired `OPENAI_API_KEY`, a proxy/network quirk,
etc. — aborts the entire `api/app.py` import and takes the whole backend down at boot, not
just AI chat. Latent on Sam's machine (works today) but a real single point of failure; a
lazy client (construct on first `ask_ai()` call) would remove it. Flagged for Sam, not
changed autonomously.

## 11. NXTDeal Hub / Multi-Tenant Architecture (added session 50)

A separate small app, `hub/` (sibling to `backend/`/`frontend/`), for NXTDeal staff to
launch new dealerships and watch the network — not dealer-facing, not part of any
dealer's own `/workspace`.

**Model: process-per-tenant.** Every dealer runs the same `backend/` codebase as its
own process, pointed at its own storage directory via `DEALEROS_STORAGE_DIR`
(`backend/core/storage_paths.py`; defaults to plain `storage`, so today's one real
dealer is unaffected). Chosen over making the graph/ledger layer itself tenant-aware,
which would mean rewriting the singleton-repository pattern every `core/*.py` module
uses — process isolation gets the same practical isolation for far less risk.

**Provisioning** (`hub/core/provisioning.py`'s `create_dealer()`): validates
name/contact_email, generates a `DLR-00001`-style id, scaffolds
`backend/storage/tenants/{dealer_id}/graph.json`/`audit.json` (empty) and
`credentials.json` (one `{dealer_id}-ADMIN` credential, temp password shown once),
registers the dealer in `hub/storage/dealers.json`. Verified end-to-end via a live
sandbox boot in session 50. **Regression coverage added session 75:**
`hub/tests/test_hub_provisioning.py` (24 tests, green in the sandbox) covers
`create_dealer`/`adopt_dealer`/status+url mutation, the dealer id-generator/registry
lookups, and `dealer_storage`'s atomic save/load + truncation salvage — run it with
`cd hub && pytest tests/`.

**Not done by provisioning:** actually starting that tenant's server process (real
deploy infra, flagged for Sam) — `set_dealer_api_base_url()` just records where an
already-running instance lives once someone/something else has started it.

**Storage-path migration — COMPLETE as of session 55.** `api/app.py`'s 3 boot-time loads
and every `save_graph`/`save_audit_log`/`save_credentials` call site across `core/` now
resolve their path through `core/storage_paths.py` (`GRAPH_PATH`/`AUDIT_PATH`/
`CREDENTIALS_PATH`) instead of hardcoding `"storage/..."`, so a tenant booted with a
non-default `DEALEROS_STORAGE_DIR` has all of its writes land in its own directory. 16
`core` files were migrated in session 52 (the intake/document/bot/data-connection/lead
modules plus the assets/campaigns/deals/websites/routing/auth `*_api.py` files);
`workflow_tracking.py` was already on the constant. **The last residual is now done too
(session 55):** `documents.py`'s chat-attachment `UPLOAD_DIR` was the one non-json
storage-relative path left; it's now `uploads_dir()` from `core/storage_paths.py`
(alongside the new `UPLOADS_DIR` constant), kept as a module-level attribute so
`tests/test_intake.py`'s `monkeypatch.setattr(documents, "UPLOAD_DIR", ...)` still works.
Uploaded attachment bytes now also land in the active tenant's directory. **No
storage-relative path outside `core/storage_paths.py` remains.** (Sessions 52 and 55 were
both verified host-side/via focused unit tests only; the bash sandbox mount served
truncated file views, so a live `uvicorn` boot against the edited files wasn't run — the
changes are mechanical and follow `workflow_tracking.py`'s live pattern.)

**Hub auth today:** one shared-secret header (`X-NXTDeal-Hub-Key`), not real
per-employee login — there's no `NXTDEAL_STAFF` role concept yet, flagged for Sam.

**Network aggregation** (`hub/core/network_aggregator.py`'s `network_overview()`):
calls each opted-in, reachable dealer's own `/network/benchmark` over plain `urllib`,
reports what actually responded rather than faking network-wide insight. Meant to
eventually replace `core/network_benchmark.py`'s simulated peer-dealer seed once 2+ real
tenants exist — flagged as needing Sam's sign-off first, not an automatic swap.

**Dealer slugs + adopting pre-existing dealers (session 51).** `Dealer` gained a `slug`
field (`"dealer1"`, derived from the same counter as `dealer_id`/`DLR-00001`, so they
always agree numerically) — the URL-facing identifier used in the deployment topology
below. `hub/core/provisioning.py`'s `adopt_dealer()` registers an already-existing,
already-populated dealer (as opposed to `create_dealer()`'s scaffold-from-empty) without
touching its storage or issuing a new credential. Used live to register today's one
real dealer as `DLR-00001`/`dealer1`/`storage_dir="storage"`.

**Deployment topology (Coolify, session 51).** `dealeros.xyz` is a marketing-only site;
`dealeros.xyz/hub` is the Hub; each dealer is its own Coolify app deployment at
`dealeros.xyz/dealer1`, `/dealer2`, etc. — path-based, one deployment per dealer, per
Sam's explicit direction. Backend APIs live on their own subdomains
(`dealer1-api.dealeros.xyz`) rather than nested paths, specifically to avoid Coolify's
"Strip Prefixes" feature, which has open bugs when combined with path-based routing.
`frontend/next.config.ts` reads a build-time `DEALEROS_BASE_PATH` env var into Next's
`basePath` (every internal nav already used `next/link`/`useRouter()`, both
basePath-aware, so no other frontend code needed to change); `frontend/app/page.tsx`
reads `NEXT_PUBLIC_DEPLOYMENT_MODE=marketing` to swap the sign-in form for a "Request a
Demo" CTA; `frontend/middleware.ts` (new) keeps the marketing deployment's copy of
`/workspace` etc. unreachable. Full Coolify app/domain/env-var table: `docs/DEPLOYMENT.md`.

## 10. Automation

(numbered 10 rather than moved to the end deliberately — see §11 immediately below for
the Hub, which came later chronologically but is a big enough architectural layer that
it gets its own top-level section rather than being folded into §2/§7.)


A scheduled task (`dealeros-builder`, see `C:\Users\sambo\Claude\Scheduled\dealeros-builder\
SKILL.md`) runs autonomously, reads `CLAUDE.md` + `BUILD_QUEUE.md` fresh on every run (it
has no memory of prior runs or of any interactive chat), and picks up the next unchecked
`BUILD_QUEUE.md` item. **This is the key operational fact:** anything decided in an
interactive chat session only reaches the automation if it's written into `CLAUDE.md` or
`BUILD_QUEUE.md` before the session ends — the automation cannot see chat transcripts.
Interactive sessions are expected to close out the same way scheduled ones do: check off
backlog items, add a Session Log entry, and (as of session 47) update this manual.

## Keeping This Current

Every session that ships backend or frontend work should, as part of closing out (same
moment it updates `BUILD_QUEUE.md`'s Session Log):

1. Add/update the relevant section above — new entity types go in §3, new modules in §4,
   new routes in §5, new components/pages in §6, new gaps in §9, anything about the
   NXTDeal Hub / multi-tenant provisioning in §11.
2. Keep this a coherent reference, not a changelog — that's what `BUILD_QUEUE.md`'s Session
   Log is for. If something here is superseded, edit it in place rather than appending a
   correction.
3. If a whole architectural layer changes (e.g. a real DB replaces `graph.json`), update
   §2 and §7 together so the diagram and the prose don't contradict each other.

This instruction is mirrored in `CLAUDE.md`'s Working Agreement and in the
`dealeros-builder` scheduled task's own prompt, so both interactive and autonomous sessions
maintain it the same way.


## Dealership Lab (candidate, October 5, 2026)

The isolated `codex/dealership-lab` candidate replaces the Network presentation with a staff-only learning and scenario workspace. Existing Network services are not deleted or cut over. Lab workspace, version, profile, model and run entities are owned by the authenticated employee inside the tenant's canonical graph. Archived plans can be restored; version and run evidence are immutable. No second SQLite database is introduced.

The engine is canonical Chrono code, bundled verbatim with per-file SHA-256 and a source commit in `backend/chrono/shared/MANIFEST.json`. Refresh with `scripts/sync_chrono_dealership.py`, never edit the bundle. The original dealership mechanics are a Chrono model plugin; Chrono supplies execution admission, numerical shape checks, percentile bands, outcome regions and probability intervals. This explicit assumption path writes no observed training facts and does not bypass the historical model's data requirements. Paired comparisons calculate differences within trials, not by subtracting percentile summaries. Input snapshots, revisions and engine commit are retained for every saved comparison.

The October 15 parity candidate adds native setup/department, customer/mix, finance, goal planner, saved-version recovery and prepared-review screens in the existing left navigation. `setup.py`, `mix.py` and `goals.py` preserve source revisions and use canonical shared mechanics; preview and adoption are separate. Saved goal previews reopen without recomputation. Goal adoption and reported calibration create independent options. `reviews.py` freezes imported report periods for owner-scoped ADMIN/OPERATIONS draft/publication; publication is private, not dealership-wide or customer delivery. `notebook_export.py` exports exact saved revisions, preserving unknowns and provenance. New procedure checkpoints use C30/C60/C90/C120; legacy annual checkpoints require explicit new-edition migration. Due/location review cues do not rewrite saved evidence.

Decision chaining promotes the source workspace's scenario into a new baseline through `analysis.decision_source`. GET model exposes `decision_requires_hybrid`. For a reviewed real-path source whose proposed economics differ, POST decisions requires strict `acknowledge_hybrid: true`; only the new option becomes Hybrid and its data/review setup confirmations are cleared. The original baseline review is retained as history, never renewed as an attestation of modeled figures. Stale original real-data reviews still fail closed even with acknowledgement. Request identity includes true acknowledgement and retries retain the same option. Shared calculations remain unchanged.

The learning program uses source battle rules and owned artwork, with native NXTDeal controls. Progress XP is awarded for server-observed reviews and distinct substantive comparisons. Fictional game saves and wins remain client-reported, like the original program, and cannot create XP, verified facts, operational permissions or business results. Four wins unlock the final crew card; cosmetic packs do not affect analysis. Daily/weekly/monthly resets use UTC.

Public customer access, message delivery, provider settings, production data authority and Hub authentication are unchanged. Department workbooks and procedure notebooks now retain frozen expected totals, source-qualified reported follow-ups, 30/60/90/365-day checkpoints and versioned review locks in the canonical graph. They are private learning records, not shared operational approvals. Monthly CSV reports now use private canonical-graph revisions with preview tokens, cell-level source lineage, explicit corrections, complete-scope KPIs and frozen outlooks. Blank imports preserve existing cells; missing history is not imputed. Shared Chrono selects and samples a reported-metric model using at least six consecutive trailing months. The displayed origin is historical; information available now is not an as-known-then backtest. Separate hybrid options can apply reviewed unit economics; they do not mutate original plans or live accounting.

Procedures include imported primary-source reference links with their original recorded date (not a claim of current validation), separate rollout allowances, print/PDF-friendly records and 30/60/90/120-day planning projections over saved expected paths. Existing 30/60/90/365-day review checkpoints remain distinct. Old runs without expected paths show unavailable planning blocks.

Hub Module Management retains the existing `network` configuration key but presents it as Dealership Lab. An explicit live check/sync applies that desired switch to the tenant. The transport refuses HTTP, redirects, missing or development fallback network keys and mismatched `NXTDEAL_DEALER_ID`. Tenant policy revision checks and graph audit receipts protect changes; disabled policy blocks all staff Lab endpoints but retains saved records. This does not enforce other Hub module toggles or expose dealer report values to the Hub. Live secure configuration and exact CI/deployment verification remain required.
