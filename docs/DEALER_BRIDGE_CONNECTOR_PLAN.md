# Dealer Bridge connector delivery plan

Status checked 2026-10-03. This is an implementation plan, not a claim of vendor approval or API access. The shipped intake supports bounded CSV/TSV/flat JSON snapshots and a separately approved ADF creation-event profile; the Frazer file profile is dealer-supplied and unverified. No application, email, partnership form or credential request has been submitted.

## First pilot: Frazer, then the pilot dealer's adjacent systems

Frazer publishes a [partner application](https://www.frazer.com/frazer-partner-program) and an [integration directory](https://www.frazer.com/frazer-integrations). These establish a contact path, not NXTDeal's authorization or the availability of any particular endpoint. Start by obtaining a dealer-authorized, sanitized export and its column definitions. Validate the existing file-profile scaffold against that sample before pursuing a live adapter through the partner process.

Frazer's [product description](https://www.frazer.com/) includes BHPH and accounting functions. For the pilot, sequence customers and inventory first, then contracts/accounts and payment history. Confirm whether exported balances are as-of snapshots, whether payments include reversals, and how source timestamps and stable IDs behave. Do not derive balances from observed payment rows or treat an approved source payment as a native cash posting.

## Independent and BHPH coverage

| System family | Current Bridge state | Next implementation evidence |
| --- | --- | --- |
| Frazer | Unverified supplied-column CSV profile; no live API | Authorized sample, identity/time definitions, partner access decision |
| DealerCenter | Catalog placeholder; generic authorized CSV review | Dealer's product/version, supported export/API documentation, sandbox and consent |
| DealerSocket IDMS / AutoStar | Separate catalog entries; generic CSV review | Product-specific access, portfolio identifiers, schedules/reversals and history limits |
| AutoManager DeskManager | Catalog placeholder; generic CSV review | Actual deployment/version and authorized schema sample |
| Wayne Reaves | Catalog placeholder; generic CSV review | ProDMS versus other deployment, authorized sample and partnership requirements |
| Deal Pack | Catalog placeholder; generic CSV review | Current vendor documentation and dealer-approved extract; older public documents do not establish a current API |
| Carsforsale.com / Dabadu / other independent DMS | Catalog placeholders | Pilot-system inventory and authorized technical documentation |

DealerSocket describes an [independent/BHPH product and integration ecosystem](https://dealersocket.com/solutions/dms-independent/) and [IDMS account management](https://dealersocket.com/products/idms/account-management/). Wayne Reaves publishes a [partner page](https://www.waynereaves.com/partners). Those are verified vendor contact/context sources; implementation details and NXTDeal access remain unverified.

## Adjacent stacks are separate connections

Record each actual system separately in System Map, even when several belong to one vendor. Do not assume a DMS license authorizes its CRM, website, payments, accounting or marketing products.

| Stack | Planned first canonical objects | Later capabilities require separate verification |
| --- | --- | --- |
| CRM: Elead, VinSolutions, DriveCentric, DealerSocket, AutoRaptor, HubSpot, Salesforce, Zoho, other | Customers, leads, communications, consent | History completeness, consent semantics, incremental reads |
| Websites/inventory: DealerOn, Dealer.com, Dealer Inspire, AutoRevo, Dealer Car Search, other | Vehicles, price observations, leads | Feed scope, lead identity, deletes and correction semantics |
| Accounting: QuickBooks, Xero, Sage, NetSuite, other ERP | Accounts and journal observations | Period boundaries, debit/credit meaning, currency and independent totals |
| Phone/messaging: Twilio, RingCentral, CallRail, other | Communication metadata and consent | Recording/content access, retention, contact identity |
| Marketing: Google, Meta, Microsoft, Mailchimp, other | Campaign observations | Correct business/property scope, attribution definitions and read permissions |
| Payments/servicing: REPAY, PayNearMe, other | Payment/schedule/account observations | Reversals, settlement versus authorization, processor IDs; no charging or collection commands |

These are NXTDeal planning choices, not assertions that each vendor exposes every listed object. The catalog includes other-system entries so an independent dealer can describe its complete stack without pretending that a named connector exists.

## Franchise access path

CDK/Fortellis, Reynolds, Tekion, Dealertrack, DealerBuilt and Auto/Mate remain explicit placeholders. For each, obtain the applicable dealer authorization and vendor program documentation, identify the specific product/API, then add its adapter under `backend/core/bridge_adapters/`. Certification, fees, scopes and endpoints are deliberately unspecified until verified for the actual product. Do not infer access from another integration marketplace's listing.

## Expanded overnight coverage (October 4)

`backend/core/bridge_catalog.py` is the product/alias inventory. Category labels and planned record types now come from the server. Searchable aliases do not authorize an adapter or pick credentials. The UI requires a visible selected product before adding a system. Catalog entries are planning records; manual CSV/TSV/flat JSON and bounded ADF intake are available without live vendor access. Operator-bound collectors and signed gateways require their own configuration and explicit policies.

The supplied list is represented across independent DMS (including Desk-It, DealerClick, Auto Master Systems and Finance Express), CRM (Selly, DealerCenter CRM and cyclCRM), BDC (Impel/SpinCar, Matador, Fullpath/AutoLeadStar and CarNow), communications (Car Wars, Convirza, Podium, Kenect and SocketTalk), websites (Dealer Spike, DealerCenter Web and Carbase), valuation (vAuto, MAX Digital, Laser Appraiser, Carbly, MMR, KBB, Black Book and CARFAX), fixed operations (Dealer-FX), marketing (AutoHook), servicing (Megasys and Nortridge), devices (GoldStar, PassTime and Procon), payments (Speedpay), bureau reporting (Datalinx, individual bureaus and dealer-specific DMS modules), and lender networks (RouteOne and Dealertrack Lender Network). Existing franchise, accounting and independent products remain in the registry.

Product identity still needs confirmation for ambiguous supplied names such as Desk-It and cyclCRM. Auto Master Systems is distinct from AutoManager DeskManager. Dealertrack DMS is distinct from its lender network. A shared company name does not combine separately authorized products.

### Public access evidence checked October 4, 2026

- [Nortridge API overview](https://apidocs.nortridge.com/docs/understanding-the-api): version-dependent API documentation and OAuth authentication are described, with connection licensing considerations. No NXTDeal credentials, licensed connection, deployment version or approved scope have been established.
- [Nortridge payment history](https://apidocs.nortridge.com/docs/viewing-a-loans-payment-history): documents a loan payment-history read. Component and total rows require explicit classification before canonical payment mapping; summing every row would be unsafe. Confirm source timestamps, reversal semantics and totals against authorized fixtures. Do not copy illustrative credentials or enable XML import/payment posting.
- [Spireon developer page](https://api.spireon.com/doc): describes FleetLocate. This is **not evidence of GoldStar API access**. GoldStar stays unavailable until product-specific documentation and authorization are supplied.
- [Datalinx integration services](https://datalinxllc.com/integration/): establishes an integration contact path, not a verified endpoint or permission to submit bureau files. Reporting metadata remains a future schema decision; bureau pulls, furnishing and dispute actions are disabled.

Megasys and the remaining newly listed products still require product-specific authorized technical evidence. Public documentation is research evidence only; none of these sources activates a runtime binding.

## Adapter acceptance checklist

1. Keep every vendor field, pagination rule and source identifier inside its adapter/profile. Map into the shared canonical model through immutable approved mappings.
2. Use a distinct authenticated runtime instance and explicit object allowlist per configured system. Registering a vendor implementation does not authenticate a dealer.
3. Test sanitized fixtures for stable IDs, timezone handling, missing/duplicate columns, page bounds, history ordering, cursor continuity and financial totals.
4. Exercise timeout/rate-limit classification without returning raw response bodies or credentials in errors. The adapter must bound its own network timeout.
5. Test restart/replay with saved checkpoints. Never advance a nonempty page before human activation; mapping changes require a reviewed transition.
6. Enable only verified read capabilities first. Write proposals remain blocked until a separate operation-specific authorization and reconciliation design is implemented.

The next highest-priority connector is the Frazer pilot export profile, because that scaffold exists and the independent/BHPH request makes its account/payment relationships a useful first validation target. The actual pilot dealer's installed stack and authorized access should determine the connector after that.


### October 4 local export collection foundation

The SDK now includes `ExportFileConnector` for trusted runtime configuration of a
single authorized CSV, TSV or flat JSON file. It stages changed snapshots through
the existing human approval flow and has no history or write capability. This can
support an authorized export pilot once the dealer supplies the actual profile;
it does not establish vendor access or install a production binding. See the SDK
for original-byte cursor versus normalized CSV evidence and filesystem limitations.


### BHPH pilot acceptance scenario

The executable synthetic pilot in `backend/tests/test_bridge_pilot_workflow.py`
now exercises customers -> vehicles -> finance contract -> loan account -> payment
and schedule -> linked reversal -> collection and repossession observations,
alongside an explicitly linked adjacent CRM and balanced accounting journal.
Run it with the repository backend test command before adapting an authorized
sample. It checks exact allocation totals, stable relationship IDs, reversal replay,
source-history lookup, real graph reload and idempotent local temporal delivery.
Imported states do not execute payments, collection actions or repossession tasks.

For a real pilot, independently establish the vendor's payment/reversal sign and
status conventions, account balance as-of time, partial versus complete payment
history, schedule revisions, and whether a row is a component or total. The test's
synthetic negative reversal convention must not be assumed for any vendor. Source
balances remain observed facts; the Bridge does not infer a new balance from the
payment rows available in an export.


The first authorized sample can now be checked directly with
`scripts/check_bridge_export.py --mapping <definition.json> --export <export-file> --format csv`
(or tsv/json), optionally with --expectations. This runs in a disposable empty
graph and prints only bounded counts/hashes. It does not approve the sample,
validate Frazer's semantics, authenticate any vendor or load related production
records. Review dependency warnings and independently confirm financial totals
before the contextual pilot workflow.


### Products spanning multiple discovery categories

Catalog entries retain one identity while `discovery_categories` supports finding
a product in multiple groups. The supplied list puts Auto/Mate in independent/BHPH
as well as franchise planning, Deal Pack in loan servicing as well as DMS planning,
and Fullpath in BDC as well as marketing planning. The UI searches these tags;
primary category and connector capability declarations are unchanged. Separate
dealer installations or scopes can still be registered separately. Categories
are discovery aids and never imply API access, certification or authorization.


For related authorized pilot files, `scripts/check_bridge_pilot.py --manifest
<manifest.json>` now checks an ordered bundle in a disposable in-memory graph.
The supplied `backend/tests/fixtures/bridge_pilot/manifest.json` demonstrates a
synthetic customer CSV, contract TSV and loan-account JSON. This is a neutral
fixture, not a Frazer schema. Passing steps are synthetically activated only inside
the process so later source references can resolve; production approval is never
created. The checker stops on dependency, reconciliation or borrower-review issues.
See the SDK for manifest bounds, source namespace isolation and report semantics.
