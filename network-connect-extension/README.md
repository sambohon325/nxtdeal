# DealerOS Network Connect -- browser extension

A free-tier Chrome/Edge extension implementing Sam's "Give Value -> Collect
Data -> Create Insight -> Create Dependency -> Upgrade To DealerOS" flywheel.
No build step -- plain Manifest V3 HTML/CSS/JS, loaded straight from this
directory.

## What it does

- **Sign up** with just a company name and email -- no CRM/DMS connection
  required. Creates a real `NetworkConnectAccount` on the NXTDeal Hub and
  mints two secrets, shown exactly once: an `account_token` (identifies you)
  and a `pseudonym` (anonymizes your KPI submissions -- NXTDeal can never
  join the two back together, by design; see
  `hub/core/network_connect.py`'s own module docstring).
- **Connectors tab** -- self-report which CRM/DMS/Website/Marketing/Service
  platform you use today (no real OAuth/login to any of them happens here;
  see "What this does NOT do" below).
- **Submit KPIs tab** -- enter real monthly numbers (close rate, gross
  profit, RO count, inventory age, etc.). Values are bucketed (rounded) both
  client-side intent and server-side before storage, so a submission is
  never precise enough to be personally identifying.
- **Dashboard tab** -- your real percentile rank across the DealerOS
  Network, your top real opportunities (with a real dollar estimate where
  the KPI is currency-denominated), and a real, rule-based daily brief.
  Root-cause/recommended-action detail is gated behind the `premium` tier
  (set by NXTDeal staff via the Hub console) -- the free tier sees an honest
  locked teaser instead of fabricated insight.

## What this does NOT do (by design, not an oversight)

No real OAuth or live data pull from any of the 23 named providers
(VinSolutions, CDK, DealerOn, Google, Xtime, etc.) happens anywhere in this
extension or its backend. Building real connector integrations for each one
needs real developer credentials NXTDeal doesn't have yet -- Sam's own
original spec scoped that as its own, separate, later "Connector framework"
slice. The Connectors tab is honest self-reported tracking only, useful for
Migration Readiness conversations, not a live data feed.

## Install (developer / unpacked)

1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable "Developer mode" (top right).
3. Click "Load unpacked" and select this `network-connect-extension/`
   directory.
4. Click the extension icon in your toolbar to open the popup.

## Configuring the API endpoint

By default the extension talks to `http://127.0.0.1:9000` (the Hub's own
dev port -- see `docs/DEPLOYMENT.md`'s app table, `hub-api`). Change this
under the signup screen's "API endpoint (advanced)" section, or later under
Settings, to point at a real deployment (e.g.
`https://hub-api.dealeros.xyz`).

## Data stored locally

`chrome.storage.local` only, on this device: `nc_account_id`,
`nc_account_token`, `nc_pseudonym`, `nc_company_name`, `nc_api_base`. Never
synced, never sent anywhere except as the credential values the Hub's own
`/network-connect/*` routes expect. "Sign out" in the popup clears all of
these (the account itself still exists on the Hub -- signing back in isn't
possible without re-entering the account_token/pseudonym by hand, since
neither is ever shown again after signup; this is the same one-time-secret
tradeoff `backend/core/api_keys.py`'s API keys already make).

## Backend

Every route this extension calls already exists and is live-verified end to
end (a real `TestClient` smoke test, `hub/core/network_connect_api.py` +
`hub/app.py`) -- see `CLAUDE.md`'s "DealerOS Network Connect" section for
the full build writeup.
