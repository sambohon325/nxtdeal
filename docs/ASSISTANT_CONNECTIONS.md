# Assistant connections and Chrono setup

The Department Agents **Connections & assistant access** link opens `/agents/connections`. This release provides native OAuth onboarding and a read-only Chrono API adapter. It does not claim any third-party account is installed or any vendor write adapter is connected.

## Assistant account setup

1. In the assistant's remote MCP configuration, use `https://api.nxtdeal.app/agent-fabric/mcp`. Obtain the **exact callback URL from that client's settings**.
2. In NXTDeal's connection center, an administrator registers the assistant name and that HTTPS callback. This produces a public client ID; token endpoint authentication is `none`, with S256 PKCE mandatory. No client secret or NXTDeal employee token is copied into the assistant.
3. Enter the client ID in the assistant and start its OAuth sign-in. NXTDeal displays the registered name, client ID, callback and requested scopes. Select the departments to grant and explicitly approve or deny.
4. Verify a catalog read from the actual assistant. Registration alone is not connection evidence. Revoke the grant in NXTDeal to check that subsequent requests fail. Client disable revokes all grants for that client.

Supported flows: authorization code plus S256 PKCE, one-use codes, rotating refresh tokens, exact resource binding and explicit HTTPS callbacks. Metadata lives at `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource/agent-fabric/mcp`. No open dynamic client registration, implicit grant, client credentials, guessed callbacks or account auto-installation is implemented. Client-specific availability and support for manually entered public client IDs must be verified in each target account. This is not a claim that all advertised AI brands have passed interoperability tests.

Scopes are `nxtdeal:read` and optional `nxtdeal:propose`. Grants are restricted to selected departments plus the employee's current permissions and dealer policy. Access tokens last at most one hour, grants and refresh tokens at most 30 days. Replayed valid codes/refresh tokens revoke the grant. Disabled/deleted employees, changed passwords, password-change-required accounts and IP-restricted accounts cannot use these assistant grants. IP-restricted employees need a separately reviewed client-network policy; the connection does not bypass their restriction. Role changes are checked on every call. OAuth tokens are accepted by MCP only, not general employee REST endpoints. Approval, policy edits and action execution are absent from MCP.

Client labels and `provider` fields are descriptive metadata, not verified platform identities. The UI never preselects department consent. It blocks framing and suppresses referrers. Public authorization/token/revocation routes share a bounded 300-request/minute process budget, token forms are capped at 8 KiB, and MCP messages at 64 KiB. Client, pending-request, grant and refresh-history limits are enforced. No real employee access was granted during fixture testing.

## Deployment and recovery

`NXTDEAL_PUBLIC_API_URL` and `NXTDEAL_PUBLIC_APP_URL` are trusted server configuration. Defaults identify the existing primary NXTDeal deployment (`https://api.nxtdeal.app`, `https://app.nxtdeal.app`). Set both explicitly for any other dealership process; do not derive issuer/callback origins from untrusted request headers. Changing the issuer invalidates existing audience-bound grants.

OAuth state is stored separately in the active dealership storage directory as `assistant_oauth.sqlite3`. Codes/tokens/request handles are stored as SHA-256 hashes; the graph and generic entity endpoints never contain credential values. SQLite transactions serialize exchange/rotation/revocation and roll back incomplete writes. The POSIX database file is mode 0600; Windows relies on host directory ACLs. Keep one backend process per dealership as required by the existing graph storage.

Existing graph-only backups do **not** back up the OAuth database. Treat it as authentication state: after a disaster recovery, prefer deleting/replacing grants through a reviewed recovery procedure and reconnecting accounts, rather than restoring old token state that could resurrect revoked access. A database backup requires SQLite's backup API or a stopped process, not a live file copy. This feature does not establish offsite recovery or a new shared-tenant authorization system.

## Chrono

The adapter uses the actual `sambohon325/chrono` API contracts for `/v1/businesses/{business}/workspace-summary` and `/analysis-history`. Server setup requires:

- `NXTDEAL_CHRONO_BUSINESS`: the exact intended business identifier.
- `NXTDEAL_CHRONO_TOKEN`: a current, scoped Chrono API credential, stored in the deployment secret settings and resolved through `core.secrets`.
- Verified HTTPS routing for `api.chrono.technology` and API authorization for that business. A working Chrono browser session alone is not an API credential.

The host is fixed; redirects cannot forward credentials elsewhere. Responses are capped at 1 MiB with a 10-second network timeout and must match the configured business and expected response shape. No dealer records are uploaded. The connection center reports missing settings and offers an authorized read probe; it never reveals the secret. Administrator/Operations employees can use `chrono.workspace.read` and `chrono.history.read` through the GM pack. History keeps original evidence cutoffs and pagination metadata; it is saved external analysis, not a fresh prediction or an instruction to act. `chrono.analyze` remains unavailable until an approved numerical computation/data-mapping contract is supplied.

CRM/DMS/advertising writes remain unavailable without named vendor accounts, authorized API access and operation-specific adapters. The concurrent Data Bridge work is separate from this release. No silent activation of imports, outbound communication, spending or predictive decisions occurs.

## Validation

97 focused backend tests passed, covering the real HTTP MCP OAuth boundary, PKCE/resource/callback rejection, replay revocation, refresh rotation, concurrent exchange, role and credential changes, consent denial, storage rollback, token hashing and Chrono scope/response checks. Frontend ESLint and production build passed. Isolated browser testing verified sign-in, connection details, callback registration display, no preselected departments, and enabling the consent button only after explicit selection. Preview: `docs/dealeros-next/previews/assistant-connections.jpg`.

Protocol sources: [MCP authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization), [OpenAI plugin authentication](https://developers.openai.com/plugins/build/auth), and the Chrono repository's `docs/schema/openapi.json` and `docs/CHATGPT_INTERFACE.md`. Account-side connection and revocation tests require the actual target assistant account.
