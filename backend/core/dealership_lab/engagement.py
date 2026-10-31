"""Staff engagement policy and bounded, non-financial achievements.

One tenant per graph, one profile per authenticated employee. Exploration is
explicitly client-reported; verified work continues to use canonical workflows.
"""
from copy import deepcopy
from fastapi import HTTPException
from . import service as lab

KIND = 'StaffRewardsPolicy'
AREAS = ('Operations', 'Sales', 'BDC', 'Marketing', 'Inventory', 'Service',
         'Finance', 'Readiness', 'Network', 'Administration', 'Marketplace')


def policy():
    entity = next(iter(lab.items(KIND)), None)
    return deepcopy(entity.attributes) if entity else dict(enabled=True, disabled_users=[], revision=0)


def enabled(actor):
    p = policy()
    return p['enabled'] and actor not in p['disabled_users']


def enabled_at(actor, timestamp):
    """Never backfill completions that occurred during a disabled interval."""
    state = dict(enabled=True, disabled_users=[])
    for audit in sorted(lab.items('StaffRewardsPolicyAudit'), key=lambda e: e.attributes['current']['updated_at']):
        change = audit.attributes['current']
        if change['updated_at'] > timestamp:
            break
        state = change
    return state['enabled'] and actor not in state['disabled_users']


def require_enabled(actor):
    if not enabled(actor):
        raise HTTPException(403, 'Staff rewards are disabled for this account')


def update(actor, enabled_value, disabled_users, revision):
    from core.auth import credential_store
    with lab.transaction():
        current = policy()
        if current['revision'] != revision:
            raise HTTPException(409, 'Rewards settings changed. Reload before saving.')
        if any(not credential_store.get_record(user) for user in disabled_users):
            raise HTTPException(422, 'Choose existing staff accounts')
        value = dict(enabled=enabled_value, disabled_users=sorted(set(disabled_users)),
                     revision=revision + 1, updated_by=actor, updated_at=lab.now().isoformat())
        entity = next(iter(lab.items(KIND)), None)
        if entity:
            entity.attributes = value
        else:
            lab.create('RWP', KIND, value)
        lab.create('RWA', 'StaffRewardsPolicyAudit', dict(previous=current, current=value))
        return value


def journey(actor):
    profile = lab.profile(actor)
    p = profile.attributes if profile else {}
    return dict(enabled=enabled(actor), explored=p.get('explored', []),
                active_days=len(p.get('engagement_days', [])),
                milestones=[dict(target=n, title=title, xp=xp,
                    complete=f'engagement-days-{n}:lifetime' in p.get('rewards', {}))
                    for n, title, xp in ((3, 'Finding your rhythm', 50), (7, 'A familiar workspace', 100), (20, 'Built into your day', 200))])


def visit(actor, area):
    """One exploration reward per area; at most 20 distinct days, no streak loss.

    No arbitrary XP, entity or employee IDs accepted from the client. Disabled
    periods do not accumulate events or deferred rewards.
    """
    from . import learning
    if area not in AREAS:
        raise HTTPException(422, 'Unknown exploration area')
    with lab.LOCK:
        if not enabled(actor):
            return journey(actor)
        old = lab.profile(actor)
        today = lab.now().date().isoformat()
        p = old.attributes if old else {}
        # Avoid saving the entire graph for unchanged background pulses.
        work = learning.work_milestones(actor)
        needs_work = any((w['eligible'] and not w['complete']) or (w['weekly_eligible'] and not w['weekly_complete']) for w in work)
        days = p.get('engagement_days', [])
        if area in p.get('explored', []) and (today in days or len(days) >= 20) and not needs_work:
            return journey(actor)
        with lab.transaction():
            p = lab.profile(actor, True).attributes
            rewards = p['rewards']
            explored = p.setdefault('explored', [])
            if area not in explored:
                explored.append(area)
                key = 'explore-' + area.lower()
                rewards.setdefault(key + ':lifetime', dict(id=key, period='lifetime',
                    title='Explore ' + area, xp=25, created=lab.now().isoformat(),
                    basis='Client-reported active exploration; not work verification'))
            days = p.setdefault('engagement_days', [])
            if today not in days and len(days) < 20:
                days.append(today)
            for n, title, xp in ((3, 'Finding your rhythm', 50), (7, 'A familiar workspace', 100), (20, 'Built into your day', 200)):
                if len(days) >= n:
                    key = f'engagement-days-{n}'
                    rewards.setdefault(key + ':lifetime', dict(id=key, period='lifetime',
                        title=title, xp=xp, created=lab.now().isoformat(),
                        basis='Distinct UTC days of active exploration; no consecutive-day requirement'))
            learning.work_milestones(actor, claim=True, recurring=True)
        return journey(actor)


def on_work_completed(actor):
    """Best-effort post-commit award; rewards must never fail a work completion.

    The foreground reconciler retries a failed award from canonical records.
    Automation identities and customer accounts never receive staff rewards.
    """
    import logging
    from core.auth import credential_store
    from . import learning
    account = credential_store.get_record(actor) or {}
    if account.get('role') not in {'ADMIN','OPERATIONS','SALES','MARKETING','SERVICE','FINANCE','BDC'}:
        return
    try:
        with lab.LOCK:
            if not enabled(actor):
                return
            work = learning.work_milestones(actor)
            if not any((w['eligible'] and not w['complete']) or (w['weekly_eligible'] and not w['weekly_complete']) for w in work):
                return
            with lab.transaction():
                learning.work_milestones(actor, claim=True, recurring=True)
    except Exception:
        logging.getLogger(__name__).exception('Staff rewards reconciliation deferred; workflow remains complete')
