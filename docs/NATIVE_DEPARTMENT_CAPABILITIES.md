# Native department capabilities

All twelve packs have a native workbench, a manual operating-review workflow, and approved work assignment/outcome actions. They run on existing NXTDeal records without assistant, CRM or DMS connections.

| Department | Native operating evidence |
| --- | --- |
| Sales / BDC | Lead ownership, missing activity timestamps, 48-hour inactivity, appointment follow-up |
| Marketing | Campaign drafts and inventory age/merchandising exceptions |
| GM | Leads, deals, vehicles, service records and operating tasks |
| F&I | Deal/finance-contract status and missing delivery checklist observations |
| Accounting | Approved payments not marked posted, accounting periods and open deals |
| Service | Technician assignment, waiting parts, appointment outcomes and native Service bookings |
| Parts | On-hand/reorder-point observations and outstanding RO part requests |
| Inventory | Observed aging and missing year/make/model |
| Operations | Unassigned/overdue operating tasks and vehicle/deal exceptions |
| HR | Minimal employee roster plus explicitly assigned onboarding/training/policy work |
| Compliance | Recorded open alerts and missing consent timestamps |

Every pack exposes `<department>.workbench.read`, `<department>.work.create` and `<department>.work.update`. Each has `<department>.daily_review`, an on-demand read (the name does not schedule a job). Service also exposes `service.appointment.create`, replacing its inappropriate Sales appointment action.

Work assignments require an accessible source record, a due timestamp with timezone and an active employee account with the appropriate department role. The gateway requires another administrator's approval before creating or updating work or booking service. Creation and execution recheck current credentials, source access, policy, kill switches and stale record versions. Existing proposal idempotency prevents duplicate execution. Work histories retain actors and outcomes; closed work cannot be silently reopened. A completed assignment does not mark the source deal, RO, payment or compliance alert complete.

Reports allowlist scalar fields and exclude payment amounts, bank details, employee credentials, compensation and customer contact information. Existing entity permissions, department grants and OAuth read/propose scope still apply. Reports distinguish missing observations from zero and return totals, an as-of time and a 100-entry limit per section. Specific record IDs allow focused inspection beyond the first page. They report review signals, not forecasts or certification.

HR work records explicit completion evidence; it does not infer employee performance, make employment decisions or automatically attest that training occurred. Finance/accounting reviews cannot fund a deal, post a payment, transfer funds or make lending decisions. Parts follow-up does not place vendor orders. Pricing, external communication and Chrono predictions remain under their existing contracts.

This completes the native operating-workflow layer of the department packs, not every possible future feature listed in their long-term responsibility descriptions. External integrations remain optional and separate.

## Verification

The isolated department suite exercises all twelve workbench/assignment/approval/completion paths, idempotency, read-only source preservation, cross-department denial, policy/OAuth restrictions, current-credential assignment checks, stale updates, malformed observations, bounded reports and native service booking. Existing gateway, OAuth and appointment tests are included in regression verification. No production dealership records are used for tests.
