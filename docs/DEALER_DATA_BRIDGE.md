# Dealer Data Bridge foundation

Implemented 2026-10-03 in the existing NXTDeal repository. Open **Dealer Data Bridge** from the administrator account menu, or `/data-bridge` after signing in. No production data migration or deployment has been performed by this change.

## Existing architecture and integration decisions

The application uses the `DealerLedger` facade over `JsonGraphRepository`, a whole-file JSON graph. `core/schema.py` describes older import fields, not a database schema. Authentication uses signed employee sessions and API keys. Tenants currently run as separate backend processes/storage directories; `legacy-process` is a compatibility scope label, not shared-hosting tenant authorization. This feature does not introduce an ORM or assume request-level multi-tenancy.

Existing `data_connections` CSV/API paths and `integrations_registry` operational dispatchers are preserved. System Map lists old Connection records as legacy/unreviewed rather than claiming those records passed new review. New bridge metadata, staging, canonical entities, identities, audit and temporal observations all use the existing graph. Existing in-progress department-agent and Chrono work is preserved.

The canonical model uses vendor-neutral snake_case fields. A small internal projection also writes the established Customer/Vehicle/Lead/Employee aliases (`Email`, `VIN`, etc.) for legacy consumers. Existing entity prefixes are reused. Vendor field names belong only in versioned mapping proposals or future adapter modules; no vendor schema is embedded in the canonical model.

## Delivered modules

- `core/bridge_contracts.py`: canonical field catalog for dealer/location/employees, customers/households, leads, vehicles/ownership/prices, deals/finance, service/parts, accounting, communications, marketing and consent. BHPH domains include LoanAccount, PaymentSchedule, Payment, CollectionCase and Repossession. SourceRecord, SyncPage and Connector contracts are provider-neutral; money uses decimal strings.
- `core/bridge_connectors.py`: capability-aware catalog and trusted startup registry, real bounded CSV adapter, fail-closed vendor placeholders. SDK covers authenticate/discover/schema/history/sync/subscribe/write/reconcile/health. CSV only declares implemented operations. `core/bridge_adapters/frazer.py` provides an explicitly unverified, dealer-supplied file profile; live Frazer access remains unavailable. The scoped server-side credential broker accepts operator-provided secret references; secrets are never API request fields or graph credentials. A deployed secret-store provider remains an operator integration task.
- `core/dealer_bridge.py`: graph-backed System Map, immutable mapping proposals, staging, deterministic transformations, validation/quarantine, conservative identity candidates, activation, source IDs, append-only observations, sync/import health and blocked write proposals.
- `core/dealer_bridge_migrations.py`: explicit idempotent v1 graph-version migration. It adds a version/audit marker only. Existing records are not rewritten or assigned invented provenance. POST `/dealer-bridge/migrations/v1` with an administrator session when deploying. New bridge records are additive; no SQL migration applies to this storage backend.
- `api/routers/dealer_bridge.py`: authenticated administrator routes, registered in the existing app.
- `frontend/app/data-bridge`: System Map → mapping proposal → Discovery Import → Validate → Activate.
- `core/bridge_discovery.py`: bounded CSV or connected-schema column discovery before mapping, with header-only suggestions and no retained row contents. Connected inspection only calls an implemented schema capability for an operator-allowlisted object. Suggestions remain drafts and never infer vendor semantics or approve a mapping.
- `core/bridge_indexes.py`: per-preview identity/history lookups built in one graph pass. The index is discarded after validation and rebuilt before activation, preserving intervening-change checks without scanning the whole graph for every row.
- `core/bridge_lineage.py`: source-scoped lookup of canonical identity, current values and paged retained source snapshots. Current values are not presented as a full as-of reconstruction.
- `core/bridge_health.py`: explicit per-system diagnostic checks with bounded status output, durable leases, binding-revision evidence and late-response fencing. Checks never grant collection/write permissions.
- `core/bridge_reconciliation.py`: exact decimal totals by field/currency and optional independent row-count/amount expectations. Mismatch or quarantine blocks activation.
- `core/bridge_runtime.py` and `core/bridge_sync.py`: trusted per-system connector binding and disabled-by-default read-only collector with durable leases, backoff and checkpoint advancement after reviewed activation.
- `core/bridge_storage.py`: record-scoped rollback journal, preserving unrelated concurrent graph changes on Bridge persistence failures. The JSON repository flushes and fsyncs the temporary graph snapshot before atomic replacement; a failed flush preserves the previous file and propagates into Bridge rollback. This remains single-process storage. Parent-directory metadata, network-drive behavior and power-loss durability require deployment-specific validation; it is not a transactional database guarantee.
- `chrono/delivery.py` and `core/bridge_chrono.py`: provider-neutral delivery contract and opt-in durable outbox. No live sink is installed by this feature.

## Safe first import

1. Add the dealer's system using its real vendor name, even if ingestion is initially an authorized export. Vendor API health remains unavailable; successful CSV import health is tracked separately.
2. Propose a mapping for one source object and canonical type. Column transformations are a whitelist: text/lower/upper/integer/decimal, external_id for typed relationships, and finite lookup tables for selected code fields. New proposals bind source identity-column names, system, object, type, fields and transformation version into the approval hash. Hash versions 1/2 retain transformation v1; hash version 3 pins the exact transformation version. Existing v2 mappings retain UTC canonical timestamps and bounded integer fields; new v3 mappings additionally support reviewed value translations. Old approvals are not silently reinterpreted. No Python, JavaScript, SQL, expressions or model-generated code is evaluated.
3. Stage an authorized UTF-8 CSV, TSV or flat JSON export (<=1 MB, <=1,000 rows, <=100 unique columns). Flat JSON requires an array of records with matching property names; nested objects and booleans require a dedicated adapter. Every row needs a stable source ID and timezone-aware source modified time. Map the actual export headers to these roles in the proposal (defaults: `external_id` and `modified_at`). Those values are supplied by the source/export process. Do not substitute upload time for unknown source history. New jobs retain only mapped source columns and identity/time columns; other values are discarded before persistence. Evidence records include the original UTF-8 export SHA-256, schema hash, byte count and omitted column names. The Bridge does not archive the original file; retain it in dealer-approved storage if required. Older staged jobs are not silently purged.
4. Use **Test mapping without staging** for a nonpersistent preview, then stage when ready. Simulations create no jobs, approvals or audit records and never replace fresh validation. Validate and review the mapped values/errors. A proposal can be tested before approval. Missing references, invalid money/times/VINs, duplicate identities and inconsistent timestamps are quarantined; any quarantined row blocks the entire job.
5. Another administrator approves the immutable mapping. Revisions require a new proposal and approval. Activate the reviewed job from an interactive administrator session. Activation recomputes the preview to detect relevant graph changes, applies canonical values and retains source history.

Example customer export:

```csv
external_id,modified_at,name,email
customer-123,2026-10-01T15:30:00Z,Example,example@example.com
```

Map `first_name` to `name` using text and `email` to `email` using lower. Source object might be `customers`. Jobs and mappings have generated IDs; never use a vendor customer ID as the canonical graph ID.

BHPH imports require existing references: import customers before accounts and accounts before schedules/payments/collections. A relationship field can use an existing NXTDeal ID, or the external_id transform with a source object name. For example, map customer_id from the export’s customer column with transform external_id and object_type customers. Lookups use the current workspace and configured system only, require the expected target type, and block until the referenced source object has been imported. Automated multi-object dependency orchestration remains a follow-up. Financial imports record observations only: no payment collection, journal posting, collections action or repossession execution occurs.

Contract observations can retain principal, down payment, installment amount, currency, annual percentage rate, term months and start time. APR uses percentage points (7.5 means 7.5%), without legal/rate eligibility decisions. Account observations include past-due and scheduled amounts plus lifecycle/due timestamps. Payments/schedules support optional principal/interest/fee allocations; if all three allocations are present they must exactly equal the total amount, while missing allocations are not assumed to be zero. Reversal references require an existing payment in the same account and cannot reference the payment itself. These relationships do not adjust a balance or execute a reversal. Vehicle/deal/service-operation monetary fields can also preserve an explicit currency; missing currencies remain UNSPECIFIED in reconciliation.

## Identity, provenance and temporal semantics

External IDs are scoped to workspace + configured system + source object + external ID. A repeated approved snapshot is idempotent. A newer source version updates the same canonical entity; an older version records history without replacing the current projection. Conflicting data at the same source timestamp is quarantined, including historical conflicts. Event IDs normalize timezones and include content identity. A batch containing multiple versions of one external identity is blocked; use ordered separate jobs in this release.

Email/VIN candidates include legacy field aliases. Candidate matches are never automatically merged, including within a batch. The preview offers administrator-reviewed identity links, displaying both incoming values and candidate details. The administrator supplies a reason and a snapshot-bound review token. Linking adds source history and a persistent external ID to the existing record while preserving its current values, including on later imports from that linked source. It never merges two canonical records. Customer-only keep-separate decisions require reviewing every offered candidate and bind all candidate snapshots; this handles shared household email without allowing a VIN or within-batch duplicate override. Unactivated decisions can be withdrawn with a reason, retaining original evidence. Stale candidate/row/mapping snapshots require review again. API credentials cannot make identity decisions. Canonical-record merging and phone/household/fuzzy rules remain pending stronger matching evidence. Confidence is validation evidence (1 for accepted structured rows, 0 for rejected rows), not a statistical probability that identity is correct.

Bridge-origin SourceObservation records reuse the existing agent timeline integration and retain source system/ID/object, effective/source time, import time, immutable mapping ID, canonical values, identity decision, confidence and staging reference. Confidence is a deterministic validation/identity signal, not a calibrated probability or certification that the source is correct. GET `/dealer-bridge/chrono/observations` exposes stable event IDs and Chrono Observation-compatible fields. The outbox overlays delivery status from separate receipts; source observations stay immutable. Records remain pending until a trusted sink is installed and a human authorizes that exact destination name/revision. This feature does not claim remote prediction-engine availability.

POST `/dealer-bridge/lineage` accepts system ID, source object and external ID, with a bounded page size and optional cursor from the same lookup. It returns the current canonical values separately from source snapshots ordered by source time, including mapping/import references. The Source history section in `/data-bridge` exposes this lookup. Foreign-source cursors and wrong-workspace targets are rejected.

## Field-change review

Validation and nonpersistent simulations explain whether each row creates a record, updates mapped fields, preserves a linked record, retains an older observation, repeats an existing source version or is blocked. Before/after values are limited to mapped canonical fields. When a canonical value and its legacy NXTDeal alias differ, both are shown; the Bridge does not silently choose a new authority. Source history exposes the same divergence separately from retained observations. Simulation and staged review show 25 rows per page, with review issues first and an optional issues-only filter. Every row remains reachable, with original source row numbers preserved. Newly validated results reset to the first page; filtering never changes which records activation processes. Previously validated jobs without this richer preview require fresh validation before activation. Review snapshots can contain mapped current values as well as source values and remain subject to the deployment retention/access policy.

## Import dependency guidance

**View import order** on a System Map card reads the approved mapping references for that system. GET `/dealer-bridge/systems/{id}/import-order` returns ordered source-object groups, mapping-version choices, existing source-link counts and review warnings. Customers can precede contracts/accounts, then payments/collections; the order comes from actual mappings, not vendor guesses. Missing or incompatible source mappings, cycles, self-references and direct canonical-ID references are made explicit. Proposed, revoked or changed definitions are excluded. Guidance does not select a mapping, stage rows, approve anything or prove that each referenced source ID exists. Revalidate every export.

## Accounting journal observations

AccountingAccount supports source account code/type/currency/status. JournalEntry is a source line with amount/currency/time and optional journal_id, entry_side (`debit` or `credit`) and ledger_account_id. Explicit sides use nonnegative amounts; adapters must translate verified vendor sign conventions. Account references validate source account code and any declared account currency. No native general-ledger entries or accounting periods are created.

For an export containing complete journals, select **Require balanced journals in this export** or provide `expectations.balanced_journals: true`. The approved mapping must include journal_id and entry_side. Reconciliation compares exact debits/credits per journal and currency and blocks missing group metadata or imbalance. It does not net across journals/currencies or certify an accounting period. Partial exports leave this option off and remain source observations. Existing mappings/expectations retain their previous behavior.

## Authorization, agents and write-back

### Financial observations and native operations

Canonical Payment, FinanceContract, Deal, Campaign and Consent imports use `ImportedPayment`, `ImportedFinanceContract`, `ImportedDeal`, `ImportedCampaign` and `ImportedConsent` graph storage types, with `canonical_kind` and `import_semantics=observation_only`. The corresponding native types drive posting, servicing, deal funding and campaign activation; imported statuses must not enter those operational lifecycles. Typed Bridge references resolve both the canonical imported contract and an explicitly supplied native contract ID, without altering the native record. The accounting posting entry point now verifies the native Payment type. Promoting imported facts into operational finance records remains a separate reviewed workflow; importing a payment does not record a second cash receipt or change an account balance. Existing native records are untouched. Any pre-release Bridge records using older native storage types require an explicit reviewed migration before reuse; no production migration has been run.

Imported consent is evidence, never automatic permission for outbound messaging. The agent send guard considers both native and imported channel consent. When the latest evidence is imported (even a source `granted` value), sending remains blocked until a later native consent decision is recorded through a separately reviewed process. Equal-time conflicting evidence denies permission, as do unknown states and customer-level do-not-contact. Imported opt-outs therefore cannot be bypassed by a legacy positive flag. Channel casing/outer whitespace cannot hide SMS/email opt-outs. Explicitly foreign-workspace consent records are excluded. This is a conservative technical permission boundary, not a legal determination of consent validity.

### Read-only collection and mapping changes

An operator binds a distinct authenticated adapter per system through `bridge_runtime.bind`; credentials and endpoint URLs never arrive through Bridge HTTP bodies. A human saves the collection policy, which pins the adapter revision. A revision change requires review again. Schedules are off by default; manual collection is also session-only. A nonempty page is durably staged and awaits human validation/activation before its opaque cursor advances. Empty pages may advance without canonical writes. Invalid contracts, cancellations, revoked mappings and exhausted retries block the stream; errors do not echo vendor payloads. Adapters must enforce bounded network timeouts.

Registration and runtime binding validate a bounded capability declaration and reject missing or explicitly unavailable methods without invoking them. The binding snapshots verified capabilities; a declaration alone does not prove authenticated vendor access. POST `/dealer-bridge/systems/{system_id}/discover-schema` accepts only canonical kind and source object. It returns up to 100 flattened column names and draft suggestions, without fetching records or persisting the response. A pause, unbind or binding replacement during inspection discards the result. Demo mode blocks external inspection, collection and delivery.

Collection mode is `sync` (default, preserving existing stream IDs) or `history`. Backfill has its own cursor and requires a declared history implementation; both streams use the same source-record identity namespace. Every nonempty history page needs activation. The final accepted page, or a final empty page, completes the backfill and disables its schedule; completion survives restart. Generic retry does not rewind completed history. Adapters must split multiple versions of one external identity into separate ordered pages.

`ConnectorFailure` provides a bounded allowlist of public failure codes and an optional 1–86,400-second retry delay. Rate-limit delays are honored alongside exponential backoff; access/permission/source changes always require review. A new active connector scope/instance or Chrono sink instance requires a new revision. Operator startup configuration must preserve the same account/destination identity when reconstructing a reviewed revision after restart.

For a replacement mapping, approve a new proposal for the same system, source object and canonical type. Preview the transition and submit its snapshot-bound review token plus reason. An unreviewed pending job must first be activated or cancelled. An activated page is checkpointed; a cancelled page is never checkpointed. The source position is preserved, the prior mapping and transition evidence remain, and scheduling is disabled after the change. A source identity namespace change needs a separate migration plan; this flow does not reset cursors or reinterpret external IDs. Completed history remains terminal, including a final activated page whose end cursor is empty; replacing its mapping cannot silently restart backfill.

### Chrono outbox

`bridge_chrono.bind_sink` is a trusted startup hook. A sink must declare durable event-ID deduplication and enforce its own network timeout. Human policy authorizes its exact name/revision; changed bindings or lost administrator authorization block delivery. Batches use durable fenced leases and individual receipts. Delivery is at least once, including after a crash between remote acknowledgment and local persistence; sinks must deduplicate the stable event IDs. Partial receipts acknowledge only named requested events, and unknown, duplicate, oversized or excessive receipt IDs fail closed before acknowledgment. Receipt IDs are limited to 120 characters and the returned count cannot exceed the requested batch. Source observations are never rewritten with delivery state. Acknowledgments arriving after a disable request are retained as factual receipts, but no new delivery starts. No sink is connected by default.

All bridge routes require administrator access in the existing dealership process. Body-supplied workspace IDs, credentials and unknown fields are rejected. API credentials can propose/test mappings and stage exports but cannot approve mappings, run migration or activate imports. Approval requires a different administrator from the proposer. The server derives session/API principal type from authentication, not client assertions. This is a credential boundary: a tool holding a human session has the session's authority, so do not distribute administrator session tokens to agents.

There is no AI-provider import or dependency in the bridge. Any provider can propose declarative mappings through the same authenticated interface. Neither connector registration nor a successful import grants writes. Write proposals are retained as blocked; there is no write execution route. A future write implementation must add operation-specific human approval, immutable payload hash, expiry, scoped credential/consent checks, idempotency, retry/reconciliation semantics and independent adapter tests before enabling dispatch. Disable-switch enforcement must sit before all outbound effects.

## Coverage and rollout path

Catalog coverage is a requested roadmap, not a statement that an API or partnership exists:

- Franchise DMS: CDK/Fortellis, Reynolds, Tekion, Dealertrack, DealerBuilt, Auto/Mate.
- Independent/BHPH: DealerCenter, Frazer, AutoManager DeskManager, DealerSocket IDMS/AutoStar, Wayne Reaves, Deal Pack, Carsforsale.com, Dabadu and an other-system entry.
- CRM: Elead, VinSolutions, DriveCentric, DealerSocket CRM, HubSpot, Salesforce, Zoho, AutoRaptor and other providers.
- Websites: DealerOn, Dealer.com, Dealer Inspire, AutoRevo, Dealer Car Search and other providers.
- Accounting: QuickBooks, Xero, Sage, NetSuite.
- Marketing: Google, Meta, Microsoft, Mailchimp.
- Phones: Twilio, RingCentral, CallRail. Payments/servicing: REPAY, PayNearMe and other providers.

**Next highest-priority connector: validate the Frazer export profile against an actual authorized independent/BHPH dealer sample.** The file-intake scaffold now accepts dealer-supplied ID/time columns and mapping proposals, but no verified vendor schema or native API adapter is claimed. This is a sequencing choice, not a verified assertion about Frazer API/export availability. Start with customers and inventory; then verify loan/account/payment meanings against source balances. The generic CSV review path is usable now. DealerCenter/IDMS and CDK/Fortellis follow based on the first pilot dealer's installed systems and actual access.

For each vendor: obtain dealer authorization and vendor docs/access requirements; keep source schemas in a dedicated adapter; add sanitized fixture/contract tests; verify discovery, pagination/history coverage, deletes/corrections, rate limits, secret resolution and reconciliation; expose only verified capabilities. Build read-only import first. No endpoints, OAuth scopes, certifications or credentials have been invented.

The expanded [connector delivery plan](DEALER_BRIDGE_CONNECTOR_PLAN.md) records verified partner/contact references, independent/BHPH sequencing and separate CRM/accounting/website/phone/marketing workstreams. Other-system catalog entries accommodate stacks not yet named in the roadmap.

The [adapter SDK guide](DEALER_BRIDGE_ADAPTER_SDK.md) specifies page/schema contracts, exact monetary values, history semantics, revision/scoping obligations, safe failure codes and fixture verification. It includes only synthetic examples, not fabricated vendor schemas.

## Activation receipts and code translations

Each new activated job retains a versioned activation receipt in the same commit as its canonical changes. It captures mapping proposer/approver, staging and validation actors/principal types when recorded, activator, timestamps, connector revision/collection mode, input/preview fingerprints, reconciliation and identity-review references. GET `/dealer-bridge/imports/{id}/report` returns it; the import card exposes **Import evidence and approval receipt**. Later mapping revocation and idempotent reactivation do not rewrite it. Failed persistence rolls it back with the import. Old imports without receipts are labeled honestly and are never backfilled with invented approval evidence. The checksum detects accidental changes; it is not a digital signature or independent source certification. There is no receipt-edit endpoint.

A `lookup` transform maps exact source codes to explicitly reviewed text values for status, channel, direction, payment method, account type, department, journal side or currency. Tables contain 1–100 entries, each at most 120 characters; no defaults, wildcards or expressions. Source input is trimmed, then matched case-sensitively. Unknown nonblank codes quarantine the row; blanks retain the normal omitted-field behavior. Normal canonical validation still applies afterward. The mapping UI displays the complete table before approval. Agents can propose/test these tables but cannot approve or activate them. Edits require a new proposal. This normalizes documented codes, not permission or consent semantics inferred by a model.

## Identity review and export-profile follow-up

POST `/dealer-bridge/imports/{job_id}/identity-review` accepts row, target_id, review_token and reason. Candidates/tokens are obtained only from current validation results; unoffered, wrong-type, foreign-workspace or changed candidates are rejected. Review invalidates the previous preview; revalidate before activation. Linked-source updates retain source observations while preserving current graph attributes. Existing-source updates also fingerprint the current target at validation time, preventing unnoticed intervening edits from being overwritten at activation.

Source-column names are part of the immutable mapping proposal and shown in the UI. Discovery and mapping preserve exact header characters, including leading/trailing spaces; source values still follow their approved transforms. The Frazer adapter only parses a supplied CSV profile; its requirements explicitly list the missing authorized sample, stable-ID/time semantics, customer/account relationships and balance reconciliation. Synthetic tests use arbitrary column names and are not Frazer fixtures. No credentials or guessed source timestamps are used. Malformed CSV, conflicting reserved identity columns and ambiguous identity-role assignments fail closed.

Schema changes are additive: optional identity_decisions on jobs, BridgeIdentityReview audit records, and projection policy on external links. Legacy links default to their prior update behavior; reviewed links explicitly preserve current values. No production migration is run automatically.

## Reproduce the synthetic preview

Use an isolated development copy with the existing Python/frontend dependencies installed. From the repository root, run `python scripts/preview_dealer_bridge.py --port 8303`. The preview creates fresh temporary graph/authentication storage on each launch and binds only to loopback; it does not load a dealer graph.

In a second terminal, from `frontend/` in that development copy, set `NEXT_PUBLIC_API_URL` to `http://127.0.0.1:8303` and `DEPLOYMENT_MODE` to `application` before starting `npm run dev -- --webpack --hostname 127.0.0.1 --port 3303`. These options were verified against the installed Next CLI. Setting the API URL before startup ensures the browser bundle uses the disposable backend.

Open `http://127.0.0.1:3303/`, sign in with the synthetic credentials documented at the top of `scripts/preview_dealer_bridge.py`, then open `/data-bridge`. The second synthetic administrator supports separate-approver testing. `/qa-info` on port 8303 identifies the synthetic backend.

The fixture includes approved customer/account/payment/journal mappings, an identity-review case, a native-field difference, a local read connector and a disabled local Chrono sink. Its vendor entry explicitly awaits an authorized sample. The preview registers only login and Bridge endpoints; unrelated workspace widgets are outside its scope. Stop both terminals with Ctrl+C after review. No live vendor, AI service or remote temporal engine is needed for this fixture. `test_bridge_pilot_workflow.py` separately exercises the synthetic multi-system/restart path against real temporary persistence.

## Limitations and deployment checks

This is a bounded, single-process foundation. Read-only collection and Chrono outbox workers are integrated into app startup/shutdown but remain inert without trusted bindings and explicit policy. Bounded SFTP and fixed-endpoint HTTPS export transports are implemented and locally tested. The signed NXTDeal ADF gateway stages creation events behind explicit human policy. General vendor XML ingestion, native vendor webhook formats and authentication flows, automated identity merges, shared-hosting membership resolution and production write dispatch remain unimplemented. SDK contracts are extension points, not access claims.

Bridge mutations are serialized and in-memory changes roll back if persistence fails. The JSON repository now serializes saves through a process-local persistence guard and encodes detached snapshots. Bridge mutations hold that same guard through commit/rollback so another save cannot persist tentative Bridge changes. Legacy direct in-memory mutations/readers do not share this guard automatically: this is not database-level cross-module transactional isolation, and separate processes/repositories writing one file remain unsupported. Avoid concurrent imports/legacy writes in a production pilot until repository-wide transactions and job locking exist. Staging retains mapped source values and identity/time values in administrator-accessible graph records: retention/purge policy, encryption at rest and scalable queues remain deployment work. The shared legacy registry falls back to a workspace-scoped graph lookup for unindexed VINs, under the persistence guard. Unique imported vehicles remain reachable by native lead/service intake; duplicate VIN creation is rejected, and ambiguous optional links are not guessed. Imported lead phone aliases remain available to native consumers; explicit lead-to-customer conversion also preserves older canonical-only phone values without overriding an intentional native blank. Customer/lead/vendor-ID registries are not automatically re-indexed because those identifiers are source-scoped. Legacy direct import routes otherwise retain their previous behavior. Rollback of an activated import requires a reviewed restore/correction; there is no delete/undo endpoint.

Verification checkpoint: **11,975 full backend tests passed**, one existing Starlette/httpx warning, including the synthetic multi-system pilot and native finance/consent boundaries. Full frontend TypeScript and Bridge-page lint passed. Expanded lint also checked the shared Command Center and found four pre-existing React-hook/purity errors, reproduced from `HEAD`; this feature does not claim that baseline lint is clean. The final isolated production build passed compilation, TypeScript and all 37 static pages, including row paging. The full regression includes 388 Bridge-specific cases. See `DEALER_BRIDGE_BUILD_SESSION.md` for detailed verification evidence. Browser QA succeeded against isolated synthetic storage: identity link/separation, reconciled activation, collection, checkpoint advancement, mapping replacement, malformed UTF-8 rejection, exact-header/connected-schema suggestions, historical backfill completion, current-value preservation, lineage lookup, nonpersistent simulation, reviewed code translation, approval receipts, local sink acknowledgments, and 60-row simulation/staged paging with issue filtering and fresh-validation reset. Screenshots are under `dealeros-next/previews/dealer-bridge-*.jpg`. No production deployment occurred.

Validation: bridge lifecycle/auth/identity/history/money/rollback/persistence tests plus adjacent agent, integrations, data connections, graph repository and route-protection suites; frontend scoped type checking and lint. Tests use isolated temporary graph storage. A test-only dummy AI key is needed for existing app-import initialization; the bridge itself requires no AI key. No vendor traffic is part of these checks.

## Per-system setup planning

`bridge_catalog.py` supplies searchable software aliases, category labels and explicitly planned record types, including the expanded independent/BHPH and adjacent-stack list. Each system card has an optional Connection setup details editor. `bridge_onboarding.py` stores a bounded product version, deployment type, selected canonical kinds and dealer-reported evidence states. Updates require an interactive administrator, use revision checks to prevent overwriting another editor, and are audited with the existing rollback mechanism. Existing systems need no migration: reading missing details returns defaults without writing.

GET/POST `/dealer-bridge/systems/{id}/onboarding` reads or replaces this planning record. POST requires the current `revision` and the complete `details` object. The seven evidence keys cover authorization, documentation, sample export, stable IDs, source timestamps, relationship keys and independent totals. States are unknown/requested/available/not_applicable. These are statements to review, not verified approvals. They do not change runtime bindings, collection schedules, mappings, jobs, native records or write permissions. Do not put credentials or customer data in these fields. Agents may read setup details but cannot record human evidence through this endpoint.

## Flat JSON file intake

Discovery, mapping simulation and import staging accept optional `file_format: "json"`; omission keeps CSV behavior. JSON must be an array of 1–1,000 flat objects with the same property names, up to 100 properties and 1 MB UTF-8. Values are strings, numeric lexemes preserved without float conversion, or null (normalized to an empty value). Nested values and booleans require a dedicated adapter. Source IDs and timezone-aware timestamps use the approved mapping profile. File hashes refer to the original JSON; omitted values are discarded as for CSV. Human approval and activation requirements are unchanged. The browser offers explicit CSV/flat JSON selectors for discovery and import. Changing formats clears the selected file and simulation; the receipt displays the original format. Synthetic browser verification covered discovery through activation and retained source history.

## Tab-delimited exports

The same discovery, simulation and staging APIs accept `file_format: "tsv"`. Browser selectors offer TSV explicitly. Quoted tabs/newlines are supported; source column names and identity profiles remain exact. Limits are 1 MB, 1,000 rows and 100 columns. No delimiter detection or schema inference is performed. File fingerprints retain the original TSV text and activation still requires approved mappings and a human administrator. Connected adapter pages continue using the internal CSV serialization contract.

## Explicit staging-copy retention

`bridge_retention.py` provides GET/POST `/dealer-bridge/imports/{job_id}/payload-cleanup`. GET returns eligibility, retained row counts and a review token without row values. POST accepts that token plus an 8–500 character reason and requires an interactive administrator. Only cancelled or activated jobs qualify; activated jobs additionally require a consistent recorded receipt tied to their mapping/content/source fingerprints. Older imports without receipts remain ineligible.

Cleanup removes only the job's `rows` and cached `preview`, records actor/time/counts/reason, and adds an audit entry in the existing rollback-protected mutation. Job status, sync checkpoint references, source fingerprints, activation receipt, canonical records, external IDs and source observations remain. It cannot undo an import, erase all personal data or remove backup copies. Failed saves restore the payload; repeated successful requests are idempotent. No automatic retention schedule or production cleanup is enabled. Finished import cards expose an explicit cleanup review with retained counts, receipt eligibility, a required reason and an acknowledgment checkbox. Refreshing the review or changing the reason clears acknowledgment. Use the dealership's retention requirements before invoking it.

## ADF creation-event workflow

`/data-bridge/events` provides an administrator workspace for the bounded ADF identity subset. It supports exact provider-namespace profile proposals, separate human approval/revocation, authorized-file simulation/staging, paginated event jobs, current-graph validation, explicit identity link/keep-separate/withdrawal, activation acknowledgment and source-history/receipt inspection. `bridge_event_profiles.py`, `bridge_event_imports.py` and the isolated `bridge_adapters/adf.py` implement this path. It is not a full ADF schema implementation or a live lead receiver.

Creation time remains creation time. Provider-scoped event IDs never enter modification-time snapshot collection. Canonical Lead creation or human-linked history is atomic with namespace-scoped identity links, immutable observations and approval evidence. Linked history preserves current lead values. Source/candidate/profile changes require fresh validation or review. Unselected XML values are not stored. Imported lead facts grant no communication consent. Chrono uses the existing disabled-by-default authorized outbox, with explicit creation-time/namespace provenance.

Browser verification used synthetic data only: different-admin profile approval, simulation/stage/validate/activate/history and blocked matching lead -> human link -> history-only activation passed. Original source names remained visible beside preserved current dealership names. The adapter SDK document describes supported fields, parser limits, API routes and remaining full-format/live-transport work.

System Map next-step guidance includes scoped event profiles and staged/blocked/validated event batches, alongside snapshot imports. Successful event activation updates source health and last-success time. These summaries expose no staged lead values and never grant live access. Disk reload tests cover event approval, human identity links, receipts, replay, cancellation and revocation.


Snapshot receipt integrity is checked against the owning import and its preserved
review/activation metadata, not just the receipt checksum. Before terminal payload
cleanup, the retained staging rows and preview must also match their recorded
hashes. After reviewed cleanup, the receipt remains verifiable against preserved
metadata and the cleanup marker. This is consistency evidence, not a cryptographic
signature or proof against a privileged writer changing the stored graph.


## Implementation boundary review (October 4 evening)

| Requested foundation | Current implementation | Remaining delivery work |
| --- | --- | --- |
| Canonical model, source IDs and history | Vendor-neutral contracts, scoped external identities, snapshot and creation-event observations, legacy projection | Validate each real product's source meanings and historical coverage |
| Connector SDK and registry | Capability validation, unavailable vendor stubs, per-system runtime bindings, scoped credential broker, bounded local/SFTP/HTTPS export readers and signed ADF staging | Authorized native adapters, deployed secret-store provider, vendor certification where required |
| Staging, mapping and deduplication | CSV/TSV/flat JSON, constrained ADF events, immutable proposals, simulation, quarantine, explicit identity review, borrower advisories and receipts | Additional vendor envelopes and event shapes based on authorized samples |
| Temporal delivery | Local observations and opt-in Chrono outbox with idempotent delivery contract | An operator-authorized real sink and deployment-specific delivery verification |
| Sync and recovery | Durable leases/checkpoints, retry classification, separate history streams, reviewed mapping transitions and replay recovery | Vendor pagination, expiring cursors, deletion/correction and source-completeness contracts |
| Onboarding/System Map | Requested software catalog and aliases, category onboarding, discovery, review queues, health and next-step guidance | Validate the pilot dealer's actual product versions and adjacent system scopes |
| Agent boundary and write-back | Provider-neutral declarative proposals/tests; human approval/activation; blocked write proposals | No write executor is shipped; any future operation needs its own authorization and reconciliation design |
| Offline pilot preparation | Single-export, captured-page and ordered multi-file checkers; synthetic BHPH/accounting fixtures with reference and reconciliation checks | Dealer-authorized samples and independent source totals; disposable synthetic approvals never transfer to production |
| Persistence/migrations | Additive graph schema marker, scoped mutation rollback, snapshot flush before replacement and real reload tests | No relational database migration or shared multi-process tenant platform is claimed |

The graph schema marker remains version 1 because these additions introduce new
records and optional evidence fields without rewriting stored canonical data.
Approval receipts are never reconstructed from today's mapping. Older activated
pending pages missing checkpoint evidence use the explicit reviewed replay path;
previously accepted source positions remain intact. No production migration has
been run by this build session.

Catalog coverage and local fixture tests do not constitute live integrations.
The next concrete delivery milestone remains one authorized Frazer export pilot:
verify stable source IDs and timestamp meanings, compare customer/inventory facts,
then establish BHPH account/payment definitions and independent source totals.
Fixed-path SFTP and fixed-endpoint HTTPS snapshot adapters pass mocked-client and
real loopback protocol tests. HTTPS enforces verified TLS and does not follow
redirects; both transports use explicit credential grants and human-reviewed
staging. An authorized dealer pilot and deployment verification remain outstanding. The NXTDeal signed ADF gateway is implemented and locally tested;
native vendor webhook formats, mailbox delivery, broad XML support, vendor OAuth/secret
store deployment and live write-back remain separate transport or authorization
work. The file reader is a bounded snapshot collector, not a
replacement for a durable event feed.


Before simulation, **Inspect export structure** provides a data-minimal preflight:
missing mapped/source-identity columns, blank-value counts by mapped field,
unmapped headers and added/removed columns versus the latest activated import
using the same mapping. The comparison is unavailable when the retained receipt
or schema evidence is inconsistent. This read-only check accepts CSV, TSV and flat
JSON through `POST /dealer-bridge/mappings/{id}/preflight`; it never persists rows,
changes mappings or substitutes for value validation and financial reconciliation.
Reports disappear when the selected file contents, format or mapping changes.


System Map's **Source activity history** reads retained actions through
`GET /dealer-bridge/systems/{id}/activity?limit=25&before_id=...` (maximum 100 per
page). It shows actor, recorded credential type, action, time and target record,
with source/workspace checks across typed parent references. Legacy principal
values remain unknown. It omits row values, decision reasons, raw cursors and
global Chrono policy actions. Missing targets cannot be attributed and are excluded;
the feed is not a tamper-proof or comprehensive application audit log.


Optional organization relationships preserve multi-rooftop source structure:
Location.dealer_id references Dealer; Customer.household_id references Household;
and Customer, Employee, Vehicle, Deal, ServiceRecord and Appointment may reference
a Location through location_id. External IDs require the explicitly selected
source object and a previously imported reference of the correct canonical type.
Import-order guidance includes these dependencies. Discovery never invents the
reference namespace. Existing mappings do not change, and no group, location or
household is inferred from names. These relationships are not tenant isolation,
employee provisioning, access grants or automatic household merging.


Creation-event batches now expose the same explicit staging-copy cleanup review
through GET/POST `/event-imports/{job_id}/payload-cleanup` and the event review UI.
Only cancelled or activated batches qualify; activated batches require consistent
owning-job receipt evidence, staged rows and validation preview. The human-only
POST requires the current review token and a recorded reason. The UI additionally
requires an acknowledgment of permanent staging-copy removal.

Cleanup removes mapped staging rows and cached previews, retaining source
observations, lead records, identity reviews, export fingerprints, activation
receipts and original batch counts. Event lineage remains available through its
exact source namespace and external ID. Receipt observation buttons use GET `/event-observations/{event_id}` to retrieve
retained history even after staging rows have been removed. This lookup verifies
the workspace, Bridge creation-event origin and source identity before returning
lineage. Cleanup does not delete source history or undo an import.
As with snapshot cleanup, consistency checks are not signatures against a graph
writer, and there is no automatic retention schedule or complete erasure claim.


### Resolving related records across import batches

Validation and simulation return `reference_issues` for unresolved relationships.
Each issue names the canonical field and expected kind; source-ID mappings also
name the referenced object within the same configured source. Direct canonical-ID
issues instead require an existing compatible workspace record. Raw reference IDs
are not added to these diagnostic records. Import and activate the missing parent
records, then explicitly validate the original staged batch again. This supports
customer/contract/account/payment dependencies without automatic batch activation
or cross-source identity assumptions. Existing import-order guidance remains an
advisory plan, not a workflow executor.


Employee canonical records are directory observations. Allowed fields are names,
department and reviewed location reference; they do not include credentials,
roles, permissions, MFA settings or tenant membership. A source department named
ADMIN remains a department value. Employee source IDs are external identities,
not login identifiers. Importing or updating them never provisions or modifies
credential-store accounts. The Employee mapping form makes this distinction
explicit. Password columns outside the approved mapping are discarded with other
unselected values.


## Combined import review queue

Open `/data-bridge/review` from System Map to review pending snapshot and ADF
creation-event batches together. Filter by source system, status or import type;
open a batch to use its existing validation, identity review and human activation
controls. The queue itself cannot approve, activate or call external systems.

`GET /dealer-bridge/review-queue` accepts `system_id`, `status` (default `pending`),
`kind` (`all`, `snapshot`, `event`), `limit` (1-100, default 25), and a returned
`before_id` cursor. Pending includes staged, validated and blocked batches. The
response contains scoped source labels, job metadata and live counts, never source
row values. Cursor scope includes source and import type; a status change on the
anchor does not invalidate paging. Refresh starts at the newest batches. Counts
are live, not a frozen snapshot. Cleaned terminal jobs retain their recorded source
row count and cleanup marker. This is bounded response paging over the existing
in-memory ledger, not an indexed database query or multi-process queue service.

The review page keeps source, status and import type in its URL. Returning from a
batch preserves those filters, and each System Map card links directly to its
pending review queue. These URLs contain source/job identifiers, not row values.


## Chrono delivery review and recovery

`/data-bridge/chrono` provides paginated review of recorded delivery attempts for
the currently authorized destination. It can filter unacknowledged, blocked,
retrying, in-flight and delivered receipts. It does not hide older failures behind
the legacy 200-receipt response window. The existing System Map summary remains
available, with a link to the complete review view.

`GET /dealer-bridge/chrono/receipt-queue` accepts `status`, `limit` (1-100, default
25), and the returned `before_id`. Ordering follows immutable observation import
time and event ID, so retrying an observation does not move it between pages.
Cursor scope is the selected destination name/revision and workspace. Receipts
without consistent observation ownership or deterministic receipt identity are
excluded and counted for operator review. No source values or lease tokens are
returned. Unattempted observations have no delivery receipt and are not listed.
The existing overview includes those observations in its pending count.

Retry controls require a reason, current human authorization, an enabled matching
destination and no active delivery lease. The browser sends the reviewed receipt
ID with each retry. If the selected destination has changed, the API rejects that
stale action. The optional receipt ID preserves compatibility for existing API
callers; new callers should always supply it. Queueing a retry may allow the
already-authorized worker to deliver the observation. It does not create a new
observation, approve a destination or replay acknowledged data. This remains a
local-ledger foundation; a real sink and deployment verification are outstanding.


Collection settings now distinguish stopping a schedule from reviewing a replaced
connector. Disabling preserves the prior revision/environment approval. A changed
connector remains blocked until an administrator reviews the displayed revision,
environment and source-object scope and explicitly saves that exact configuration.
The browser sends those reviewed values so a concurrent replacement cannot be
approved through a stale screen. The adapter SDK documents the additional fields
for reconfiguration API callers.


### Loan/contract customer review advisories

A LoanAccount referencing a contract whose current canonical customer differs
from the incoming account customer includes a `contract_customer_differs` review
advisory. It asks the administrator to review borrower roles, identity links and
historical timing. This does not infer co-borrower semantics, declare either source
wrong, rewrite the relationship, or block otherwise valid observations. Unknown
contract customer values are not guessed. The warning appears in simulation and
staged review, including the review-issues filter. A change affecting the advisory
after validation requires fresh validation before activation. Structured confidence
remains a validation signal, not proof of borrower identity.

Captured-page conformance reports summarize advisory counts/codes without customer
or contract IDs and return issues_found for human review. This is a review outcome,
not a malformed-page classification.

Import summaries expose `review_advisory_rows` separately from financial status.
An advisory hash binds the contract/customer pair used during review, so changing
that relationship requires fresh validation even when advisory wording is unchanged.
The hash is an integrity comparison, not a signature or independent source proof.


### Storage failure responses

A filesystem save failure is distinguished from application authorization after
Bridge rollback. API callers receive HTTP503 with a bounded instruction to check
storage, reload current state and review it before retrying; OS paths and volume
diagnostics are not returned. A filesystem PermissionError is not reported as a
human-access403. Core callers retain the OSError contract through
`bridge_storage.PersistenceUnavailable`. Human authorization remains403, and a
concurrent record change that prevents clean rollback remains409 for review.
There is no automatic retry of an approval or activation request.

Snapshot cleanup review tokens also bind the activation receipt, source evidence
and mapping hash, matching the event-cleanup evidence boundary. An operator
correction invalidates an earlier cleanup review even if the corrected receipt
is internally consistent. Old open cleanup dialogs must reload before submission.
This is a stale-review check, not protection against a privileged graph writer.


### Source-version timestamp precision

New snapshot source `modified_at` values, captured SDK pages and ADF creation-event
contracts reject nonzero fractional digits beyond microsecond precision. Python's
datetime parser otherwise truncates those digits, which could collapse distinct
source versions into one timestamp. Additional trailing zeros are accepted because
they lose no information. Raw accepted source timestamp strings remain preserved.
ADF discovery reports `source_time_precision_requires_adapter` for this case.

This guard applies at new source intake, not as a rewrite of saved history or a
change to pinned canonical field transformations. The retained timestamp parser
keeps its existing behavior for compatibility; previously staged or retained
high-precision data is not retroactively repaired. A source with finer precision
needs a separately designed version/identity contract. Do not round or invent
source times simply to pass intake; verify the actual product's precision first.

Intake also rejects fractional timezone offsets that the installed datetime
parser collapses to zero (for example, +00:00:00.5). Exactly represented offsets
remain accepted. This prevents a source instant from silently shifting to UTC.
