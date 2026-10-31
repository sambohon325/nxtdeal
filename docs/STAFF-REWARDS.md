# Staff achievements and rewards

Staff rewards use the existing private DealershipLabProfile in the tenant graph. They never add customer loyalty points, affect permissions, or change business KPIs.

## Earning and coverage

- Main CommandCenter: Operations, Sales, BDC, Marketing, Inventory, Service, Finance, Readiness, Network, Administration and Marketplace. Exploration earns 25 XP once per area after a foreground dwell with recent activity. Server checks department access. This is explicitly client-reported exploration, not proof of work.
- Authenticated staff AppShell apps share the same profile and map to Sales or Service. Personal MySales and customer My Garage do not emit staff events.
- Return milestones: 50 / 100 / 200 XP at 3 / 7 / 20 distinct UTC days. No consecutive streak, decay, missed-day penalty or repeat reward.
- Existing knowledge checks, reviewed Lab sections and substantive scenario comparisons continue to earn their existing rewards.
- Verified linked WorkflowInstance and WorkflowInstanceV2 completions: 150 XP once per department, plus 50 XP per department per current UTC week. Attribution uses the completing employee, canonical workflow definition, final history entry, completed stages/steps and real linked source. Cancelled, forced or unlinked completions do not count.
- Both workflow engines award immediately after persisting successful completion. A foreground pulse retries reconciliation of eligible work at most once per minute after recent interaction. Extras retains manual reconciliation. Raw clicks, arbitrary API calls, message sends and high transaction volume do not award work XP.
- Server reward identities deduplicate concurrent tabs, retries, repeated visits and claims. No user-submitted amount, employee ID or work-completion assertion is accepted.

## Administrator controls

Administration > Extras & tools > Progress > Administrator controls. The existing ADMIN role is the full platform administrator in this codebase; there is no separate SUPERADMIN role. Both the current credential role and authenticated role must be ADMIN.

Global off applies to this dealership and overrides individual account checkboxes. Off stops profile/reward writes, pack opening, cosmetics, decks and games through both Extras and legacy Lab endpoints. Lab business/scenario editing remains available without earning. Existing XP is retained; workflow completions during disabled intervals are excluded from later claims.

Policy uses an optimistic revision and persists the actor, timestamp and before/after settings in StaffRewardsPolicyAudit. Existing staff accounts are validated before saving. UI changes propagate within one minute while visible, or upon focus. Backend enforcement is immediate. Disabled clients poll policy without posting exploration. Controls remain reachable by an administrator even if their own rewards are off.

## Experience

No modals, sounds, notification spam, leaderboard, loss aversion or activity-volume incentives. Progress remains in the account menu, staff app Progress and Extras. Rewards failures cannot block core screen interactions. Server-side reward writes remain authoritative even if a stale client still shows controls.

## Validation and rollout

Backend: 165 tests passed across test_staff_engagement.py, test_extras.py, test_dealership_lab.py, test_workflow_engine_v2.py and test_workflow_tracking.py. TypeScript and focused rewards-component ESLint pass; existing broader workspace lint findings remain. Isolated browser preview exercised earning, global off/on, preserved XP and individual exclusion. No production accounts or balances were changed.

Deploy the API changes to codex/department-workflow-audit-20261021 before frontend changes to codex/department-workflow-ui-20261021. These are separate live deployment sources. Existing graph persistence includes the policy and profile; no migration or customer loyalty database change is needed. GitHub runner availability must be checked separately from local tests.

If both the post-completion award and foreground/manual retry fail until a later week, the previous week's optional reward is not backfilled. Only linked canonical workflows qualify as verified work; standalone operations without a workflow are not represented as verified completions.
