# NXTDeal

NXTDeal is an automotive dealership operations platform developed from the DealerOS codebase. The project brings dealership departments and workflows into a shared workspace, with a FastAPI/Python backend, a Next.js/React frontend, a dealer administration Hub, and a separately developed Chrono decision-support component.

The project is being prepared for community stewardship. Its original developer is ending active development. This repository snapshot is a substantial work in progress; it is not a supported commercial service or a production-ready deployment. Features, integrations, security controls and documentation vary in completeness. See `PUBLIC-RELEASE-CHECKLIST.md` for release caveats and `COMMUNITY-HANDOFF.md` for the current handoff map.

## Repository map

- `backend/` — FastAPI application, dealership domain logic, API routers, and tests.
- `frontend/` — Next.js application and user interfaces.
- `hub/` — dealer administration and platform services.
- `deploy/`, `compose.synthetic.yaml` — deployment material, including an isolated synthetic rehearsal stack.
- `docs/` — selected product and technical documentation. Some internal development journals and evidence were intentionally left out of this release copy.
- `backend/chrono/shared/` — vendored/shared Chrono source pinned by the included manifest; licensing and provenance must be reviewed before publication.

## Getting started

The source includes separate backend and frontend applications plus a synthetic Docker Compose stack. That stack is designed for an isolated fictional dealership and binds its published ports to loopback. Review `compose.synthetic.yaml` and the Dockerfiles before running it. The package has not yet had a clean-machine build or test run, so the steps and dependency versions still need community validation before this README can be called a verified setup guide.

For development, the backend entrypoint is `backend/api/app.py` and the frontend package is under `frontend/`. Each component has its own dependency manifest and README. Do not point a local experiment at a real dealership database or enable customer delivery, payments, lender actions, or outbound messaging.

## Data and integrations

The sample seed generator in `backend/imports/generate_seed_data.py` creates fictional records. This release copy was adjusted to use `example.com` addresses and reserved 555-0100–0199 phone numbers. Never use production exports or real customer/staff data as fixtures. Real integrations require credentials and operational review that are not included here.

## License

Original software source and text documentation in this snapshot are released under the MIT License; see `LICENSE`. The media, font, logo, and artwork files under `frontend/public/` are excluded from that grant and remain with their respective rights holders. NXTDeal and third-party trademarks are not granted by the software license. See `ASSET-NOTICE.md`.

## Community status

The project is being handed off to volunteers or another maintainer. No response-time, security-fix, uptime, or compatibility commitment is made. Community contributors should open focused issues and pull requests; please review `CONTRIBUTING.md` and `SECURITY.md` first.
