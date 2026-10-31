# Public release checklist

This checklist is specific to the review snapshot `ee722ed4a59185d48e939a48614167c3e113097c`. It records the project handoff state, not a production-readiness certification. Record completion evidence and owner for every remaining gate.

## Scope and ownership

- [x] Select a single core-app snapshot from `main`; separate Chrono Lab, desktop, template studio, marketing, compliance and other workstreams are not included unless present in this snapshot.
- [ ] Confirm all code contributors and copyright holders may license the included work. Review contribution and employment/contract ownership where applicable.
- [x] Select MIT for the original software source and text documentation. The repository owner requested a recommendation; MIT is the permissive, low-friction choice for a community handoff. Choose AGPL-3.0 instead only if the project specifically wants service operators who modify it to provide source to users.
- [x] Add `LICENSE` for the original software source and text documentation. Third-party packages follow their own licenses; `frontend/public/` media/brand assets are explicitly excluded by `ASSET-NOTICE.md`.

## Data and secrets

- [x] Sanitize the seed generator contact values and replace the identified bridge conformance fixture email with `customer@example.com`; inspect remaining fixtures and assets before future releases.
- [ ] Keep `backend/data/` omitted unless its complete provenance and fictional nature are established.
- [ ] Scan the complete release tree and intended Git history with a maintained secret scanner. This package received only a limited custom pattern scan; no dedicated secret-scanning tool was available during preparation.
- [ ] Recheck excluded runtime stores, backups, credentials, `.env` files, database files, logs, and attachments; do not add local operational data.
- [ ] Review URLs, screenshots, support logs, sample credentials and workflow artifacts for private infrastructure/account details.

## Copyright and dependencies

- [ ] Inventory `frontend/public/` and all binary/media assets. The assets remain in the public source tree for project continuity but are excluded from the MIT grant until redistribution rights are confirmed. Remove any item that should not remain publicly visible.
- [ ] Review `backend/chrono/shared/` against its private upstream Chrono repository and select a public provenance/license strategy. Ensure the manifest and notices remain accurate.
- [ ] Generate a dependency/license inventory for Python, npm, fonts and bundled assets; resolve incompatible or missing notices.
- [ ] Review trademark use and distinguish project branding from third-party marks.

## Quality and operations

- [ ] Add a public root README with clean-machine install, safe demo run, architecture links, supported environment, and known limitations.
- [ ] Reproduce the synthetic Docker Compose stack from a clean checkout and verify it cannot reach production or external delivery providers by default.
- [ ] Run the intended backend, Hub, frontend, database/import and container checks against this exact snapshot; publish pass/fail summaries and logs with secrets/PII removed.
- [ ] Review current security and compliance claims; remove stale or overbroad claims and state the project is not certified or production-supported unless separately evidenced.
- [x] Enable private vulnerability reporting and vulnerability alerts. Verify that notifications reach a monitored maintainer.
- [ ] Configure branch protection, CI, CODEOWNERS or clear maintainer ownership, issue templates and a release policy.
- [ ] Mark the project accurately as community-maintained / looking for maintainers and state support expectations.

## GitHub publication

- [x] Create a new public repository, [`sambohon325/nxtdeal`](https://github.com/sambohon325/nxtdeal), rather than changing the existing private `dealerOS` repository to public.
- [x] Prepare one history-free snapshot; private Git history and development branches are not copied.
- [x] Exclude `sources/`, private project instructions, local evidence/build diaries, `backend/data/` dealer CSVs, private domain routing configs, deployment/internal release docs, private planning docs, and the identified non-synthetic fixture email.
- [x] Inspect the package for high-confidence secret patterns; the limited scan found none. It is not a full historical secret scan.
- [x] Inspect the final public file list for excluded development history and data. The repository uses the MIT license for original source and text documentation; public media assets are excluded from that license grant.
- [x] Enable GitHub private vulnerability reporting and vulnerability alerts.
- [x] Remove the inherited Coolify deployment workflow and private AI review/nightly workflows; retain CI and security checks.
- [ ] Finish clean-machine build/tests, asset rights catalog, contributor/copyright review, and maintainer ownership process.

