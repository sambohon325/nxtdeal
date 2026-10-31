# NXTDeal community handoff

**Prepared October 31, 2026.** This document transfers project context to a future community maintainer. It reflects a review of a single source snapshot, not an assurance that every branch or deployment matches it.

Public repository: [github.com/sambohon325/nxtdeal](https://github.com/sambohon325/nxtdeal). The current `main` is a clean, history-free snapshot created from upstream `dealerOS` `main` at `ee722ed4a59185d48e939a48614167c3e113097c`, without copying its history or other branches.

## Project summary

NXTDeal is a dealership operations platform evolved from DealerOS. The intended product spans Sales, Marketing, Inventory, Service, Finance, Operations and Administration, with dealer apps, a platform Hub, integrations, audit/governance, and Chrono decision-support components. Legacy names and domains remain in code and configuration.

The main application architecture is a Python/FastAPI backend (`backend/`), Next.js/React frontend (`frontend/`), and Hub/control-plane services (`hub/`). The application currently has both direct FastAPI route wiring and router modules. Business logic is spread across `backend/core/` and `backend/api/routers/`; follow local patterns when making changes.

The legacy graph model stores dealership entities and relationships. JSON files and subsystem stores remain active compatibility surfaces. A repository abstraction and PostgreSQL schema work exist in the development history, but the available docs do not establish that PostgreSQL replaced JSON as runtime authority. Do not assume a completed database cutover.

## Snapshot selected for this package

- Upstream repo: `https://github.com/sambohon325/dealerOS`.
- Selected commit: `ee722ed4a59185d48e939a48614167c3e113097c` on `main`, dated October 26, 2026.
- The GitHub repository was private when inspected. Its default branch was unprotected and many development branches were present.
- This package deliberately excludes private `.git` history and branches, internal build diaries/evidence, tracked `backend/data/` CSV files, editor instruction files, and private deployment/AI automation workflows. It keeps the coherent tree from one commit and makes no claim that this is the only relevant NXTDeal work. Separate streams such as Chrono Lab, templates, desktop, compliance, security and marketing may have later or independent changes that are not included.

## State and expectations

The project is an unfinished, broad product with incomplete workflows, integrations and release gates. Existing readiness notes contain dated candidate evidence, not a guarantee that the current snapshot is accepted or deployed. This package has not been validated by a clean install, full test run, browser acceptance, comprehensive security audit, or deployment rehearsal.

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
