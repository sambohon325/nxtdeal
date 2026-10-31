# Dealership and NXTDeal system administration

`ADMIN` is the dealership administrator role. It does not confer platform access.
Each backend retains its existing isolated credentials, graph and storage directory.
This change does not introduce cross-dealership data access.

## Provisioning

The deployment operator provisions an existing, individually assigned ADMIN login
in that backend, completes its password change, and sets `NXTDEAL_SYSTEM_ADMIN_IDS`
to its exact employee ID (comma-separated for multiple people). Use a separate
NXTDeal staff account, not a shared dealership login. Configure this on the backend,
not the frontend. Leave it empty to disable system administration. No existing
ADMIN is automatically promoted. Do not list an ID until its ownership is verified.

The designation is outside the editable graph and role/permission APIs. Dealership
administrators cannot create/reset a reserved identity, change its role, disable
its MFA, or grant system access through overrides. Existing API keys do not inherit
system privilege. Removing an ID revokes system access on the next API request,
even for an existing session; reload to refresh visible navigation.

## Enforcement

The request boundary protects system route families, including backups, audit,
connections/providers, SSO/security, API keys, AI controls, agent runtime, customer
success and Dealer Data Bridge. Entitlement and feature-flag writes are protected;
operational entitlement reads remain available. Menu catalogs and direct menu reads
are filtered independently, unknown admin menu keys deny by default, and retired
system workflow data is blocked. Generic graph edits cannot mutate control records.

`/auth/whoami` reports `is_system_admin` from the verified server identity. The UI
uses that result for navigation, bridge entry and scoped help; the API remains the
authority. Users cannot upgrade themselves by editing local storage.

## Release checks

Run backend `pytest tests/test_administration_access_boundary.py` and the auth,
user-management and security regressions; run the frontend tests/typecheck/build.
Deploy both backend and frontend. Verify a dealership ADMIN sees only dealership
areas and receives 403 from system endpoints, and a provisioned NXTDeal account
can reach system tools. Confirm the exact account IDs with the deployment owner
before setting production environment configuration.
