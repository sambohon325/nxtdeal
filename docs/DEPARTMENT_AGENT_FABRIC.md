# Department agents and automation fabric

Implemented 2026-10-03 in the existing NXTDeal backend and workspace. This document describes shipped behavior and external dependencies; it does not claim that unconfigured vendors or AI accounts are connected.

## Entry point

Open **Department Agents** in the workspace account menu, or `/agents`. The page uses the current authenticated employee and dealership API origin. It provides department tools, typed action forms, an approval queue, policy controls, event subscriptions, readiness/audit views and provider manifests.

## Canonical architecture

- `core/department_agents.py`: one versioned registry of READ, ACTION and EVENT capabilities, risk levels 0–5, Sales/Marketing/GM reference packs, and nine remaining department scaffolds. Provider definitions contain no separate business logic.
- `core/agent_fabric.py`: one gateway for UI, HTTP, MCP and workers. Department grants, current employee role, existing entity permissions, dealer denials and employee limits intersect. ADMIN has no universal capability bypass.
- `core/agent_actions.py`: typed native actions and trusted provider registrations. Native actions reuse existing lead tasks, lead workflow transitions, appointments and campaign drafts. Approval/review requests and deterministic message drafts are supported. No draft is represented as a send.
- `core/agent_context.py`: projections map both legacy and canonical field names. Customer timelines use explicit graph relationships and authorized observations. Inventory matches use observed interest links; next-action suggestions are labeled deterministic rules, without probabilities.
- `core/agent_events.py`: an opt-in background loop in the existing dealership process, running every 60 seconds. Events and per-subscription receipts persist. Every run re-resolves employee credentials and permissions. The worker prepares proposals; it never approves or executes them.
- `core/agent_data_bridge.py`: existing CSV imports now retain provenance for newly created entities. Source timestamps that the file does not provide remain null. The separately implemented Dealer Data Bridge shares the same `SourceObservation` and Chrono contracts.
- `chrono/contracts.py` and `intelligence/facade.py`: generic temporal contracts and an explicit unavailable-engine response. No Chrono algorithms or probabilities were invented.

## Operational workflows

1. **Sales stale-lead recovery:** checks observed open status and timezone-aware last activity, deduplicates by that observation, and proposes a real follow-up task. Default policy requires separate administrator approval for task creation.
2. **Sales actions:** draft messages, create tasks/appointments, advance valid lead workflow states, request manager review, inspect customer timelines, match explicitly linked inventory, and read rule-based next actions.
3. **Marketing:** inspect consent-segment counts and inventory; prepare campaign drafts; automatically propose an inventory campaign for a qualifying 60+ day vehicle with observed make/model. Publishing is separately gated by a connected provider.
4. **GM:** review authorized entity counts, stale leads, activity-data gaps, draft campaigns, approval backlog and execution exceptions; request record/deal reviews and use the shared approval queue.

## Approval and execution

Actions are proposed first. The client cannot supply its identity or role. At the HTTP boundary, roles are refreshed from the current credential record and the server distinguishes interactive sessions from API credentials. API credentials cannot approve actions, change dealer policy or reconcile outcomes. MCP exposes discovery, reads/proposals and proposal listing, with no approval or execution tool.

A different administrator approves consequential proposals. Execution rechecks current grants, policy, connected capabilities, consent and AI/bot/workflow/department switches. Prepared payload hashes and source-record hashes protect approval integrity. Proposals expire after 24 hours. Completed requests are idempotent; a reused key with different input is rejected. Failed saves roll back policy, proposal and approval metadata.

Default maximum autonomous risk is 2. Task creation is level 3 and requires approval by default. Draft campaign/message/review creation is level 2. Consequential actions remain level 4 and always require approval. Level 5 cannot execute through an agent.

Execution persists `executing` before effects. A crash or unconfirmed provider response produces an uncertain outcome, not an automatic retry. Administrators can reconcile it with a confirmed outcome and evidence reference. Reconciliation is terminal; it does not retry the action. Execution events feed the graph timeline and canonical event queue.

An interactive session is a credential boundary, not proof that a human is holding it: do not give administrator session tokens to external agents. Give integrations appropriately restricted employee API credentials.

## External adapters and credentials

SMS/email reuse `integrations_registry` only when its notification adapter is live. The gateway requires explicit current channel consent and a destination, passes the proposal ID as an idempotency key, and requires an explicit non-simulated dispatch outcome. Consent is rechecked at execution; missing consent is denial.

Other write capabilities use `agent_actions.register_connector(...)` at trusted server startup. Registration requires a typed schema, access validator, existing connection ID, centralized secret reference and dispatcher. Secrets resolve through `core.secrets` at execution. Packs and manifests never contain credentials. The graph journals only the agreed outcome projection, not arbitrary provider responses.

`campaign.publish`, `crm.update` and `crm.marketing_status.write` remain unavailable until an actual provider adapter is registered. The existing bridge's separate blocked write-proposal mechanism is unchanged; this gateway does not bypass its gates.

## AI interfaces

`GET /agent-fabric/manifest/{department}/{provider}` generates the same authorized contract for ChatGPT, Claude, Copilot, Hermes and OpenClaw. Each manifest includes tool schemas, canonical instructions, the HTTP gateway and MCP location. Installation status remains `not_installed`; changing the selected interface does not claim to install anything.

The authenticated endpoint `/agent-fabric/mcp` implements stateless JSON-response Streamable HTTP with initialize, ping, tools/list and tools/call. Protocol versions 2025-03-26 and 2025-06-18 are supported. POST requires JSON and an Accept header listing JSON and event streams. Origins and protocol versions are checked; GET returns 405 because this implementation does not offer SSE. Discovery and calls use current NXTDeal authorization.

Protocol references: [MCP transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) and [MCP tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

## API routes

All routes below have the `/agent-fabric` prefix and require employee bearer authentication:

- `GET /catalog`, `/readiness`, `/audit`, `/proposals`, `/subscriptions`, `/receipts`
- `GET /manifest/{department}/{provider}`
- `POST /invoke` with department, capability, input and an idempotency key for actions
- `POST /proposals/{id}/approve`, `/execute`, `/reject`, `/reconcile`
- `PUT /policy` for an interactive administrator's validated policy replacement
- `PUT /subscriptions/{automation_id}` with an enabled flag
- `POST /automations/{id}/run` for on-demand canonical workflows
- `POST /events/process` for an administrator-triggered event batch
- `POST /mcp` for supported MCP messages

Audit records contain actor, session fingerprint, canonical agent version, declared interface origin, capability, record IDs, decision and timestamps. Interface origin is metadata, not verified provider identity. Operational proposals retain bounded input needed for approval; separate audit events omit message bodies, task descriptions and credentials.

## Deployment boundary and remaining external work

The implementation inherits the existing isolated backend process per dealership and graph-file persistence. `legacy-process` is a compatibility scope label, not a shared-hosting tenant resolver. Gateway locking does not turn unrelated legacy graph writers into transactional operations. Multi-worker/shared-tenant deployment requires the repository's broader transactional persistence and membership work; do not use this implementation as a shortcut around that boundary.

Provider account installation/OAuth registration, real CRM/DMS/advertising write adapters and credentials, provider certification, and an approved Chrono Core artifact are not present in the repository. These are required before claiming live end-to-end integrations or predictive intelligence. No real customer communication was performed.

The remaining department packs are deliberately scaffolds as requested. Policy SLA/discount/appraisal thresholds are retained for future pricing/routing workflows; this release exposes no automatic pricing or lending decisions. Identity resolution readiness is reported as unmeasured rather than inventing a percentage. Event receipts that are blocked or uncertain stay visible for review; they are not silently retried.

## Validation

Backend tests use the isolated storage fixture in `backend/tests/conftest.py`; legacy import-time OpenAI initialization requires a dummy test key, with no real provider calls.

```powershell
$env:OPENAI_API_KEY = 'test-placeholder-not-a-real-key'
.\venv\Scripts\python.exe -m pytest tests/test_agent_fabric.py tests/test_agent_fabric_extended.py tests/test_lead_tasks.py tests/test_ai_kill_switch.py tests/test_data_connections.py tests/test_route_protection.py tests/test_campaigns.py tests/test_appointments.py tests/test_appointment_scheduling.py tests/test_integrations_registry.py tests/test_dealer_bridge.py -q
```

Frontend checks: `npx tsc --noEmit --incremental false` and `npx eslint app/agents/*.tsx`. The browser was checked against an isolated temporary dealership: sign-in, department rendering, preparing a task proposal, required approval disabling execution, and rejection. Preview: `docs/dealeros-next/previews/department-agents.jpg`.

Final verification: **390 backend tests passed**, full frontend TypeScript and agent-page ESLint passed. Canonical Consent records take precedence over legacy consent flags, including revocations and unknown/conflicting states.

## Production release — October 3, 2026

Commit `49e518d4c63e2e52105f71b215e29750b688c0fa` was pushed to `nxtdeal/chrono-brand` after exact-candidate [CI 37149076278](https://github.com/sambohon325/dealerOS/actions/runs/37149076278) passed. CI recorded 11,485 backend passes, 32 existing failures within the 33-failure baseline, zero new regressions, and successful frontend type checking and production build. The local production build also passed.

Coolify verified successful deployments of that exact commit: frontend `vcsnsoewklrugwys1iw4xtww` (2m11s), marketing `7xntzdengeirytmy2vaueqtl` (2m11s), and dealer API `farur6gzdkwta27tvjxheoaz` (4m38s). The API retains its single-process uvicorn command and existing `/data/dealer1-api/storage` to `/app/storage` mount.

All seven production DNS/TLS/availability/CORS probes passed after rollout. Unauthenticated catalog, readiness and MCP requests returned 401 with the expected app-origin CORS header. The live `/agents` page renders its sign-in requirement; available browser sessions did not provide valid employee authentication, so signed-in mutation verification remains the isolated-dealership browser evidence above. No production customer records, policies, subscriptions or messages were changed for verification.

Open [Department Agents](https://app.nxtdeal.app/agents) after signing in, or use the workspace account menu. Concurrent Dealer Data Bridge implementation files were preserved locally and excluded from this release. This release includes the agent-side CSV provenance hook and compatibility projections, not the separate bridge import UI. Third-party installation, connected write adapters and Chrono engine delivery remain external prerequisites.
