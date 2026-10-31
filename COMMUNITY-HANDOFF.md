# NXTDeal community handoff

**Prepared October 31, 2026.** This document transfers project context to a future community maintainer. It reflects a review of a single source snapshot, not an assurance that every branch or deployment matches it.

Public repository: [github.com/sambohon325/nxtdeal](https://github.com/sambohon325/nxtdeal). The current `main` is a clean, history-free snapshot created from upstream `dealerOS` `main` at `ee722ed4a59185d48e939a48614167c3e113097c`, without copying its history or other branches.

## Project summary

NXTDeal is a dealership operations platform evolved from DealerOS. The intended product spans Sales, Marketing, Inventory, Service, Finance, Operations and Administration, with dealer apps, a platform Hub, integrations, audit/governance, and Chrono decision-support components. Legacy names and domains remain in code and configuration.

NXTapp (the NXTDeal application) is an open-source dealership operations workspace. It was designed to bring customer and sales work, department tools, and dealership planning into a shared product. The system is made up of a Next.js/React web interface, a Python/FastAPI backend, and a dealer administration Hub, alongside Chrono decision-support components.

NXTDeal grew from DealerOS. In this package, the name NXTDeal refers to the public repository and product; older DealerOS names remain in some code, configuration and documentation.

### Implemented areas in this source snapshot

The repository contains substantial implementation work in the following areas. This is an inventory of code and interface surfaces, not a claim that every feature is complete, integrated, or production-ready:

- **Shared dealership records:** graph-oriented entities and relationships for customers, vehicles, employees, leads, deals, documents and workflows, with JSON-backed stores and compatibility code.
- **Customer, CRM and BDC work:** lead and customer records, assignment and follow-up concepts, appointments, customer journeys, messaging-related workflows and BDC interfaces.
- **Sales and delivery:** deal and vehicle workflows, sales dashboards, delivery-oriented workflows and sample/demo flows.
- **Department tools:** interface and API work for marketing, inventory, service and parts, finance, operations, administration and related dealership functions.
- **Workflows and audit:** workflow definitions, execution and history, plus audit records connected to selected lead and workflow events.
- **Planning and Chrono:** Dealership Lab scenarios, reporting and planning interfaces, and shared Chrono decision-support code. Several areas are candidates or guarded paths and need independent verification.
- **Dealer Hub and integrations:** a separate Hub for dealer registration/configuration and integration or provider scaffolding. Provisioning does not itself start or operate a tenant deployment; some provider paths require credentials and explicit setup.
- **Web application and API:** a Next.js/React frontend and a FastAPI backend with a broad set of router modules and domain services.

### Screenshots

These are illustrative product-interface captures from the NXTDeal work. They include interface/demo material and sample data; they are not proof of a currently running product, a completed integration, or production acceptance. Media and brand assets are excluded from the MIT software license; see `ASSET-NOTICE.md` before reusing them.

- [Sales workspace capture](frontend/public/handoff/nxtdeal-home-real-product.jpg)
- [CRM workflow example](frontend/public/handoff/nxtdeal-crm-report-demo.jpg)
- [Dealership Lab scenario screen](frontend/public/handoff/nxtdeal-lab-dashboard.jpg)

The main application architecture is a Python/FastAPI backend (`backend/`), Next.js/React frontend (`frontend/`), and Hub/control-plane services (`hub/`). The application currently has both direct FastAPI route wiring and router modules. Business logic is spread across `backend/core/` and `backend/api/routers/`; follow local patterns when making changes.

The legacy graph model stores dealership entities and relationships. JSON files and subsystem stores remain active compatibility surfaces. A repository abstraction and PostgreSQL schema work exist in the development history, but the available docs do not establish that PostgreSQL replaced JSON as runtime authority. Do not assume a completed database cutover.

## Snapshot selected for this package

- Upstream repo: `https://github.com/sambohon325/dealerOS`.
- Selected commit: `ee722ed4a59185d48e939a48614167c3e113097c` on `main`, dated October 26, 2026.
- The GitHub repository was private when inspected. Its default branch was unprotected and many development branches were present.
- This package deliberately excludes private `.git` history and branches, internal build diaries/evidence, tracked `backend/data/` CSV files, editor instruction files, and private deployment/AI automation workflows. It keeps the coherent tree from one commit and makes no claim that this is the only relevant NXTDeal work. Separate streams such as Chrono Lab, templates, desktop, compliance, security and marketing may have later or independent changes that are not included.

## State and expectations

The project is an unfinished, broad product with incomplete workflows, integrations and release gates. Existing readiness notes contain dated candidate evidence, not a guarantee that the current snapshot is accepted or deployed. This package has not been validated by a clean install, full test run, browser acceptance, comprehensive security audit, or deployment rehearsal.

The marketing deployment is intentionally a single-page community handoff. With `NEXT_PUBLIC_DEPLOYMENT_MODE=marketing`, the root page explains the handoff, NXTapp and its implemented areas, and links to the screenshots and this repository; other non-static paths redirect to `/`. The live marketing domains are deployed from a separate private Coolify-connected branch. The public repository does not contain production deployment credentials or a deployment workflow.

The seed generator in this package has been adjusted to use `example.com` employee emails and reserved fictional 555-0100–0199 phone numbers. Previously committed `backend/data/` CSVs are omitted. The bridge conformance customer-export fixture email was replaced with `customer@example.com`. Private domain routing configurations, deployment notes, internal release documents, planning notes, preview images, and selected private operational docs were also removed. This is targeted data cleanup, not certification that every remaining file is free of personal or proprietary material.

## Suggested order for maintainers

1. Decide whether to maintain a server product, a local/demo package, or just preserve the source. Avoid implying production support until someone owns operations.
2. Review `PUBLIC-RELEASE-CHECKLIST.md`, especially code/data provenance, assets, licensing and dependencies.
3. Reproduce the synthetic stack and clean-install instructions on a fresh machine, then publish the actual results and known failures.
4. Prioritize a narrow, well-tested workflow before attempting broad rewrites. Add regression coverage alongside behavior changes.
5. Keep customer, employee, dealer and credential data out of issues, pull requests, logs, demos and fixtures.
6. Treat authentication, tenant boundaries, financial workflows, compliance, messaging and external integrations as high-risk areas. Require independent review for changes that affect those boundaries.
7. Update this handoff and public status notes with dated evidence. Distinguish code present, tests passing, deployed, and user-accepted.

## Known architectural questions

- Which workstreams and products are in the intended public scope (especially Chrono, desktop, template studio, and marketing surfaces)?
- Which backend/frontend deployment pairing is the intended community baseline?
- Which JSON stores are authoritative today, and what remains only a PostgreSQL schema/import scaffold?
- Which features are production-enabled versus fixture/demo-only or guarded by provider credentials and feature flags?
- Who will own dependency updates, security reports, CI, hosting, and release decisions after the original developer exits?

## Handoff boundary

No production access, credentials, dealer records, domains, hosting accounts, payment accounts, or customer relationships are transferred by this source package. The receiving maintainer must establish their own accounts, test tenants, providers, policies and operational ownership.
