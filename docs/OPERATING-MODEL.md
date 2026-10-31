# DealerOS — Operating Model & Path to Market
**Authored 2026-08-03. This is the governing doc: every recurring Cowork task reads it first.**

---

## 0. The honest read

DealerOS is not a prototype in the "unfinished software" sense. The feature surface is extraordinary
for a system this young: ~10,875 passing backend tests, a full deal lifecycle, BHPH loan servicing,
13 AI workforce roles, an eight-slice digital-retail journey, a seven-app mobile suite, a 93-listing
marketplace, a self-serve freemium tier with real entitlement enforcement, a Hub that provisions a
dealer's entire stack in Coolify with one click, and a marketing site with six industry pages.
Most companies would call that a product.

It is a prototype in a different and more specific sense: **nothing under it is load-bearing yet.**

Five structural gaps stand between where DealerOS is today and something a real dealership can run
their month on. None of them are features. All five are fixable.

| # | Gap | Why it ends a pilot |
|---|---|---|
| 1 | **Durability** — the ledger is a single JSON file per tenant, rewritten whole on every save. No database, no transactions, no concurrency control, no backups, no point-in-time recovery. | The product promise is *"a single ledger to run the dealership."* A crash mid-write, or two writers at once, corrupts that ledger with no way back. This is the one that doesn't just embarrass you — it ends the company. |
| 2 | **Verification** — no CI. Tests run only when an agent runs them in an ephemeral container. `next build` has never run in the loop (only `tsc --noEmit`). Deploys are manual. 30 stale count-guardrail tests have been failing so long they're treated as background noise. | There is no automated gate between "an agent wrote it" and "it's live at dealer1." The 30-failure baseline means a real regression can hide in plain sight. |
| 3 | **The last hop is simulated** — telephony, e-sign, credit bureau, payments, email/SMS, enrichment, DMS/CRM. | Architecturally this is *already solved* — the integration seam is genuinely good design, and connecting a provider flips a capability live with no code change. Commercially it is unsolved: every customer-visible promise currently ends in a simulation. This is a credentials problem, not a build problem. |
| 4 | **Compliance** — the system pulls credit, stores consumer PII, texts and calls consumers, e-signs retail contracts, services BHPH loans, and computes payroll withholding with an explicitly simplified tax model. | FCRA, GLBA, TCPA, ESIGN/UETA, state lending and licensing, and payroll tax are not code-quality issues — they are liability. No human who carries that liability has reviewed any of it. |
| 5 | **Operability** — no error monitoring, no uptime alerting, no log aggregation, no staging environment, no rollback rehearsal, no support runbook, no on-call. | When an F&I manager can't fund a deal at 6pm Saturday, nobody finds out until Monday. |

Everything in this document is organized around closing those five, in that order, without stopping
feature work.

---

## 1. The operating model

### Who decides what

**Claude (Cowork)** — builds, tests, audits, documents, and monitors. Default posture is autonomous
on anything reversible and covered by tests. Opens PRs; never pushes to `main`. Maintains the living
backlog and the release-readiness ledger in this project.

**Sam** — sets priority and scope, holds every credential, approves merges, owns the pilot dealer
relationship, and makes the calls listed in §6. The only person who can unblock a credential gate.

**October 1, 2026 owner clarification:** Sam is the sole approver; there is no separate developer review team. His explicit approval authorizes release work, with relevant checks and verified readiness still required. The earlier separate-developer gate below is superseded by this clarification.

**Earlier model (superseded): NXTDeal dev team** — a *review gate on a defined list*, not a bottleneck on everything. If they
review everything, they become the throttle and the velocity advantage evaporates.

### Review tiers — the important part

| Tier | Scope | Gate |
|---|---|---|
| **0** | Docs, marketing copy, tests, seed data, presentational frontend | Auto-merge on green CI |
| **1** | New modules, boards, routes using existing auth patterns; feature wiring | Sam approves, green CI |
| **2** | **Money math** (deals, payments, payroll, negotiation gross, loan servicing) · **auth/tokens/tenancy** · **the storage layer** · **entitlement enforcement** · **public unauthenticated routes** · **credential handling** | Sam approval required, green CI and verified release readiness |
| **3** | FCRA/GLBA/TCPA posture, payroll tax engine, lending compliance, retail contract templates, ToS/DPA | External professional. Not a code review. |

Tier 2 is the list that protects you. It's short on purpose — roughly 15% of PRs — so the devs can
actually hold it.

### Cadence

- **Nightly** — build agent works the top of the hardening backlog, opens a PR per slice.
- **Weekday morning** — readiness brief: what shipped, what broke, host health, what needs Sam today.
- **Saturday** — adversarial QA sweep over the week's diff.
- **Monday** — roadmap review: re-score the backlog against the active gate, flag scope creep.

---

## 2. Delivery pipeline — the change

**Today:** cloud container → `.tgz` → Sam's Downloads → extract → commit → push → manual Coolify
deploy. Plus a second autonomous builder committing to the same `main`.

That loop is the throttle. It caps overnight work at zero, and two autonomous agents on one branch is
a drift factory — the handoff doc already carries a whole subsection of workarounds for it.

**Target:**

```
Claude → branch claude/<slice> → PR → GitHub Actions CI → review tier → merge main
      → Coolify auto-deploy staging → smoke check → promote to dealer1 / apps / hub
```

Concretely:

1. **Fine-grained GitHub PAT**, scoped to `sambohon325/dealerOS` + the Hub repo, permissions
   *Contents: read/write* and *Pull requests: read/write* only. 90-day expiry. **No admin, no
   workflow-write, no org scope.** Verified today: the container reaches `api.github.com` fine and
   `git` is present, so this works the moment the token exists.
2. **Branch protection on `main`** — no direct pushes (including from the other builder), CI required,
   one approval required.
3. **GitHub Actions CI** on every PR: backend `pytest`, frontend `tsc --noEmit`, frontend
   `next build`, and a **regression gate** that compares failures against a committed baseline file
   rather than a hardcoded number.
4. **Give the concurrent autonomous builder its own branch**, or retire it. Two agents, one `main`,
   no CI is the single most likely source of a silent production break.
5. **A staging tenant** — `staging-api` / `staging-frontend` Coolify apps off a `staging` branch.
   There is no staging today; dealer1 is effectively production *and* test.

### On where the token lives

Scheduled tasks start fresh sessions with no persistent secrets, so the token has to be stored
somewhere the task can read. Put it in **the scheduled task's own prompt**, not in a project doc —
project docs are visible across the whole project and to anyone on the team. A fine-grained,
two-repo, 90-day, contents+PR-only token is a proportionate risk envelope. Rotate it on the expiry.
If that's not acceptable, the fallback is that overnight tasks prepare branches as patch files and
you push in the morning — still better than today, but it loses CI-on-PR.

---

## 3. Staged launch gates

You chose all three, staged. Here are the exit criteria. A gate is passed when every line is true —
not when it feels close.

### Gate A — First paying pilot dealer live · target 4–6 weeks

- [ ] Ledger durability: atomic writes + file locking shipped; **nightly offsite backup with a
      rehearsed restore** (a restore you have actually performed, not a script you believe works)
- [ ] Persistence decision made and in flight (§4, H4)
- [ ] CI green-gate on `main`; staging tenant live; **rollback rehearsed**
- [ ] Real providers live: SMS/voice, transactional email, e-signature, card/ACH payments
- [ ] Error monitoring + uptime alerting on every deployed host; log retention ≥ 30 days
- [ ] Support runbook + escalation path + a **named human on call**
- [ ] The pilot dealer's real data migrated from their incumbent DMS/CRM and reconciled by them
- [ ] TCPA consent captured on every outbound channel; ESIGN consent + disclosure on the e-sign flow;
      credit-app data handling reviewed by counsel
- [ ] Signed pilot agreement with explicit beta language and a stated data-loss liability position
- [ ] The 30 stale test failures are gone — baseline is genuinely green

### Gate B — NXTDeal sales-led franchise launch · target +6–8 weeks

- [ ] Two more dealers live with **zero per-dealer code**
- [ ] Hub auto-provisioning proven end-to-end on a real dealer (built in `c80ff47`/`c5ef034`, never
      exercised on a live paying tenant)
- [ ] Per-tenant backup + self-service restore
- [ ] Real credit bureau connector (Experian / 700Credit / RouteOne) with FCRA permissible-purpose
      handling
- [ ] DMS/CRM connectors for the two incumbents your pilots actually run
- [ ] A security posture doc that answers a franchise IT questionnaire; SOC 2 Type I started
- [ ] Payroll: real tax engine (Symmetry/Avalara) **or** payroll shipped disabled and marked
      non-authoritative. The current simplified withholding model must not compute a real paycheck.

### Gate C — Public self-serve · target +3 months after B

- [ ] Stripe billing end-to-end: signup → charge → provision → dunning → downgrade → cancel, with
      entitlement enforcement actually enforcing
- [ ] Abuse controls: bot protection on `/public/signup`, rate limits, per-tenant resource caps
- [ ] **Tenant density economics solved.** One Coolify app pair per dealer does not scale to hundreds
      of free Foundation tenants — 500 signups is 1,000 containers. This needs an architecture
      decision *before* the Start Free button gets traffic, not after.
- [ ] Self-service support: docs, in-product help, ticketing
- [ ] Legal: ToS, DPA, privacy policy, state lending disclosures, CCPA/CPRA handling
- [ ] The inactivity lifecycle sweep wired to a real cron and observed working for a full cycle

---

## 4. The two-week production-hardening backlog

Ordered. Each is one PR. Each is independently shippable.

| # | Slice | Why it's here | Tier |
|---|---|---|---|
| **H1** | **CI + honest baseline.** GitHub Actions running pytest + tsc + `next build`. Rewrite the 30 stale count-guardrails to derive counts instead of hardcoding them. Commit a failure-baseline file the gate compares against. | Unblocks everything else. Until the baseline is truthful, no other verification means anything. | 1 |
| **H2** | **Atomic ledger writes.** `save_graph` writes to a temp file and renames; add file locking; add a crash-safety test that kills mid-write and asserts the prior graph survives. | Cheapest possible fix for the single worst risk. Hours of work, removes the corruption class entirely. | **2** |
| **H3** | **Backups + restore drill.** Per-tenant snapshot to object storage on a schedule, a restore command, and a documented drill actually performed against a copy of dealer1. | "We have backups" is worthless until a restore has been performed. | **2** |
| **H4** | **Persistence design spike.** Evaluate Postgres vs SQLite-per-tenant behind the existing storage abstraction; write the migration path. The `core/storage` module is already the right seam — this is a design doc plus a spike, not a big-bang rewrite. | The JSON graph will not survive a dealership's real entity volume or a year of audit history. Decide now, migrate before Gate B. | **2** |
| **H5** | **Observability.** Sentry on backend + frontend, structured logging, `/health` on every service, uptime checks on all deployed hosts with alerting to Sam's phone. | You currently learn about outages from customers. | 1 |
| **H6** | **Staging + rollback.** `staging` branch → staging Coolify apps; document and rehearse a Coolify rollback. | dealer1 is production and test at the same time. | 1 |
| **H7** | **Secrets audit + rotation.** Confirm nothing sensitive is in the repo; rotate `DEALEROS_AUTH_SECRET` and `DEALEROS_NETWORK_KEY`; verify credential stores are encrypted at rest (they're correctly outside the graph already). | Pre-pilot hygiene; also the first thing a franchise IT questionnaire asks. | **2** |
| **H8** | **Tenancy isolation adversarial pass.** Cross-tenant leakage across Hub↔tenant, the `apps.dealeros.xyz` API-base override, customer-vs-employee token domains, network benchmark k-anonymity, and the flagged staff min/max leak. | Two audits found real PII leaks already (revoked PURL, kiosk state, benchmark reconstruction). Multi-tenancy is where the next one lives. | **2** |
| **H9** | **Close the flagged gaps.** Digital Retail "I'm interested" → actually start a deal (needs your routing decision, §6), staff network-analytics k-floor, `apps.dealeros.xyz` root → `/apps` redirect. | Known-open items sitting in the audit docs. | 1 |
| **H10** | **Frontend build truth.** Fix the pre-existing `@/types/artifacts` errors so "typecheck clean" means clean, and get `next build` green in CI. | "Clean except for the known errors" is how real errors hide. | 1 |

H1 and H2 should land first and can land the same day the token does.

---

## 5. Project hygiene — a recommendation

The 14 project docs are append-style session logs, and `DealerOS-Migration-Handoff.md` has grown into
a ~30KB document that every session pays a context tax to read. It's excellent institutional memory
and terrible working memory.

Proposed restructure:

- **`OPERATING-MODEL.md`** *(this doc)* — governing. Read first by every recurring task.
- **`RELEASE-READINESS.md`** — living checklist of the three gates, updated by the Monday review.
- **`BACKLOG.md`** — living, ordered, one line per slice with tier and status. Updated nightly.
- **`ARCHITECTURE.md`** — the durable facts from the handoff doc: conventions, module patterns, entity
  prefixes, the seam, name collisions, the invariants. The stuff that's true regardless of session.
- **`archive/`** — every session log and audit as-is, searchable, never read whole.

This is a 30-minute job and it pays back every single session afterward.

---

## 6. Decisions only Sam can make

1. **GitHub token** — issue it, or choose the patch-file fallback.
2. **The concurrent autonomous builder** — branch it or retire it.
3. **Persistence** — approve a Postgres migration in principle (H4 produces the proposal; the decision
   is a cost and timeline commitment).
4. **Provider accounts** — which to open this week. Ranked by pilot impact:
   telephony (Twilio) → e-sign (Dropbox Sign is cheapest to start) → email (Postmark/SendGrid) →
   payments (Stripe) → credit bureau (longest lead time, start the application now).
5. **Payroll** — real tax engine, or ship it disabled? It currently computes paychecks with an
   explicitly simplified withholding model. Shipping that to a real dealer is a tax liability.
6. **Digital Retail post-verification routing** — after a customer verifies identity from "I'm
   interested," what should happen? Build a deal room, reserve the vehicle, or hand to a rep?
   (Flagged in the pass-2 audit as a wiring gap deliberately left undecided.)
7. **Pilot dealer** — who, and when do they start? Everything in Gate A is scoped to a real store's
   real workflow; without a named dealer the criteria stay abstract.
8. **Compliance counsel** — who reviews Tier 3. This needs to start now; it has the longest lead time
   of anything on this page.

---

## 7. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Ledger corruption on a live dealer | Medium | **Catastrophic** | H2 + H3, this week |
| Silent regression reaches production | High | High | H1 CI gate + branch protection |
| Two autonomous builders collide on `main` | High | Medium | Branch or retire the second builder |
| Compliance exposure (FCRA/TCPA/lending) | Medium | **Catastrophic** | Tier 3 counsel engaged now |
| Provider credentials block Gate A | High | High | Start applications this week; bureau first |
| Public self-serve traffic outruns per-dealer container model | Medium | High | Gate C blocker; decide before the Start Free button gets ad spend |
| Scope creep — the feature surface keeps growing while the foundation doesn't | **High** | High | The Monday roadmap review exists specifically to catch this |

That last one is worth saying plainly. The pattern in the project history is a new initiative every
session — Connect, Digital Retail, App Suite, Marketplace, Demo Platform, Freemium, Marketing,
Competitive Roadmap — each one built well and completely. The instinct to build is not the problem.
The problem is that none of those initiatives made the ledger durable, and the ledger is the product.

For the next two weeks, the answer to "should we build X" is no.
