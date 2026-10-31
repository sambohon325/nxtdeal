# Dealer Data Bridge adapter SDK

This is the implementation contract for a new read-only vendor adapter. It does not grant vendor access. Obtain the dealer's authorization, authoritative vendor documentation, a permitted sandbox/export and any required certification before implementing real transport. The [connector plan](DEALER_BRIDGE_CONNECTOR_PLAN.md) records the current rollout order and access blockers.

## Boundaries and installation

- Keep vendor endpoints, response schemas, pagination rules and export-field names under `backend/core/bridge_adapters/<vendor>.py` or a vendor-specific package. Canonical domains remain in `bridge_contracts.py`.
- Declare only locally implemented capabilities in a bounded collection, normally a `frozenset`. Supported names are `authenticate`, `discover`, `schema`, `history`, `sync`, `subscribe`, `write`, `reconcile`, and `health`. An inherited unavailable method does not count as implemented.
- `register_connector(vendor, adapter)` registers a trusted implementation with the catalog. It does not authenticate a dealership, bind a system or grant write permission. Registry instances must not hold shared mutable dealer credentials.
- An operator resolves credentials on the server and creates a **distinct adapter instance for each configured system**. After authenticating the intended dealer account, call `bridge_runtime.bind(system_id, adapter, revision=..., objects=[...])` from trusted startup configuration. No Bridge HTTP route accepts adapter code, endpoints, credentials or secret references.
- A bound collector needs `sync`, `history`, or both. Object names are an explicit allowlist, not a result inferred from a model. Capability inspection never calls a vendor method. Rebinding an active instance/scope under the same revision is rejected; an identical binding is idempotent.
- The revision identifies the implementation **and the authorized account/scope configuration**. Change it when those meanings change. A restart can reconstruct the same reviewed binding, so startup code is responsible for preserving that identity; revision text must not disguise a changed dealer account. Secret rotation that preserves the same account/scope must not expose the secret in revision text.

Credentials must remain limited to read access wherever the vendor supports that distinction. Do not guess OAuth scopes or certification rules. Authentication/refresh failures are reported through the safe failure contract below; agents cannot renew or broaden access through a mapping proposal.

## Page contract

Both `sync(object_type, cursor)` and `history(object_type, cursor)` return `SyncPage` from `core.bridge_contracts`:

```python
from core.bridge_contracts import SourceRecord, SyncPage

# Synthetic contract example only; these are not any vendor's field names.
page = SyncPage(
    records=(SourceRecord(
        object_type="loan_accounts",
        external_id="fixture-account-1",
        modified_at="2026-09-01T13:00:00Z",
        values={
            "customer_reference": "fixture-customer-1",
            "outstanding_amount": "1234.56",
            "source_currency": "USD",
        },
    ),),
    cursor="opaque-fixture-next-position",
    complete=False,
)
```

The adapter translates vendor payload shape into bounded flat source columns. An approved declarative mapping translates those columns into canonical fields. No executable transformation code is accepted through the mapping API.

| Element | Requirement |
| --- | --- |
| Object | Exact configured source-object name; the record must match the requested object. |
| External ID | Nonempty string, at most 500 characters, no surrounding whitespace. Preserve stable vendor identity and its source namespace. Never use a display name, changing balance or row position as identity. |
| Modified time | Actual source timestamp with timezone. Do not substitute ingestion time for missing history or guess the dealer's timezone. |
| Values | Flat scalar columns; at most 100 columns with bounded names. Nested vendor structures must be deliberately flattened inside the adapter. |
| Money | Decimal strings or integers, never binary floats or booleans. Preserve the source currency; no implicit currency or conversion. Supported fixed-point precision is six decimal places and 24 integer magnitude digits per value. |
| Page | A tuple of at most 1,000 records; resulting UTF-8 staging CSV must fit within 1 MB. A single value is bounded to 100,000 characters. |
| Cursor | Opaque string at most 2,048 characters or `None`. An incomplete page must provide a changed next cursor. Never include a credential in a cursor. |
| Complete | A real boolean. For history it marks the finite backfill boundary; for ongoing sync it ends the current polling cycle. |

One page must not contain multiple versions of the same external identity. Split those versions into ordered pages/jobs. Older accepted versions retain observations while leaving the newer projection intact. Conflicting values at the same source timestamp are quarantined; do not silently create a new timestamp to get around this check. Deletions and same-time corrections require a separate reviewed contract; they are not inferred from a missing row or an empty page.

History and ongoing sync use independent durable cursors, but share the external-ID namespace. A nonempty page is staged, then waits for human validation and activation. Only an activated page advances its stream's cursor. A final history page completes the backfill after activation and disables its schedule. A final empty history page may complete immediately. Generic retry does not restart completed history from the beginning; replay needs a separate reviewed plan. Mapping replacement preserves terminal completion, even when the final source cursor is None, and never restarts a completed backfill.

All adapter IO happens outside the Bridge graph lock. Implement bounded connection/read timeouts and bounded pagination within each call. Do not launch an untracked background loop inside an adapter. The host owns scheduling, leases, retry counters and checkpoints. The collection lease lasts 300 seconds; late replies cannot stage data or update retries after expiry. The next attempt can reclaim the expired lease. Keep adapter timeouts comfortably below that limit. Page expansion and CSV serialization enforce the UTF-8 limit incrementally, including quote escaping. A worker restart or lease recovery may repeat a read, so reads must be safe to repeat.

## Schema discovery

An implemented `schema(object_type)` returns a list or tuple of **column names only**, with 1–100 unique bounded strings. It must not return raw vendor metadata, sample customer rows, credential-bearing URLs or account secrets. Connected inspection is limited to the binding's object allowlist and schema capability. A pause, unbind or replacement during IO discards the result.

The UI matches neutral header names to optional draft suggestions. Source identity roles, timestamp semantics and relationship namespaces still require review. A schema result never approves a mapping. The other SDK methods are extension points: there is no automatic subscription installation, reconciliation action or write dispatch merely because an adapter declares the method.

## Failure and retry contract

Use `core.bridge_sync.ConnectorFailure` for classified failures:

```python
from core.bridge_sync import ConnectorFailure

# The adapter has already parsed a documented vendor rate-limit response.
raise ConnectorFailure(code="rate_limited", retry_after_seconds=120)
```

Allowed codes are `unavailable`, `rate_limited`, `authentication_required`, `permission_denied`, and `source_changed`. Access, permission and source-change codes always stop for review. Optional retry delay is an integer from 1 to 86,400 seconds; the collector honors the larger of that delay and its own backoff. Temporary failures stop after five attempts. A human can request a reviewed retry from the saved position. Standard timeout/connection exceptions are also treated as temporary; unknown contract failures stop for review.

Do not put vendor responses, tokens, customer details, raw request URLs or credentials into errors. Public state uses fixed messages and codes. A production adapter may need an operator diagnostic channel with its own redaction/access policy; this foundation does not store raw transport errors in the graph.

## Staging and financial meaning

### Explicit health probes

An adapter declaring `health` returns a dictionary with a `status` from `ready`, `degraded`, `unavailable`, `authentication_required`, `permission_denied`, `rate_limited`, or `source_changed`. Other response fields are discarded. The administrator's **Check connector health** action calls this method only on the dealer's trusted binding, outside graph/persistence locks. Results carry the checked time and binding revision; prior-revision results are labeled accordingly. A 60-second lease prevents overlapping probes and rejects late results. Adapters must set a shorter bounded transport timeout. Pause/unbind/rebind in flight discards the result. No probe authenticates, approves, enables collection or writes.

### Mapping simulations and BHPH terms

POST `/dealer-bridge/mappings/{id}/test` accepts a bounded CSV `content` and optional source `expectations`. It runs the same parser, transformation, identity and reconciliation checks without creating a job, approval or audit record. Simulated rows are returned to the administrator/authorized agent and not retained. Later staging and activation require fresh validation; a passing simulation is not approval.

Canonical contract terms include principal, down payment, installment amount, currency, term months and annual percentage rate (percentage points, not a fraction). Account facts include past-due amount, scheduled payment and lifecycle/due times. Payment/schedule principal, interest and fee allocations are exact decimals; when all three are present they must sum to the amount. Missing allocations are not assumed to be zero. A payment reversal link must point to an imported payment on the same account and cannot point to itself. These fields preserve source facts; they do not calculate regulatory disclosures, eligibility, balances or operational reversals.

New jobs retain only mapped columns plus identity/time values. For connector reads, export/schema hashes refer to the normalized staging representation, not the original vendor wire bytes. Omitted values are not archived. Preserve any separately required source export only in the dealer's approved storage.

Import customers before contracts/accounts, then schedules/payments/collections that reference them. External-reference mappings are scoped to the same workspace and system. For BHPH adapters, verify whether balances are as-of snapshots and how reversals, returned payments, adjustments, delinquency and repossession statuses are represented. Do not derive or overwrite a balance from payment rows without a separate approved accounting model.

JournalEntry represents an observed source journal line. Map verified journal IDs and debit/credit meanings explicitly; sided amounts are nonnegative. `ledger_account_id` may use a same-system external reference to AccountingAccount and must agree with its code/currency. Complete-journal exports can opt into `balanced_journals` reconciliation, which compares debit/credit totals separately for each journal and currency. Do not enable that check on partial pages or infer a complete accounting period from a balanced extract.

Imported Payment, FinanceContract, Deal, Campaign and Consent facts have observation-only storage types. Source consent never automatically grants message-send permission; later native consent review is required when imported evidence is latest. They do not create native cash receipts, post journal entries, run collections or initiate repossession. Independent source totals can be supplied for review, but matching an export total does not certify the source accounting ledger.

## Verification before real access

Keep sanitized, synthetic or explicitly authorized fixture tests next to the adapter. Cover at least:

1. Source account/object isolation, actual ID/time semantics and unknown schema fields.
2. Pagination, cursor continuity, repeated reads, empty/final pages and history completion.
3. Missing/duplicate columns, same-time conflicts, malformed values and exact currency totals.
4. Credential expiry, permission loss, rate limits, bounded timeouts and sanitized errors.
5. Pause/rebind while reading, cancelled pages, persistence failure and restart recovery.
6. Existing read-only/human-review/write-block invariants.

The core reference tests are `test_bridge_adapter_contracts.py`, `test_bridge_schema_discovery.py`, `test_bridge_sync.py`, `test_bridge_history_collection.py`, `test_bridge_sync_recovery.py`, `test_bridge_restart.py`, and `test_bridge_currency.py`. Run from `backend/`; the test configuration uses disposable storage. Synthetic fixture success must not be labeled vendor certification.

No real vendor adapter is installed by this document. The Frazer module remains an unverified dealer-supplied CSV profile. Live connector rollout, production secret provisioning, approved Chrono destination installation and any write-back workflow remain separate deployment work.

## Reviewed value translations

Transformation v3 adds finite `lookup` rules. Synthetic example only:

```json
{"status": {"source": "fixture_status", "transform": "lookup", "values": {"A": "active", "C": "closed"}}}
```

Allowed targets are advertised as `lookup_fields` by System Map. Values are case-sensitive after source whitespace trimming; an unmapped nonblank code quarantines the row and blocks activation. Blanks remain omitted. Tables have 1–100 bounded text pairs and no fallback or executable expressions. Money, identity and timestamps keep their existing dedicated contracts. The full lookup is included in the approved mapping hash; old transformation versions never gain new semantics. Do not invent a vendor's code meanings: use authorized documentation and reviewed fixtures. Human approval remains required.

## Captured-page conformance checks

`core.bridge_conformance.verify_pages(actor, mapping_id, pages, initial_cursor=None)` is a Python SDK helper for authorized synthetic/sanitized fixtures. Pass 1–10 `SyncPage` objects, at most 1,000 records overall and 2 MB of serialized CSV overall. It invokes the same page serializer, mapping preparation and row preview used by collection. It never calls an adapter, authenticates, binds a runtime, stages an import, saves a graph or advances a cursor. Administrator authorization and workspace isolation still apply; proposed mappings may be tested by an authorized API/agent actor.

The report contains per-page counts, sanitized issue codes, schema fingerprints, the mapping hash and a fingerprint of successfully serialized pages (including hashed cursor values). It omits raw source values and raw cursors. Checks include repeated/cyclic incomplete-page cursors, pages following a completion flag, source contract failures, quarantined rows and contradictory mapped values for the same source identity/time across pages. Same-time replay and different-time history are allowed. Timestamps representing the same UTC instant compare as one source time.

Passing this helper proves only captured fixture behavior. It does not verify actual request-cursor use, source completeness, access, certification, timeout handling or credential rotation. Each page is checked against the current graph; earlier fixture pages are not simulated as activated, so dependent source objects must already exist for relationship checks. The fingerprint is not a signature or proof of source accuracy. Keep the existing runtime/restart/permission tests and real authorized sample review as separate acceptance requirements.

```python
from core.bridge_conformance import verify_pages
from core.bridge_contracts import SourceRecord, SyncPage

# Synthetic fixture; use the mapping's actual source-object name and columns.
pages = [SyncPage((SourceRecord("customers", "fixture-1", "2026-10-04T19:00:00Z",
                              {"name": "Synthetic", "email": "fixture@example.invalid"}),),
                  None, True)]
report = verify_pages(authorized_actor, proposed_mapping_id, pages)
assert report["status"] == "fixture_checks_passed"
```

## ADF structure discovery

`POST /dealer-bridge/systems/{system_id}/discover-adf` accepts UTF-8 XML `content` for an administrator in that system's workspace. Authorized API principals can inspect it because this is non-persistent discovery. The isolated `bridge_adapters/adf.py` adapter returns original byte count/hash, prospect counts, contact/vehicle/ID counts and bounded issue codes. It never returns lead values, chooses among repeated IDs/contacts/vehicles, fabricates IDs, stages records or grants communication consent.

This is structure inspection, **not full ADF validation or an ADF importer**. It enforces 1 MB, 1,000 prospects, 20,000 elements, depth32, bounded attributes, unqualified elements, and UTF-8 declarations. DTDs and entity declarations are rejected before expansion; no external resource is resolved. Missing identity, ambiguous repeated structures and missing/naive creation times become review evidence. An empty issue list does not establish full ADF conformance or import readiness.

The [ADF 1.0 specification](https://adfxml.info/adf_spec.pdf) defines requestdate as lead creation time and permits provider-assigned IDs and repeated structures. The report explicitly records `requestdate: lead_created_at` and `modified_at: not_provided`. Subsequent work must add an approved provider-specific identity profile and explicit creation-event semantics before staging; simply renaming requestdate to modified_at would lose meaning. No email receiver, webhook, vendor credentials or live provider access is included. The ordinary import API deliberately rejects `file_format: adf` until that reviewed ingestion path exists.

Each System Map card exposes this inspection under **Inspect an ADF lead file**. The browser preserves UTF-8 BOM bytes for the source fingerprint, clears previous reports when choosing another file, and exposes no import/approval control for ADF.

### Creation-event drafts

`SourceEvent` is a separate SDK draft envelope with explicit `source_namespace`, `external_id`, `occurred_at` and `time_semantics` (`created` or `occurred`). It has no `modified_at`; the snapshot collector rejects it. `bridge_adapters.adf.creation_events(content, id_source="Exact provider source")` extracts a strict subset using exactly one matching `id/@source`, one timezone-aware requestdate and one customer contact. It retains selected first/last/full-name, email and phone fields as source values. Full names are not split; repeated selected fields fail; resend never invents a modification time. Vehicles, vendor details, finance, comments and communication consent are not mapped by this subset.

This helper is for offline adapter development, not an approved production mapping. It returns sensitive draft values to the caller, unlike the value-free discovery endpoint; keep them in authorized test handling. No API exposes these drafts, no graph writes or approval occur, and no connector capability is registered. Follow-on ingestion must bind the namespace/selection/field profile into immutable human approval, retain event-time semantics in Chrono evidence and define creation-event projection before activation. Existing SourceRecord and modification-time imports remain unchanged.

### Reviewed event profiles

`bridge_event_profiles.py` adds additive `BridgeEventProfile` graph records. `POST /dealer-bridge/event-profiles` accepts system_id, exact id_source and selected Lead identity field mappings. The profile hash binds adapter version, provider namespace, fields, transformation version, creation semantics and `create_or_history_only` projection policy. Existing snapshot mapping hashes and schema marker remain unchanged; no existing records are migrated or reinterpreted.

List profiles with `GET /systems/{system_id}/event-profiles`; propose/test are available to authorized administrator API principals. `/event-profiles/{id}/approve` requires a different interactive administrator. `/revoke` takes a reason and requires an interactive administrator. `/test` takes ADF content and returns normalized created-event times, mapped values or quarantined issue codes without saving records. Profile changes and revocations invalidate simulation. Mutations use existing record-level persistence rollback and audit.

Approval approves the extraction/mapping profile; event batches still require staging, validation and separate interactive activation. Simulation does not resolve identities or assert a canonical projection. The `create_or_history_only` policy creates unmatched leads and preserves existing values on replay. Candidate matches block until explicit identity review; linking preserves existing canonical values and adds source history only. No automatic existing-record update is implemented. Do not treat ready simulation rows as authorization to import or send messages.

### Event review queue

`POST /event-imports` accepts profile_id and ADF content. `GET /event-imports/{id}` returns scoped staging/report evidence; `/validate` refreshes the current identity/conflict preview; `/cancel` requires a human and a reason. BridgeEventJob stores only mapped event values plus source ID/namespace/time, original file evidence and integrity hashes. These additive records do not enter existing snapshot collection. Identical source replays are marked duplicate; contradictory creations and possible existing Lead email/phone matches block the batch. Phone punctuation normalization is candidate detection only, not identity proof. No automatic merge or canonical update occurs. Human activation is available at `/event-imports/{id}/activate`; candidate matches require an explicit human identity decision before validation and activation.

### Event activation and Chrono

Activation requires a separately approved immutable profile, validated batch, unchanged mapped rows/source evidence and fresh graph preview, an unpaused source and an interactive administrator. It atomically creates unmatched Lead identities, separate namespace-scoped BridgeEventExternalID links, SourceObservation events and a checksummed approval receipt. Replay preserves canonical edits and produces no new observation. Conflicting creation facts and unresolved identity matches remain blocked. Save failure rolls back records and receipts. No messaging consent or outbound vendor write is created.

Creation observations use the real source time and a distinct import time. Chrono envelope provenance includes `source_time_semantics: created` and `source_namespace`; no creation time is placed in a modified_at field. The generic Observation contract and existing snapshot envelopes are unchanged. Existing Chrono destination authorization, disabled-by-default delivery and idempotent receipts apply to these events as well.

### Event identity review

`POST /event-imports/{job}/rows/{row}/identity` requires an interactive administrator, action (`link` or `keep_separate`), target_id for a link, reason and candidate_signature from a fresh validation. The preview exposes only selected Lead identity fields for candidate comparison. Decisions bind the row hash, profile hash and current candidate records. A changed candidate set or record invalidates the review, including when all candidates disappear. Linking is restricted to an existing candidate and preserves every current canonical value; activation records source history and the decision in its receipt. Keeping separate is explicit, never inferred. `/identity/withdraw` retains audit evidence and invalidates validation. Finished imports cannot change decisions.

### Event lineage and queue listing

`GET /systems/{system_id}/event-imports?limit=25&before_id=...` lists up to100 scoped job summaries with a cursor from that system, never staged lead values. `GET /event-imports/{id}` exposes the authorized detailed report and receipt integrity. `POST /event-lineage` takes system_id, exact source_namespace and external_id; it verifies the namespace-scoped link and observation fingerprint, then separates original creation facts from current canonical values/legacy alias conflicts. It exposes source/import times, profile/job references and identity-review provenance. Changed approval receipts are reported as changed; inconsistent source event links are rejected. Creation profiles record one creation event per source identity; replay does not append fabricated history.

Event Lead identities remain Leads through the native Lead-to-Customer conversion workflow. The existing BECAME relationship and conversion fields connect the Customer; source IDs and original observations are not reassigned. Disk/replay and native conversion tests verify no duplicate creation and no rewriting of original event facts. SourceEvent draft text is UTF-8 validated and capped at1MB in aggregate.


### Operator-configured local export snapshot

`core.bridge_adapters.export_file.ExportFileConnector` reads one authorized,
absolute canonical file path supplied by trusted runtime configuration. It is
not registered as a live vendor integration. Bind it per system with a new
revision whenever the path, format, source object or source-column profile changes.
No HTTP endpoint accepts a file path. Supported formats are UTF-8 CSV, TSV and
flat JSON, under the existing 1 MB / 1,000-row limits. Source IDs and genuine
source-modification timestamps are required; creation-only exports belong in an
event adapter instead.

The adapter exposes sync, schema and health. A `sha256:<hex>` cursor fingerprints
original file bytes. Unchanged bytes produce an empty complete page; changed bytes
produce a complete snapshot for the ordinary staging, validation and human
activation workflow. The collector commits the fingerprint only after activation.
The job's existing export evidence hashes the collector-normalized CSV, while the
sync cursor hashes the original file. These are distinct artifacts and neither
hash proves vendor authenticity. No raw source file or local path is stored in the
job. Whitespace-only changes may therefore stage duplicate facts for review.

This reader is not a history feed, directory watcher, SFTP client, delete detector,
or financial reconciliation guarantee. It cannot recover replacements missed
between polls and never treats missing rows as deletions. Empty or malformed
exports block as source-contract failures. Missing files and detected concurrent
changes retry; permission failures block. Errors and health responses omit local
paths and source values. There are no write, subscribe or history capabilities.

Operators must control filesystem permissions, keep parent directories stable,
and publish completed exports using atomic replacement. File identity, size and
modification-time checks detect common concurrent changes, but are not a sandbox
against a malicious local writer. Use a durable vendor-specific delivery adapter
when every intervening update must be retained. No production path or binding is
configured by this implementation.


Collected page receipts include a `collection_page` envelope with version,
request/next cursor hashes and completion flag. Before accepting a nonempty
page's checkpoint (including during mapping replacement), the collector checks
this envelope against durable pending state and the owning activation receipt.
Reports never expose the raw cursor. Legacy pending activated pages lacking this
envelope require explicit operator recovery; do not fabricate evidence or edit
stored cursors to bypass the guard. Previously accepted checkpoints remain valid.


For an activated pending page that cannot be checkpointed, use
`GET /dealer-bridge/sync/{state_id}/replay-preview` and the human-only
`POST /dealer-bridge/sync/{state_id}/replay` with its review token and a reason.
System Map exposes the same reviewed recovery. This preserves the last accepted
cursor, imported records and prior job, and disables the schedule. Confirm the
source can still reread that accepted position before resuming; otherwise obtain
a reviewed replacement export. New pages still require validation and human
activation. Recovery creates an audit record and does not repair corrupt evidence,
undo imports, authorize a replacement binding or accept the discarded checkpoint.


### Standalone captured-page check

From the repository root, run:

```powershell
python scripts/check_bridge_adapter.py --mapping backend/tests/fixtures/bridge_conformance/mapping.json --pages backend/tests/fixtures/bridge_conformance/pages.json
```

The supplied files are synthetic neutral SDK fixtures, not a vendor schema. A
mapping file contains `kind`, `object_type`, `fields` and optional `source_columns`.
A page file contains `pages` and optional `initial_cursor`. Each page has exactly
`records`, `cursor`, `complete`; each record has exactly `object_type`, `external_id`,
`modified_at`, `values`. Preserve monetary decimals as strings. No executable
Python, provider names, credentials or runtime adapter definitions are accepted.

The checker runs only in a fresh process with an empty disposable graph. It does
not load the deployment's configured graph or credentials, approve a mapping,
activate an import, call a connector or simulate earlier-page activation. Root
mapping JSON is limited to 64 KB; captured JSON to 2 MB, 10 pages and 1,000 total
records, with the SDK's stricter per-page limits still applied. Duplicate JSON
properties and non-finite numbers are rejected. Reference-bearing records that
need existing canonical entities should also use an isolated end-to-end fixture
like the cross-stack pilot test; this command cannot certify those dependencies
against a production graph.

Standard output is a sanitized JSON report containing counts, hashes and issue
codes, never source values or raw cursor tokens. Exit code 0 means fixture checks
passed, 1 means review issues were found, and 2 means input/tool failure. A passing
report does not establish credentials, certification, source completeness or live
connector behavior. Keep captured source files in authorized local storage; they
may contain sensitive data even though the resulting report omits row values.


### Operator-declared binding environment

`bridge_runtime.bind(..., environment=...)` accepts `unspecified` (the compatibility
default), `synthetic`, `local_file`, `sandbox` or `production`. These are operator
classifications, not verified vendor access, certification or permission grants.
Use `local_file` for the export-file reader and `synthetic` for mock fixtures.
Keep sandbox and production data in separate configured systems; changing a label
is not a source-identity migration plan.

Changing an active binding's environment requires a new revision. Collection
configuration pins both revision and environment, and detects a different declared
environment after restart even if an operator reuses the revision string. Human
review must save the intended configuration again. Collected import receipts retain
the declaration; health evidence is current only for the matching revision and
environment. Mapping-transition review tokens include the environment and their
previews display it. Legacy missing declarations mean unspecified, never production.

System Map says Connector binding rather than Live connector. Readiness exposes
`runtime_bound`; the older `live_access` boolean is retained only as a compatibility
alias for binding presence and must not be interpreted as verified vendor access.


Classified synthetic, sandbox and production pages cannot be retained under one
system identity across different declared environments. Configuration, reads and
mapping-transition previews check retained collection jobs, including activated
jobs after staging-payload cleanup. Use a separate configured system for the new
environment. Cancelling an unactivated page removes that page from this guard;
normal human configuration/retry requirements still apply. The guard scopes jobs
to the current workspace and source system.

`local_file` describes transport, and `unspecified` preserves older bindings;
neither establishes whether the underlying data is sandbox or production. Manual
uploads and old jobs without a declaration cannot be classified by this guard.
Operators must still keep test and production source systems separate. A declared
environment is operator metadata, not independently verified source authenticity.


Saved non-null checkpoints also retain their declared environment, including
empty-page reads. They cannot be transferred between classified environments by
reconfiguration or a mapping transition. Disabling a stream preserves this
provenance; legacy positions use their prior reviewed environment when available.
Verification: 68 environment, sync, history, recovery and transition tests pass.
The preceding full Bridge regression run passed 646 tests before this additional
empty-page checkpoint guard.


### Scoped credential-reference broker

`core.bridge_credentials.CredentialBroker` is an optional trusted-startup SDK
component. It has no HTTP route, global default provider or persisted grants.
An operator supplies a `SecretProvider.read(reference)` implementation (including
the optional explicitly configured environment provider described below) and installs an expiring grant for an existing workspace/system,
its vendor, an opaque nonsecret account reference, a declared synthetic/sandbox/
production environment and an exact read-object allowlist.

```python
from datetime import datetime, timedelta, timezone
from core.bridge_credentials import CredentialBroker

broker = CredentialBroker()
# provider is an operator-installed secret-store client; not a Bridge request.
broker.grant(system_id, provider=provider, reference="vault/dealer-read",
             account_ref="authorized-dealer-account", environment="sandbox",
             objects=["customers"],
             expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
# Inside trusted adapter code, before an authorized outbound read:
material = broker.resolve(system_id, reference="vault/dealer-read",
                          account_ref="authorized-dealer-account",
                          environment="sandbox", objects=["customers"])
access_token = material.require("access_token")
```

Resolution checks exact scope, current workspace/system/vendor, pause state and
expiry before provider IO and again after it. Revocation/replacement during IO
rejects the result. Provider values are bounded string fields; malformed material
and provider failures produce a fixed error without raw provider messages. Secret
material is not cached by the broker, written to the graph or included in its
representation. Its wrapper rejects ordinary pickle/JSON serialization. Providers
must enforce their own bounded transport timeout and must not log credentials.

These are trusted Python components, not a sandbox: adapters can access returned
strings and are responsible for not retaining or logging them. Revoking a grant
blocks future broker resolutions; it does not revoke a token at the vendor or
retract strings already handed to an adapter. Python string zeroization is not
claimed. Operators must separately verify the actual vendor account/permissions,
install a real secret-store provider, and update the runtime binding revision when
account or scope changes. A grant does not authenticate a vendor, bind an adapter,
enable collection or permit writes. Existing integrations are not silently moved
to this broker; no real credential store was accessed during this build.


The collection worker and health probe recognize `CredentialUnavailable` as
`authentication_required`, using fixed public messages. Restoring a grant does
not clear an already blocked collection stream: an interactive administrator must
request retry. Synthetic end-to-end tests in
`backend/tests/test_bridge_credential_collection.py` demonstrate a broker-backed
adapter through health, collection, staging, human activation and checkpointing,
including rotation and grant revocation during secret-provider IO. These tests
make no outbound vendor request and do not prove vendor authentication semantics.


### Connected object discovery

Adapters declaring `discover` return a list or tuple of at most 100 unique,
bounded object-name strings from `discover()`. Return no vendor envelope, sample
rows, tokens or credential-bearing URLs. Empty results are valid. GET
`/systems/{system_id}/discover-objects` invokes this read-only capability and shows
only names already in the binding's operator allowlist, plus authorized names
absent from the response. Unapproved object names are omitted, including from the
report fingerprint. Results include binding revision/environment and whether
column inspection is implemented. Nothing is saved, imported or authorized.

The call rejects paused/unbound/unsupported systems before IO, sanitizes adapter
exceptions and discards results after pause, replacement or workspace changes.
Adapters remain responsible for transport timeouts and accurately translating
vendor discovery responses. System Map exposes this inspection only for a bound
adapter declaring the capability. Vendor placeholders do not gain this behavior.


### Optional SFTP snapshot adapter (synthetic protocol verification complete)

`bridge_adapters.export_sftp.SFTPExportConnector` reads one operator-configured
absolute remote file as CSV, TSV or flat JSON, using the same source-ID/time
profiles, bounded parser and content cursor as the local export reader. Its
capabilities are sync/schema/health only. It does not enumerate directories,
write remote files, infer deletions or provide historical events. The existing
collection workflow still stages every changed nonempty snapshot for human review.

The optional dependency is pinned separately in `requirements-bridge-sftp.txt`
(Paramiko 5.0.0, already installed locally). Constructor configuration is trusted
startup code: fixed host/port/path, an explicit canonical known-hosts file,
credential broker/system/account/environment/reference and one object type.
The known host must exist in that file. RejectPolicy is explicit; SSH-agent and
implicit private-key discovery are disabled. Authentication is explicitly selected as `password`, `rsa`, `ecdsa` or `ed25519`.
The broker supplies `username` plus `password` or an in-memory `private_key`.
For encrypted keys, set `encrypted_key=True` and supply `passphrase` in the secret
material. Invalid/missing keys or passphrases fail before connection; RSA keys
below 2048 bits are rejected. No private key is written to disk. There is no
automatic fallback between authentication methods or OAuth enrollment.
It never loads default user host trust or writes a known-hosts file.

Remote reads require regular-file mode, size and modified-time attributes, reject
symlinks/oversize files, compare metadata before/open/after reads and limit bytes
to 1 MB. Per-operation timeouts are 1-15 seconds (default 10), with a checked
60-second read budget. This is not a hard DNS/process deadline. Missing server
metadata fails closed. SFTP metadata does not provide an atomic snapshot or inode
identity: the export producer must publish completed files atomically and the
server account must restrict access. A hostile or concurrently rewritten file
with unchanged size/time cannot be proven consistent by these checks alone.

Credential material now exposes `assert_current()` so adapters can recheck their
original grant after transport IO without rereading secrets. SFTP calls it before
connection and after the completed read; revocation, expiry, scope replacement or
pause discards the result. It does not retract secrets already used remotely.

Host-key/client and SFTP semantics follow the official
[Paramiko client reference](https://docs.paramiko.org/en/stable/api/client.html)
and [SFTP reference](https://docs.paramiko.org/en/stable/api/sftp.html). Mocked-client tests and a real ephemeral loopback SSH/SFTP server verify the
initial implementation. The protocol test covers collection -> staging -> human
activation -> checkpoint, unchanged-file replay, mismatched host keys before
password authentication, failed authentication and required timestamp metadata.
An operator-authorized dealer pilot and deployment-specific transport verification
remain outstanding. No
external host, dealer account, production credential provider or production runtime
binding was configured.


A trusted-startup SFTP configuration can be assembled after granting the matching
broker scope and verifying the server host key out of band:

```python
from core.bridge_adapters.export_sftp import SFTPExportConnector
from core import bridge_runtime

adapter = SFTPExportConnector(
    host=authorized_host, port=authorized_port,
    remote_path="/exports/customers.csv", known_hosts=verified_known_hosts_path,
    broker=broker, system_id=system_id,
    secret_reference="vault/dealer-read", account_ref="authorized-dealer-account",
    environment="sandbox", object_type="customers",
    authentication="ed25519", encrypted_key=True,
    source_columns={"external_id": "external_id", "modified_at": "modified_at"},
)
# Only after the operator has verified this account/path/scope:
bridge_runtime.bind(system_id, adapter, revision="reviewed-sftp-config-v1",
                    objects=["customers"], environment="sandbox")
```

Replace source column roles only after reviewing the actual authorized export.
The example does not enable collection or approve a mapping. Source host, path,
account, environment and authorized object changes belong in a reviewed runtime
configuration revision. Private key material belongs only in the secret provider,
never in mapping proposals, setup notes, URLs or the graph. Real loopback coverage
includes encrypted RSA public-key authentication without password fallback;
mocked transport tests also exercise ECDSA and Ed25519 key loading.


### Paginated local CSV/TSV snapshots

`bridge_adapters.export_file_paged.PagedExportFileConnector` is a separate trusted
local-file reader for exports up to 25 MB and 100,000 logical CSV/TSV rows. Select
`page_size` from 1-1,000 (default 500). Every emitted page must still fit the normal
1 MB staging/parser limit, so wide exports may require smaller pages. JSON arrays
and SFTP pagination are not implemented by this adapter. Manual browser uploads
and the original local/SFTP snapshot readers retain their existing small limits.

Each read verifies the local file metadata and hashes all original bytes. Cursors
include that fingerprint and the next logical row position; quoted newlines do
not change row numbering. The reader scans row widths/counts across the file and
normalizes the selected page through the existing export profile. It rereads and
scans the bounded file per page; it is not a streaming warehouse loader. Field
semantics, identity conflicts and relationships are still validated page by page.
Earlier activated pages are not rolled back if a later page fails review.

Keep the file unchanged until the final page has been activated and checkpointed.
A changed fingerprint during an incomplete sequence raises `source_changed` and
keeps the saved position. Restore the authorized original snapshot to resume; an
explicit reviewed restart workflow is described below.
After a completed snapshot, changed bytes begin a fresh sequence from its first
row. Unchanged completed snapshots return no records. No deletion inference,
historical completeness or atomic all-file import is implied.

```python
from core.bridge_adapters.export_file_paged import PagedExportFileConnector
adapter = PagedExportFileConnector(authorized_absolute_path,
    object_type="customers", file_format="csv", page_size=500,
    source_columns={"external_id": "external_id", "modified_at": "modified_at"})
```

Bind this reader under its own reviewed configuration revision and use the normal
human-reviewed collection flow. File identity/cursor rules differ from the small
snapshot adapter; changing adapter classes does not translate existing cursors.
`CsvConnector` now reports a list from `discover()`, optionally naming an explicitly
configured `object_type`. Its manual-upload metadata is available separately from
`upload_contract()`. An unconfigured CSV helper reports no discoverable objects.


For source records that must be reviewed together, paginated local readers accept
`group_by_source_column="journal_id"` (or a reviewed vendor source-column name).
Groups must be nonempty, bounded and contiguous in the file. A group cannot exceed
the configured page size. Pages include whole groups in source order; they never
fill remaining space by skipping a group. Repeated non-contiguous groups and
cursors inside groups fail closed. Group structure is checked across the bounded
file before returning a page.

Grouping does not establish accounting correctness or turn on reconciliation.
An explicit `balanced_journals` expectation is still required when staging a
journal page for that check. Synthetic tests pair grouped pages with this existing
reconciliation option and human activation. Scheduled collection supports the explicit per-page balance setting described
below. Source grouping meanings must be verified against the actual export.


### Per-page collection reconciliation policy

`bridge_sync.configure(..., require_balanced_journals=True)` and the corresponding
strict optional boolean on POST `/sync` let an interactive administrator require
balanced journal groups on every collected page. This option is valid only for
JournalEntry mappings. Omitting it (or passing null) preserves an existing stream's
policy; new streams default to false. Enabling/disabling a schedule does not reset
this review choice.

The policy is copied into each staged job's existing expectations and activation
receipt. Normal validation blocks a mismatched page. A policy change during
connector IO discards that read, and checkpoint acceptance requires the pending
job's balance policy to match the stream. Resolve and checkpoint a pending page
before changing policy; cancelled pending jobs can be retried through the normal
review flow. The System Map policy control requires explicit acknowledgment that
pages contain complete journal groups (or acknowledgment of removing the check).

These checks compare mapped debit/credit totals separately for each journal and
currency. They do not establish independent source totals, a complete accounting
period or source-ledger correctness, and do not post financial transactions.
Configure group-preserving pagination or a source endpoint that returns complete
journals before requiring this check. Static per-file row counts or monetary totals
are not reused as per-page expectations.


### Reviewed replacement of an unfinished local snapshot

A built-in paginated local reader can now restart an unfinished snapshot after a
human reviews the replacement file. `GET /dealer-bridge/sync/{state_id}/snapshot-restart-preview`
inspects the first page and whole-file structural bounds without staging; its
review token binds the current stream, mapping, pending cancelled job, runtime
binding and replacement byte fingerprint. `POST .../snapshot-restart` requires an
interactive administrator, that token and a reason. The System Map exposes the
control only for eligible paginated local streams.

Active reads and unresolved pending imports block restart. Activated pending pages
must first be checkpointed; cancelled pages remain retained. Completed snapshots
use the existing next-version behavior. Generic API/history/SFTP readers cannot use
this specialized recovery path.

Restart retains all existing canonical records, source observations, jobs and
receipts. It records the previous cursor hash and replacement fingerprint in a
BridgeSyncRecovery audit target, keeps the cumulative accepted-page count and
balance policy, and disables scheduling. The next read starts at row zero with a
cursor pinned to the reviewed file bytes. Changing those bytes after confirmation
blocks collection until a fresh review. Each new page still requires normal
validation and activation; duplicate source rows do not become new customers.
Rows absent from the replacement never imply deletion or complete history.

This is a restart, not a rollback of already activated pages. Source grouping and
all later-page semantic validation still apply. A first-page inspection does not
certify every later source record or the origin/authenticity of the file.


### Financial expectations in offline captured fixtures

The captured-pages JSON accepted by `scripts/check_bridge_adapter.py` may include
`page_expectations`, an array with exactly one entry per captured page. Each entry
uses the same row-count, monetary-total and optional complete-journal contract as
import simulation. A null entry means no independent expectations for that page.
For example, add this property to a one-page JournalEntry captured fixture:

```json
{
  "page_expectations": [{
    "row_count": 3,
    "balanced_journals": true,
    "totals": [{"field": "amount", "currency": "USD", "amount": "0.60"}]
  }]
}
```

Supply independent expectations for each actual page, not a whole-export total
repeated on every page. Empty pages also undergo requested checks. The checker
returns aggregate check counts and failed check types, with no journal IDs,
financial amounts or source values in its output. A mismatch returns exit code 1;
invalid expectation contracts return code 2. `expectations_hash` identifies the
normalized supplied checks separately from the captured `fixture_hash`.

Passing this offline test does not approve or persist collection policy, attest
that the source totals are trustworthy, certify accounting, or activate records.
Runtime collection and every staged import retain their own review requirements.

A complete synthetic journal example is included and tested. From the repository
root, run:

```powershell
python scripts/check_bridge_adapter.py --mapping backend/tests/fixtures/bridge_conformance/journal-mapping.json --pages backend/tests/fixtures/bridge_conformance/journal-pages.json
```

This example has three lines, 0.30 USD in debits, 0.30 USD in credits, and an
absolute line-amount total of 0.60 USD. Those meanings must be reviewed against a
real vendor sample; the example does not prescribe a vendor's sign convention.


### Fixed HTTPS export endpoint

`core.bridge_adapters.export_https.HTTPSExportConnector` is a built-in bounded
snapshot reader for an operator-authorized HTTPS endpoint. It shares CSV/TSV/flat
JSON parsing and SHA-256 snapshot cursors with the local and SFTP readers. It is
not a native CRM/accounting API adapter and does not guess endpoint URLs, vendor
response envelopes, source timestamps or access privileges.

The endpoint is supplied only by trusted startup code, never from Bridge HTTP
input. It must be an absolute ASCII HTTPS URL with no user information, query or
fragment. Exactly one configured path is requested using GET. No redirects,
proxy-environment lookup, cookie handling, pagination, OAuth refresh, source
writes, subscriptions or deletion inference are implemented. Use a dedicated
vendor adapter for APIs needing those additional contracts. Operators must review
the actual endpoint/account relationship and enforce deployment egress policy;
this trusted transport is not a sandbox against privileged configuration.

A scoped CredentialBroker grant supplies `access_token` as a bearer header. The
grant is checked before connecting, after TLS connection and after reading. The
TLS context must retain certificate verification, hostname checking and minimum
TLS 1.2; an optional operator-supplied context can trust a private CA, but cannot
disable verification. The context is checked again on every request. Credentials
are never passed in URLs or reflected in diagnostic text.

Only HTTP 200 export bodies are accepted. Content-Type must match `text/csv`,
`text/tab-separated-values` or `application/json`, optionally with UTF-8 charset.
Compression and ambiguous transfer/content-length headers are rejected. Both
content-length and chunked bodies are bounded at 1 MB; parsing also enforces the
existing 1,000-row/100-column limits. Each socket operation has a 1-15 second
configured timeout, with a checked 60-second read budget. This is not a hard
whole-process deadline: OS DNS resolution and trickled response-header reads may
outlast that budget before control returns. Production egress/runtime controls
must provide any required absolute deadline.

401 maps to authentication review, 403 and redirects to permission review, and
429/503 support a bounded numeric Retry-After delay (1-86,400 seconds). Other
unexpected statuses and malformed export contracts fail closed. Error response
bodies, endpoint addresses, credentials and server messages are not emitted in
Bridge errors. Every accepted nonempty snapshot still stages for human review.

Implementation references: Python's [HTTP client documentation](https://docs.python.org/3/library/http.client.html)
and [TLS documentation](https://docs.python.org/3/library/ssl.html).
Real TLS loopback tests use disposable certificates and synthetic data only;
passing them does not validate any vendor endpoint or authorize production use.


### NXTDeal signed ADF gateway v1

This is a new explicit **gateway protocol**, not a native vendor webhook format.
A trusted integration gateway may deliver existing bounded ADF creation events to
`POST /dealer-bridge/inbound/adf/{endpoint_id}`. Native vendor webhook formats need
separate adapters. Nothing is bound or enabled by default.

Trusted startup code creates an `ADFGatewayVerifier` with a CredentialBroker grant
for exactly `adf_prospects`, then calls `bridge_inbound.bind()` with one source's
approved event profile, explicit environment, revision and opaque endpoint ID.
The verifier must match that source and environment. Use a unique, randomly
chosen endpoint ID (24-96 ASCII letters/digits/underscore/hyphen); it is not a
secret or a substitute for signing. The broker supplies `hmac_key` as UTF-8 key
material, 32-4,096 bytes. Generate a high-entropy secret and store it only in the
operator's secret provider. No API accepts keys, provider URLs or binding code.

An interactive administrator inspects GET `/systems/{system_id}/inbound` and
POSTs `/inbound/{endpoint_id}/policy` with `enabled: true` and the exact runtime
`revision`. API/agent credentials cannot enable it. Disabling remains possible
when a binding is unavailable. Source pause, revoked/unapproved profile, disabled
or demoted authorizing administrator, changed runtime binding and revoked broker
grant all prevent delivery. Declared environments cannot mix between retained
snapshot pages and inbound receipts under the same source system.

Send uncompressed UTF-8 ADF bytes with `Content-Type: application/xml` (or
`text/xml`; optional UTF-8 charset). Supply exactly one of each header:

- `X-Nxtdeal-Delivery-ID`: 1-120 ASCII letters/digits/underscore/dot/hyphen, starting
  with a letter or digit. Stable across retries of the same exact body.
- `X-Nxtdeal-Signed-At`: ten-digit Unix timestamp in seconds.
- `X-Nxtdeal-Signature`: lowercase hexadecimal HMAC-SHA256.

The HMAC message is the exact concatenation below (`\n` denotes one LF byte):

```text
nxtdeal-adf-v1\n<endpoint_id>\n<signed_at>\n<delivery_id>\n<exact_body_bytes>
```

The sender must preserve exact bytes, including whitespace and encoding. The
signature is accepted only from 30 seconds in the future through 300 seconds in
the past. A later retry must be newly signed with the same delivery ID and body;
changing body bytes under an existing delivery ID is rejected. Delivery identity
is source-scoped and is separate from the ADF prospect/source identity. No sender
can provide an administrator role, tenant override, profile choice or activation
request in the delivery envelope.

HTTP 202 means a review job and delivery receipt were durably saved, or that the
same delivery was already received. It never means the Lead was activated.
Simultaneous identical deliveries create one job. Receipt deduplication survives
restart and reviewed staging cleanup. Cancelled jobs remain acknowledged; a
corrected new batch requires a new delivery identity and normal review. The
receiver never stores signing keys, signatures or unselected raw body values.

The body is capped at 1 MB even without Content-Length, with a 15-second body-read
timeout, duplicate/ambiguous header rejection, and four concurrent receiver slots
per process. The operator-configured review-queue limit defaults to 100 unfinished
batches per source (range 1-1,000). Existing duplicate acknowledgments still work
when that queue is full. Backpressure/persistence failures return a sanitized 503
with Retry-After; malformed or unauthorized deliveries return 4xx. Authentication
and parsing errors never echo payloads or secrets. The secret provider must supply
its own bounded timeout; the body timeout is not a whole-ingestion deadline.

Deployment requires HTTPS, reverse-proxy request/header limits, sender rate limits,
secure secret provisioning and the existing isolated-workspace process model.
The in-process limiter and graph storage are not a distributed webhook service.
The SDK tests use in-process HTTP and disposable graph files only; no public
endpoint, vendor subscription or production sender has been configured.


Signed delivery evidence is linked from the staged event job and checked before
validation and activation. Its receipt checksum, source/profile ownership, body
fingerprint and authorizing administrator must remain consistent. Validation binds
that evidence into its review hash; changed delivery evidence requires fresh
review. The activation receipt records the gateway principal and delivery evidence,
while source observations retain transport and receipt IDs for optional Chrono
provenance. Manual upload receipts remain compatible and do not acquire a gateway
attestation. The review page clearly separates gateway receipt from human approval.
These are retained consistency checks, not signatures against a privileged graph
writer and not a reconstruction/reverification of discarded signing material.


Gateway status is explicitly policy-only: inspection does not resolve secrets or
probe sender connectivity. It separately reports consistent retained deliveries,
last receipt time and delivery-evidence issues for the source. Counts include
completed or cancelled batches because receipt is distinct from activation. Missing
or changed receipt ownership/checksums are flagged and excluded from the received
count. System Map guidance prioritizes pending review, evidence/configuration
issues and then enabled or disabled delivery options. A ready gateway policy does
not change the snapshot connector's access status.


Receiver resource tests exercise body timeout, cancellation while reading, and
capacity exhaustion before a body is read. Slots are released on these failure
paths. Unexpected preflight infrastructure failures use the same redacted 503
and Retry-After response as staging failures; they do not expose storage details.


Gateway inspection also returns bounded review-reason codes and whether current
local prerequisites permit a human to review policy. It distinguishes missing
bindings, paused sources, unavailable/unapproved profiles, environment conflicts,
disabled durable storage, changed configuration and an unavailable authorizing
administrator. No secret is read by these diagnostics. A current administrator
can explicitly reauthorize the same revision after the prior administrator loses
access; this changes the policy sponsor and is audited. It does not approve an
event profile or activate any staged batch. Runtime authorization still rechecks
all conditions at delivery time; diagnostics cannot grant access.


### Explicit process-environment secret bundles

`core.bridge_secret_providers.EnvironmentSecretProvider` supports deployments that
already inject secrets into the backend process environment. Trusted startup code
maps up to 100 nonsecret references to exact uppercase ASCII variable names. Only
the selected variable is read, after the broker checks its scope. There is no
environment enumeration, .env loading, shell execution, fallback or automatic grant.

```python
from core.bridge_secret_providers import EnvironmentSecretProvider

# Names only; provision the JSON value through deployment secret management.
provider = EnvironmentSecretProvider({
    "deployment/dealer-export": "NXTDEAL_DEALER_EXPORT_SECRET_BUNDLE",
})
# Supply this provider and exact reference to an explicit expiring broker.grant(...).
```

The variable contains one flat JSON object with nonempty string values. HTTPS uses
`access_token`; SFTP uses `username` plus `password` or `private_key` (and
`passphrase` for encrypted keys); signed ADF uses `hmac_key`. One bundle avoids
assembling different fields from separate variable reads. Duplicate JSON fields,
nested values and malformed material fail with a fixed redacted error. The bundle
is capped at 128 KiB; broker limits also apply: 20 fields, 16,384 characters per
value and 64 KiB combined UTF-8 values. Platform environment limits may be lower.
JSON-escaped PEM newlines are preserved. Never put real values in repo examples
or CLI arguments.

The provider does not cache resolved bundles, but Python's process environment
mapping does not automatically reflect external changes. Deployment rotation or
restart must update the process appropriately. No environment reload or file
watcher is used. See [Python's environment mapping documentation](https://docs.python.org/3/library/os.html#os.environ).
Revoke/replace broker grants to invalidate in-flight checks; changing a variable
alone does not revoke already returned strings. No vendor access, actual secret
provisioning or production deployment is implied.


### Provider-neutral integration-agent discovery contract

Authenticated administrators/API principals can read `GET /dealer-bridge/agent-contract`.
Version1 advertises nine existing operations: inspect System Map and dependency
order; inspect export structure; propose/test snapshot mappings; inspect ADF; list
event profiles; and propose/test event profiles. Each descriptor includes method,
path, path parameter names, effect classification, external-IO flag, and the actual
Pydantic request JSON schema where applicable. Canonical kinds and human-only
boundaries are returned separately. The endpoint stores nothing.

This contract is a small discovery surface for any agent host, not an agent runner,
a new credential scope or automatic MCP/tool registration. It intentionally omits
staging, approval, activation, identity decisions, collection/network probes,
gateway policy and external writes from its advertised proposal/test tool set.
Existing route permissions still govern all direct API calls; this list does not
replace those checks. Agents can persist drafts, then test them without importing
records. Mapping/profile approval requires a different interactive administrator.

The host supplies authentication outside model-generated tool arguments and must
obtain any necessary authorization before sending dealership inputs/results to an
AI provider. Source text and proposed labels are untrusted data, never instructions
to invoke privileged operations. Discovery does not select an AI provider or grant
one access. Tests exercise advertised JSON snapshot and ADF creation-event paths,
ensure real request schemas match, and verify agent approval remains denied.


Runtime bindings are also fenced to the current source record's type, workspace
and vendor. A retained instance becomes unavailable when those identities differ
or the source disappears. Health, schema and collection use this check before IO
and when accepting results. Replacing a changed binding requires a new revision;
existing collection authorization must then be reviewed explicitly. This guards
source-record consistency, not the correctness of an operator-supplied vendor
credential or a privileged operator's configuration.


### Offline check of an authorized export file

For a dealer-supplied export that has not yet been wrapped as SDK pages, run the
existing import transformation/validation pipeline in an isolated process:

```powershell
python scripts/check_bridge_export.py --mapping backend/tests/fixtures/bridge_conformance/mapping.json --export backend/tests/fixtures/bridge_conformance/customer-export.csv --format csv
```

Choose csv, tsv or json explicitly. The mapping file has the same kind, object_type,
fields and optional source_columns definition as the captured-page checker. An
optional --expectations file supplies the existing row_count, totals and
balanced_journals contract. Input caps: mapping64KB, export1MB, expectations32KB;
normal row/column/parser/transform limits also apply. Source ID/time columns and
meanings must come from the actual authorized export. No time is invented.

The checker overrides storage before importing application modules and creates
only a disposable in-memory source/mapping. It loads no production graph or
credentials and calls no connector. Exit0 means the supplied fixture checks passed,
1 means rows or reconciliation need review, and2 means invalid input/tool failure.
Reports contain counts, fixed issue codes and hashes, excluding source values,
IDs, headers and financial totals. This is no approval, authenticity or completeness
attestation. The graph is empty: references to customers/accounts/contracts remain
unresolved and need a separate dependency pilot. Parent records are never silently
loaded or simulated as activated. Use the application review workflow for contextual
identity checks against the dealer's authorized workspace.


Credential material checks its original grant on every `SecretValues.require()`
call, as well as explicit `assert_current()` checks. A retained bundle cannot
return another field after grant revocation/replacement/expiry, source pause,
source removal or workspace/vendor change. This recheck is local and does not
reread the provider. Secret strings already copied by trusted adapter code cannot
be revoked or erased by this wrapper; adapters must retain their existing checks
before and after IO and must not cache credential material between operations.


### Explicit review after connector replacement

For an existing collection stream, changing scheduling settings does not approve
a different runtime revision/environment. Disabling the schedule remains possible
and preserves its prior binding approval. Enabling a changed connector without
review is rejected; manual reads remain blocked by the existing binding fence.
Initial preparation and settings changes for an unchanged connector keep their
existing behavior.

After displaying and reviewing the current operator-bound revision, environment
and source object allowlist, submit both `reviewed_binding_revision` and
`reviewed_binding_environment` to `POST /dealer-bridge/sync`. They must exactly
match the binding at mutation time. Stale or partial review is rejected. The core
`bridge_sync.configure` function accepts the same names as keyword-only arguments.
The UI's explicit Review and save current connector action supplies these fields.
Do not automatically read and resubmit the latest revision on a rejected request;
show the changed configuration for human review again.

This tightens reconfiguration callers: older callers that implicitly reapproved
a replacement by resaving settings must now supply the reviewed fields. No graph
migration is needed. The action does not expand broker grants, approve a mapping,
activate an import or enable vendor writes.


Gateway status now includes a `review_token` when policy prerequisites permit
human review. The Bridge browser submits this token when enabling or reauthorizing
staged delivery. It covers the current source identity labels, profile/hash/status,
revision, environment, queue limit and saved policy. A changed configuration or
concurrent policy change rejects the stale enable request before mutation. No
signing material is resolved to create or check this token. It is a consistency
marker, not an authentication credential or cryptographic signature.

`POST /dealer-bridge/inbound/{endpoint_id}/policy` accepts the optional64-character
`review_token`; new clients should always send the token they displayed for review.
Omitting it preserves the older revision-based API contract. Disable remains
available without a current token and preserves the prior source/profile binding.
This guard does not verify provider account ownership, send a test delivery, or
replace the required administrator session and gateway signature verification.


### Health evidence in onboarding guidance

System Map uses a failed or degraded health result only when its binding revision
and environment match the current connector. It provides operator guidance for
authentication, permissions, source change, rate limit and availability failures.
This is the last recorded diagnostic, not a background monitor or an authorization
gate. Retained imports remain reviewable and take priority. A successful explicit
recheck clears that diagnostic guidance without enabling collection or writes.
Reading System Map never invokes a connector health method.


### Requiring a terminal captured page

For a finite export capture, run:

```powershell
python scripts/check_bridge_adapter.py --mapping mapping.json --pages pages.json --require-terminal-page
```

The report always includes `terminal_page_captured` and `terminal_page_required`.
The optional flag reports `terminal_page_missing` (exit1) if the final valid SDK
page does not declare `complete: true`. Without the flag, partial captures can
still pass local fixture checks. The Python `verify_pages` helper accepts the
strict boolean keyword `require_terminal_page`. Malformed terminal envelopes
cannot satisfy the requirement.

A terminal marker is the adapter's declaration, not evidence that every vendor
record or historical event was captured. A nonempty initial cursor may describe
only the end of a longer stream. Independently validate authorized date ranges,
row counts, monetary totals and vendor pagination semantics before pilot approval.
The checker never runs an adapter, advances a real cursor or activates records.


### CSV helper capability correction

`CsvConnector` is a bounded in-memory snapshot helper. It advertises discover,
schema, sync and health; it no longer advertises history or aliases history to
sync. Use `sync()` for the captured snapshot. Calling its inherited `history()`
now fails as unavailable, and a history schedule cannot be enabled for it. An
existing history stream using this helper becomes unavailable until a genuinely
history-capable adapter is reviewed; retained imports and observations remain.
This does not remove source modified times, historical snapshots uploaded by a
human, or the Bridge's retained source-observation history.

An explicitly configured `object_type` is enforced by schema and sync. Legacy
helper callers that omit it continue relying on the operator's runtime allowlist.
Health now checks whether the bound content parses: missing content is unavailable,
invalid content reports source_changed, and a valid snapshot reports ready. These
checks expose no row values and do not authenticate a vendor. The unbound manual
upload catalog remains available; a user can still choose an authorized file.


Connected schema reports include `environment` alongside `binding_revision`.
Clients should tie displayed suggestions to the current selected source/object,
revision and environment, and suppress them when source access is paused or the
capability is removed. This is a draft-review aid; server mapping approval and
collection authorization remain separate.


### Ordered multi-file pilot checks

Use the standalone pilot checker when an authorized sample includes dependencies
across files. The single-file export checker intentionally starts with an empty
graph; this checker instead builds a disposable in-memory graph in the supplied
order. It never loads an existing graph, invokes a connector, resolves credentials,
delivers Chrono events, or persists imports. Passing steps receive **synthetic
approval and activation only inside the disposable process** so later steps can
resolve source references. This is not a production approval or an agent tool.

From the repository root, run the supplied synthetic mixed-format example:

```powershell
python scripts/check_bridge_pilot.py --manifest backend/tests/fixtures/bridge_pilot/manifest.json
```

The version-one manifest contains exactly `version: 1` and `steps`. Each step has:

- `source`: a case-sensitive local source alias (1–64 ASCII letters/digits/underscore/hyphen, starting with a letter or digit). Reuse it only for the same source identity namespace. Different aliases produce separate systems.
- `mapping`: the existing canonical `kind`, source `object_type`, `fields`, and optional `source_columns` definition.
- `export`: a relative regular file inside the manifest directory. Absolute paths, parent traversal and resolved paths outside that directory are rejected.
- `format`: explicit `csv`, `tsv`, or `json`.
- Optional `expectations`: the existing independent row/financial reconciliation contract.

Limits are 128 KB for the manifest, ten steps, 1 MB per export, 2 MB of total export
bytes and 1,000 total checked rows. Steps are ordered explicitly; no dependency
order, source timestamps, borrower roles, cross-system identity links or financial
balances are invented. Use `external_id` transforms with the actual source object
namespace for parents. Raw NXTDeal IDs from another graph will not resolve here.
The synthetic example is a neutral contract fixture, not a vendor export schema.

The report contains counts, hashes, reconciliation outcomes and issue codes, with
no source aliases, paths, record values or monetary totals. It reports the number
of steps synthetically activated. The first quarantined row, reconciliation issue
or relationship advisory stops processing; remaining steps are explicitly untested.
No identity-review decision is generated to bypass a potential duplicate. Exit0
means fixture checks passed, exit1 means review issues, and exit2 means invalid
input or tool failure. A successful report still requires independent source
completeness checks and ordinary human review in the actual dealership workspace.


The larger synthetic BHPH/accounting example uses the same checker:

```powershell
python scripts/check_bridge_pilot.py --manifest backend/tests/fixtures/bridge_pilot/bhph-accounting-manifest.json
```

Its eight ordered steps cover customer, contract, account, allocated payment,
linked reversal, payment schedule, a separate accounting chart and a balanced
journal. Ten rows use CSV, TSV and JSON. Expected amounts are fixture assertions,
not independent evidence about a dealer's books. Reversal signs and source status
labels are deliberately synthetic and must be verified for each real product.
The account balance remains a source observation; payment rows do not calculate
or update it. The journal amount total includes both debit and credit lines and
must not be interpreted as net cash. The fixture creates no native cash posting,
servicing action, collection task or external journal entry.

Repeated identical source versions are reported as duplicates. Changed values at
the same source timestamp stop the check for review. Source references remain
scoped by the manifest's source alias and object type, including across replay.


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
