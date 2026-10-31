"""Generate the programming-schedule dashboard HTML from live ledger data.

Reusable by both the standalone generator script (gen_dashboard_clean.py at
repo root) and the web API route (GET /programming-schedule/dashboard-view)
so the dashboard is hosted online and visible to the VPS agent.

Usage from API layer:
    from core.dashboard_renderer import render_dashboard_html
    html = render_dashboard_html()
"""
import json
import os
import sys

# Ensure backend/core is importable when run as a standalone script
if __package__ is None or __package__ == "":
    _backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    sys.path.insert(0, _backend_dir)

from core.dealeros import ledger
from core import programming_schedule as ps

_ROUTE_LABELS = {'local': 'Local (Desktop)', 'vps': 'VPS (Tailscale)', 'sam_only': 'Sam Only'}
_OWNER_LABELS = {'auto': 'Auto', 'sam': 'Sam', 'backend': 'Backend', 'frontend': 'Frontend',
                 'devops': 'DevOps', 'sample': 'Sample (Sam)'}

_PHASE_LABELS = {
    'Phase 0': 'AI Config', 'Phase 1': 'CI/Verification', 'Phase 2': 'Companion Apps',
    'Phase 3': 'AI Refactor', 'Phase 4': 'Marketing', 'Phase 5': 'Infrastructure',
    'Phase 6': 'Deployment', 'Phase 7': 'Launch',
}


def _build_item_dict(i):
    """Common item dict for dashboard output, including lease + runs + events."""
    runs = ps.list_runs(item_id=i['id'])
    events = ps.get_events(i['id'])
    active_run = next((r for r in runs if r['outcome'] == 'running'), None)
    return {
        'id': i['id'], 'title': i['title'], 'description': i['description'],
        'type': i['type'], 'phase': i['phase'], 'status': i['status'],
        'priority': i['priority'], 'assignee': i['assignee'],
        'progress': i['progress'], 'est_hours': i['est_hours'],
        'logged_hours': i['logged_hours'], 'security_severity': i.get('security_severity'),
        'depends_on': i.get('depends_on', []),
        'resource_route': i.get('resource_route', 'local'),
        'owner': i.get('owner', 'auto'),
        'claimed_by': i.get('claimed_by'), 'claimed_at': i.get('claimed_at'),
        'lease_expires_at': i.get('lease_expires_at'),
        'work_notes': i.get('work_notes', []), 'resources': i.get('resources', []),
        'run': active_run, 'event_count': len(events),
        'created_at': i.get('created_at'), 'updated_at': i.get('updated_at'),
    }


def _build_dashboard_data():
    """Build the full dashboard data structure from the live ledger."""
    from datetime import datetime, timezone
    dash = ps.get_dashboard()
    items = ps.list_items()
    runs = ps.list_runs()
    active_runs = ps.list_runs(outcome="running")

    # Sort items by phase, then priority, then est_hours
    phase_order = {p: i for i, p in enumerate(ps.PHASES)}
    priority_order = {p: i for i, p in enumerate(ps.PRIORITIES)}
    items_sorted = sorted(items, key=lambda i: (
        phase_order.get(i['phase'], 99),
        -priority_order.get(i['priority'], 2),
        i['est_hours'],
    ))

    # by_phase (with extended item dicts)
    by_phase = {}
    for p in ps.PHASES:
        phase_items = [i for i in items if i['phase'] == p]
        by_phase[p] = {
            'total': len(phase_items),
            'done': len([i for i in phase_items if i['status'] in ('done', 'deployed', 'pushed_live')]),
            'remaining_hours': sum(i['est_hours'] for i in phase_items) - sum(i['logged_hours'] for i in phase_items),
            'total_hours': sum(i['est_hours'] for i in phase_items),
            'logged_hours': sum(i['logged_hours'] for i in phase_items),
            'items': [_build_item_dict(i) for i in phase_items],
        }

    # in_progress — items with claimed_by set (currently being worked)
    in_progress = [_build_item_dict(i) for i in items if i.get('claimed_by') is not None]

    # up_next — top 5 todo items (not sam_only), by phase/priority/hours
    todo_candidates = [i for i in items if i['status'] == 'todo'
                       and i.get('resource_route') != 'sam_only']
    up_next = [_build_item_dict(i) for i in items_sorted if i['id'] in {x['id'] for x in todo_candidates}][:5]

    # blocked_on_sam — sam_only items + blocked items, critical first
    blocked_items = [i for i in items
                     if i.get('resource_route') == 'sam_only' or i['status'] == 'blocked']
    blocked_sorted = sorted(blocked_items, key=lambda i: (-priority_order.get(i['priority'], 2), i['title']))
    blocked_on_sam = [_build_item_dict(i) for i in blocked_sorted]

    # done — completed items with commit links from runs
    done_items = [i for i in items if i['status'] in ('done', 'deployed', 'pushed_live')]
    done_with_commits = []
    for i in done_items:
        d = _build_item_dict(i)
        completed_runs = [r for r in runs if r.get('item_id') == i['id']
                          and r.get('outcome') == 'completed' and r.get('commit_sha')]
        d['last_commit'] = completed_runs[-1]['commit_sha'] if completed_runs else None
        done_with_commits.append(d)
    done = done_with_commits

    # resources — per-worker and per-model summary
    now = datetime.now(timezone.utc)
    mtd_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    workers_summary = {}
    models_summary = {}
    total_cost_mtd = 0.0
    total_tokens_mtd = 0
    for r in runs:
        worker = r.get('worker', 'unknown')
        provider = r.get('provider', 'unknown')
        model = r.get('model', 'unknown')
        cost = r.get('cost_usd', 0.0)
        in_tokens = r.get('input_tokens', 0)
        out_tokens = r.get('output_tokens', 0)
        cache_tokens = r.get('cache_read_tokens', 0)
        started = r.get('started_at', '')

        # MTD filter
        if started and started >= mtd_start.isoformat():
            total_cost_mtd += cost
            total_tokens_mtd += in_tokens + out_tokens + cache_tokens

        if worker not in workers_summary:
            workers_summary[worker] = {
                'runs': 0, 'runs_completed': 0, 'runs_running': 0,
                'input_tokens': 0, 'output_tokens': 0, 'cache_read_tokens': 0,
                'cost_usd': 0.0,
            }
        w = workers_summary[worker]
        w['runs'] += 1
        if r.get('outcome') == 'running':
            w['runs_running'] += 1
        elif r.get('outcome') == 'completed':
            w['runs_completed'] += 1
        w['input_tokens'] += in_tokens
        w['output_tokens'] += out_tokens
        w['cache_read_tokens'] += cache_tokens
        w['cost_usd'] = round(w['cost_usd'] + cost, 6)

        model_key = f"{provider}/{model}" if provider else model
        if model_key not in models_summary:
            models_summary[model_key] = {
                'runs': 0, 'input_tokens': 0, 'output_tokens': 0,
                'cache_read_tokens': 0, 'cost_usd': 0.0, 'free': True,
            }
        m = models_summary[model_key]
        m['runs'] += 1
        m['input_tokens'] += in_tokens
        m['output_tokens'] += out_tokens
        m['cache_read_tokens'] += cache_tokens
        m['cost_usd'] = round(m['cost_usd'] + cost, 6)
        if provider and ':free' not in provider and not str(model).startswith('local'):
            m['free'] = False

    # Target date: December 1, 2026
    target_date = "2026-12-01"
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_left = (target - now).days
    except Exception:
        days_left = 0

    total_est = sum(i['est_hours'] for i in items) or 1
    total_logged = sum(i['logged_hours'] for i in items)
    pct_done = round((total_logged / total_est) * 100, 1)

    output = {
        'dashboard': dash,
        'by_phase': by_phase,
        'phase_order': list(ps.PHASES),
        'route_labels': _ROUTE_LABELS,
        'owner_labels': _OWNER_LABELS,
        'route_counts': {r: len([i for i in items if i.get('resource_route') == r])
                         for r in ['local', 'vps', 'sam_only']},
        'in_progress': in_progress,
        'up_next': up_next,
        'blocked_on_sam': blocked_on_sam,
        'done': done,
        'active_runs': active_runs,
        'resources': {
            'workers': workers_summary,
            'models': models_summary,
            'mtd_total_cost': round(total_cost_mtd, 6),
            'mtd_total_tokens': total_tokens_mtd,
        },
        'target_date': target_date,
        'days_left': days_left,
        'pct_done_by_hours': pct_done,
        'total_est_hours': total_est,
        'total_logged_hours': total_logged,
    }
    return output


# The embedded JS — uses data attributes + document-level event delegation
# instead of inline onclick handlers (avoids JS quote-escaping bugs).
_JS = r'''const PHASE_LABELS = {Phase 0: "AI Config", Phase 1: "CI/Verification", Phase 2: "Companion Apps", Phase 3: "AI Refactor", Phase 4: "Marketing", Phase 5: "Infrastructure", Phase 6: "Deployment", Phase 7: "Launch"};
const COLORS = {
  type: {feature: "text-blue-400", bug: "text-red-400", security: "text-amber-400", "tech-debt": "text-purple-400"},
  priority: {critical: "bg-red-900", high: "bg-orange-600", medium: "bg-amber-500", low: "bg-gray-600"},
  status: {todo: "bg-gray-500", in_progress: "bg-amber-500", in_review: "bg-purple-500", done: "bg-emerald-500", deployed: "bg-cyan-500", pushed_live: "bg-green-600", blocked: "bg-red-500"}
};
let allItems = [];
let activeFilters = {};

function esc(s) {
  if (!s) return '';
  const d = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};
  return String(s).replace(/[&<>"']/g, c => d[c]);
}
function fmtId(id) { return id ? id.replace('PS-', '') : ''; }
function prioOrder(p) { const o = {critical: 0, high: 1, medium: 2, low: 3}; return o[p] !== undefined ? o[p] : 99; }
function phaseOrder(p) { return data.phase_order.indexOf(p); }
function tLabel(t) { const m = {feature: "Feature", bug: "Bug", security: "Security", "tech-debt": "Tech Debt"}; return m[t] || t; }
function sLabel(s) { const m = {todo: "To Do", in_progress: "In Progress", in_review: "In Review", done: "Done", deployed: "Deployed", pushed_live: "Pushed Live", blocked: "Blocked"}; return m[s] || s; }
function aLabel(a) { const m = {backend: "Backend", frontend: "Frontend", devops: "DevOps", sample: "Sample (Sam)", unassigned: "Unassigned"}; return m[a] || a; }
function rLabel(r) { return data.route_labels[r] || r; }
function oLabel(o) { return data.owner_labels[o] || o; }
function rBadge(r) { const m = {local: "route-badge-local", vps: "route-badge-vps", sam_only: "route-badge-sam_only"}; return m[r] || "bg-gray-600"; }
function rColor(r) { const m = {local: "text-blue-400", vps: "text-purple-400", sam_only: "text-pink-400"}; return m[r] || "text-gray-400"; }
function isCompleted(s) { return s === "done" || s === "deployed" || s === "pushed_live"; }

function renderTopStats(dash) {
  const stats = [
    {label: "Total Items", value: dash.total},
    {label: "Completed", value: dash.completed || 0},
    {label: "Deployed", value: dash.deployed || 0},
    {label: "Pushed Live", value: dash.pushed_live || 0},
    {label: "Remaining Hours", value: (dash.remaining_hours ? dash.remaining_hours + "h" : "0h")}
  ];
  document.getElementById('top-stats').innerHTML = stats.map(s =>
    '<div class="bg-gray-900/50 border border-gray-800 rounded-xl p-5 text-center">' +
    '<div class="stat-value text-blue-400">' + s.value + '</div>' +
    '<div class="stat-label text-gray-500 mt-1">' + s.label + '</div>' +
    '</div>'
  ).join('');
}

function renderPhaseTimeline(dash) {
  document.getElementById('phase-timeline').innerHTML = data.phase_order.map(p => {
    const s = dash.by_phase[p] || {total: 0, done: 0, remaining_hours: 0};
    const pct = s.total > 0 ? Math.round((s.done / s.total) * 100) : 0;
    return '<div class="phase-bg rounded-xl p-4">' +
      '<div class="flex items-center justify-between mb-2">' +
        '<span class="timeline-phase-label text-gray-400">' + esc(p) + '</span>' +
        '<span class="text-xs text-gray-500">' + (PHASE_LABELS[p] || '') + '</span>' +
      '</div>' +
      '<div class="w-full bg-gray-800 rounded-full h-2.5 mb-2">' +
        '<div class="phase-bar h-2.5 rounded-full transition-all duration-500" style="width:' + pct + '%"></div>' +
      '</div>' +
      '<div class="flex justify-between text-xs text-gray-500">' +
        '<span>' + s.done + '/' + s.total + ' complete</span>' +
        '<span>' + pct + '% ' + s.remaining_hours + 'h remaining</span>' +
      '</div>' +
    '</div>';
  }).join('');
}

function renderItemRow(item) {
  const typeCls = COLORS.type[item.type] || 'text-gray-400';
  const priorityCls = COLORS.priority[item.priority] || 'bg-gray-600';
  const statusCls = COLORS.status[item.status] || 'bg-gray-600';
  const rB = rBadge(item.resource_route);
  const rC = rColor(item.resource_route);
  const secBadge = (item.type === 'security' && item.security_severity)
    ? '<span class="ml-1 px-1.5 py-0.5 rounded text-[9px] font-medium bg-red-900/50 text-red-300">' + esc(item.security_severity) + '</span>'
    : '';
  const notesN = (item.work_notes || []).length;
  const resN = (item.resources || []).length;
  return '<div class="item-row ' + esc(item.status) + ' bg-gray-900/30 border border-gray-800 rounded-lg p-3" data-item-id="' + esc(item.id) + '">' +
    '<div class="flex items-start justify-between gap-3">' +
      '<div class="flex-1 min-w-0">' +
        '<div class="flex items-center gap-2 flex-wrap">' +
          '<code class="text-xs text-gray-600">' + esc(fmtId(item.id)) + '</code>' +
          '<span class="' + typeCls + ' text-xs font-medium">' + esc(tLabel(item.type)) + '</span>' +
          '<span class="' + priorityCls + ' text-xs font-medium px-1.5 py-0.5 rounded text-white">' + esc(item.priority) + '</span>' +
          '<span class="' + rB + ' text-xs font-medium px-1.5 py-0.5 rounded text-white">' + esc(rLabel(item.resource_route)) + '</span>' +
          secBadge +
        '</div>' +
        '<div class="mt-1 font-medium text-white">' + esc(item.title) + '</div>' +
        (item.description ? '<div class="mt-1 text-xs text-gray-500">' + esc(item.description) + '</div>' : '') +
        '<div class="mt-1 flex items-center gap-3 text-xs text-gray-500">' +
          '<span class="' + rC + '">to ' + esc(rLabel(item.resource_route)) + '</span>' +
          '<span>owner: ' + esc(oLabel(item.owner)) + '</span>' +
          '<span>' + item.est_hours + 'h est</span>' +
          '<span>' + item.logged_hours + 'h logged</span>' +
          (notesN > 0 ? '<span>N ' + notesN + '</span>' : '') +
          (resN > 0 ? '<span>R ' + resN + '</span>' : '') +
        '</div>' +
      '</div>' +
      '<div class="flex items-center gap-2">' +
        '<span class="text-xs text-gray-400">' + item.progress + '%</span>' +
        '<div class="w-16 h-1.5 bg-gray-800 rounded-full overflow-hidden">' +
          '<div class="' + statusCls + ' h-1.5 rounded-full" style="width:' + item.progress + '%"></div>' +
        '</div>' +
      '</div>' +
    '</div>' +
  '</div>';
}

function renderPhaseItems(byPhase) {
  const phases = Object.keys(byPhase).sort((a, b) => phaseOrder(a) - phaseOrder(b));
  document.getElementById('phase-items').innerHTML = phases.map(p => {
    const pd = byPhase[p];
    if (!pd || pd.total === 0) return '';
    return '<div><h3 class="phase-title text-gray-400 mb-3">' + esc(p) + ' — ' + (PHASE_LABELS[p] || '') + '</h3>' +
      '<div class="space-y-2">' + pd.items.map(renderItemRow).join('') + '</div></div>';
  }).join('');
}

function showDetail(itemId) {
  const item = allItems.find(i => i.id === itemId);
  if (!item) return;
  const typeCls = COLORS.type[item.type] || 'text-gray-400';
  const priorityCls = COLORS.priority[item.priority] || 'bg-gray-600';
  const rB = rBadge(item.resource_route);
  const wc = {backend: 'text-blue-400', frontend: 'text-pink-400', devops: 'text-green-400', sample: 'text-purple-400', unassigned: 'text-gray-400'}[item.assignee] || 'text-gray-400';
  const workNotesHtml = (item.work_notes || []).length > 0
    ? item.work_notes.map(n =>
        '<div class="ml-4 border-l-2 border-gray-700 pl-4 py-2">' +
          '<div class="text-xs text-gray-500">' + new Date(n.timestamp).toLocaleString() + '</div>' +
          '<div class="text-sm text-gray-300 mt-1">' + esc(n.note) + '</div>' +
        '</div>'
      ).join('')
    : '<div class="text-sm text-gray-600 italic">No work notes yet.</div>';
  const resourcesHtml = (item.resources || []).length > 0
    ? item.resources.map(r => '<code class="text-xs bg-gray-800 px-2 py-1 rounded block mb-1 break-all">' + esc(r) + '</code>').join('')
    : '<span class="text-sm text-gray-600 italic">No resources attached.</span>';
  const dependsHtml = (item.depends_on || []).length > 0
    ? (item.depends_on || []).map(d => '<code class="text-xs bg-gray-800 px-2 py-1 rounded mr-2">' + esc(fmtId(d)) + '</code>').join('')
    : '<span class="text-sm text-gray-600 italic">No dependencies.</span>';
  let routeDesc = '';
  if (item.resource_route === 'local') routeDesc = 'Handled by the local desktop Hermes agent. No remote resources needed.';
  else if (item.resource_route === 'vps') routeDesc = 'Assigned to the VPS agent (Tailscale). Picked up via the Telegram job control bot.';
  else if (item.resource_route === 'sam_only') routeDesc = "Blocked. Requires Sam's explicit authorization (credentials, signing keys, or account access).";
  const html =
    '<div class="flex items-start justify-between mb-4">' +
      '<div>' +
        '<code class="text-xs text-gray-500">' + esc(fmtId(item.id)) + '</code>' +
        '<h3 class="text-xl font-bold text-white mt-1">' + esc(item.title) + '</h3>' +
        '<div class="flex items-center gap-2 mt-2 flex-wrap">' +
          '<span class="' + typeCls + ' text-xs font-medium px-2 py-0.5 bg-gray-800 rounded">' + esc(tLabel(item.type)) + '</span>' +
          '<span class="' + priorityCls + ' text-xs font-medium px-2 py-0.5 rounded text-white">' + esc(item.priority) + '</span>' +
          '<span class="' + rB + ' text-xs font-medium px-2 py-0.5 rounded text-white">' + esc(rLabel(item.resource_route)) + '</span>' +
          '<span class="' + wc + ' text-xs">to ' + esc(aLabel(item.assignee)) + '</span>' +
        '</div>' +
      '</div>' +
      '<span class="' + (COLORS.status[item.status] || 'bg-gray-600') + ' px-2 py-1 rounded text-xs font-medium">' + esc(sLabel(item.status)) + '</span>' +
    '</div>' +
    (item.description ? '<div class="text-sm text-gray-400 mb-4">' + esc(item.description) + '</div>' : '') +
    '<div class="grid grid-cols-2 gap-4 mb-4 text-center">' +
      '<div class="bg-gray-900/50 border border-gray-800 rounded-lg p-4">' +
        '<div class="text-2xl font-bold text-blue-400">' + item.progress + '%</div>' +
        '<div class="text-xs text-gray-500">Progress</div>' +
      '</div>' +
      '<div class="bg-gray-900/50 border border-gray-800 rounded-lg p-4">' +
        '<div class="text-2xl font-bold text-green-400">' + item.logged_hours + 'h / ' + item.est_hours + 'h</div>' +
        '<div class="text-xs text-gray-500">Hours (logged / estimated)</div>' +
      '</div>' +
    '</div>' +
    '<div class="mb-4">' +
      '<h4 class="text-sm font-semibold text-gray-400 mb-2">Routing & Ownership</h4>' +
      '<div class="flex items-center gap-4 flex-wrap">' +
        '<div><span class="text-xs text-gray-500">Route:</span> <span class="' + rB + ' text-xs font-medium px-2 py-0.5 rounded text-white">' + esc(rLabel(item.resource_route)) + '</span></div>' +
        '<div><span class="text-xs text-gray-500">Owner:</span> <span class="text-sm text-white">' + esc(oLabel(item.owner)) + '</span></div>' +
      '</div>' +
      '<div class="mt-2 text-xs text-gray-500">' + routeDesc + '</div>' +
    '</div>' +
    (item.security_severity ? '<div class="mb-3"><span class="text-xs font-medium text-red-300">Security: ' + esc(item.security_severity) + ' severity</span></div>' : '') +
    '<div class="mb-4"><h4 class="text-sm font-semibold text-gray-400 mb-2">Resources</h4><div class="flex flex-wrap gap-2">' + resourcesHtml + '</div></div>' +
    '<div class="mb-4"><h4 class="text-sm font-semibold text-gray-400 mb-2">Dependencies</h4><div class="flex flex-wrap gap-2">' + dependsHtml + '</div></div>' +
    '<div><h4 class="text-sm font-semibold text-gray-400 mb-2">Work Notes (' + (item.work_notes || []).length + ')</h4><div class="space-y-2">' + workNotesHtml + '</div></div>';
  document.getElementById('detail-content').innerHTML = html;
  document.getElementById('detail-overlay').classList.remove('hidden');
  document.getElementById('detail-overlay').classList.add('flex');
}

function closeDetail() {
  document.getElementById('detail-overlay').classList.add('hidden');
  document.getElementById('detail-overlay').classList.remove('flex');
}

function renderFilters() {
  const allTypes = [...new Set(allItems.map(i => i.type))].sort();
  const allAssignees = [...new Set(allItems.map(i => i.assignee))].sort();
  const allPriorities = [...new Set(allItems.map(i => i.priority))].sort((a, b) => prioOrder(a) - prioOrder(b));
  const phases = ['All', ...data.phase_order];
  const routes = ['All', 'local', 'vps', 'sam_only'];
  document.getElementById('filter-phase').innerHTML = '<option value="All">All Phases</option>' + phases.map(p => '<option value="' + p + '">' + esc(p) + '</option>').join('');
  document.getElementById('filter-type').innerHTML = '<option value="All">All Types</option>' + allTypes.map(t => '<option value="' + t + '">' + esc(tLabel(t)) + '</option>').join('');
  document.getElementById('filter-assignee').innerHTML = '<option value="All">All Teams</option>' + allAssignees.map(a => '<option value="' + a + '">' + esc(aLabel(a)) + '</option>').join('');
  document.getElementById('filter-priority').innerHTML = '<option value="All">All Priorities</option>' + allPriorities.map(p => '<option value="' + p + '">' + esc(p) + '</option>').join('');
  document.getElementById('filter-route').innerHTML = '<option value="All">All Routes</option>' + routes.filter(r => r !== 'All').map(r => '<option value="' + r + '">' + esc(rLabel(r)) + '</option>').join('');
  document.getElementById('filter-phase').onchange = e => { activeFilters.phase = e.target.value === 'All' ? null : e.target.value; applyFilters(); };
  document.getElementById('filter-type').onchange = e => { activeFilters.type = e.target.value === 'All' ? null : e.target.value; applyFilters(); };
  document.getElementById('filter-assignee').onchange = e => { activeFilters.assignee = e.target.value === 'All' ? null : e.target.value; applyFilters(); };
  document.getElementById('filter-priority').onchange = e => { activeFilters.priority = e.target.value === 'All' ? null : e.target.value; applyFilters(); };
  document.getElementById('filter-route').onchange = e => { activeFilters.route = e.target.value === 'All' ? null : e.target.value; applyFilters(); };
}

function applyFilters() {
  const filtered = allItems.filter(item => {
    if (activeFilters.phase && item.phase !== activeFilters.phase) return false;
    if (activeFilters.type && item.type !== activeFilters.type) return false;
    if (activeFilters.assignee && item.assignee !== activeFilters.assignee) return false;
    if (activeFilters.priority && item.priority !== activeFilters.priority) return false;
    if (activeFilters.route && item.resource_route !== activeFilters.route) return false;
    return true;
  });
  const byPhase = {};
  for (const p of data.phase_order) {
    const pi = filtered.filter(i => i.phase === p);
    if (pi.length === 0) continue;
    byPhase[p] = {
      total: pi.length,
      done: pi.filter(i => isCompleted(i.status)).length,
      remaining_hours: pi.reduce((s, i) => s + (isCompleted(i.status) ? 0 : i.est_hours - i.logged_hours), 0),
      items: pi.sort((a, b) => prioOrder(a.priority) - prioOrder(b.priority))
    };
  }
  renderPhaseItems(byPhase);
}

// Click-to-expand: document-level click handler using data-item-id attribute
document.addEventListener('click', e => {
  const row = e.target.closest('.item-row');
  if (row && row.dataset.itemId) {
    showDetail(row.dataset.itemId);
  }
});

// Initialize
document.getElementById('last-updated').textContent =
  'Last updated: ' + new Date().toLocaleString() + ' | ' + data.dashboard.total + ' items | ' + data.dashboard.remaining_hours + 'h remaining';
renderTopStats(data.dashboard);
renderPhaseTimeline(data.dashboard);
allItems = [];
for (const [phase, phaseData] of Object.entries(data.by_phase)) {
  phaseData.items.forEach(item => { item.phase = phase; allItems.push(item); });
}
allItems.sort((a, b) => phaseOrder(a.phase) - phaseOrder(b.phase) || prioOrder(a.priority) - prioOrder(b.priority));
renderPhaseItems(data.by_phase);
renderFilters();
'''


def render_dashboard_html() -> str:
    """Generate the full dashboard HTML from live ledger data.

    Used by both the standalone script and the web API route so the dashboard
    is accessible online (not just on the local laptop).
    """
    output = _build_dashboard_data()
    data_json = json.dumps(output, indent=2, default=str)

    parts = []
    parts.append('<!DOCTYPE html>\n<html lang="en">\n<head>\n')
    parts.append('<meta charset="UTF-8">\n')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">\n')
    parts.append('<title>NXTDeal Programming Schedule</title>\n')
    parts.append('<script src="https://cdn.tailwindcss.com"></script>\n')
    parts.append('<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">\n')
    parts.append('<style>\n')
    parts.append('body { background: #0f0f12; color: #e5e5e5; margin: 0; overflow-x: hidden; font-family: "Inter", system-ui, sans-serif; }\n')
    parts.append('.phase-bar { background: linear-gradient(90deg, #3b82f6 0%, #1e40af 100%); }\n')
    parts.append('.phase-bg { background: #1a1a20; border: 1px solid #2a2a35; }\n')
    parts.append('.item-row { border-left: 3px solid transparent; cursor: pointer; transition: background-color 0.2s; }\n')
    parts.append('.item-row:hover { background: #232330; }\n')
    parts.append('.item-row.todo { border-left-color: #6b7280; }\n')
    parts.append('.item-row.in_progress { border-left-color: #f59e0b; }\n')
    parts.append('.item-row.in_review { border-left-color: #8b5cf6; }\n')
    parts.append('.item-row.done { border-left-color: #10b981; }\n')
    parts.append('.item-row.deployed { border-left-color: #06b6d4; }\n')
    parts.append('.item-row.pushed_live { border-left-color: #22c55e; }\n')
    parts.append('.item-row.blocked { border-left-color: #ef4444; }\n')
    parts.append('.route-badge-local { background: #1e3a8a; }\n')
    parts.append('.route-badge-vps { background: #5b21b6; }\n')
    parts.append('.route-badge-sam_only { background: #be123c; }\n')
    parts.append('.detail-panel { background: #232330; border: 1px solid #2a2a35; }\n')
    parts.append('.stat-value { font-size: 1.75rem; font-weight: 700; }\n')
    parts.append('.stat-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; }\n')
    parts.append('.phase-title { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }\n')
    parts.append('.timeline-phase-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }\n')
    parts.append('@media (max-width: 768px) { .stat-value { font-size: 1.25rem; } }\n')
    parts.append('</style>\n</head>\n<body>\n')
    parts.append('<div class="max-w-7xl mx-auto p-6">\n')
    parts.append('  <div class="mb-8">\n')
    parts.append('    <h1 class="text-3xl font-bold text-white mb-1">NXTDeal Programming Schedule</h1>\n')
    parts.append('    <p class="text-sm text-gray-500">Production bridge tracking — target: December 1st, 2026 (first dealer)</p>\n')
    parts.append('    <div class="mt-2 text-xs text-gray-600" id="last-updated">Loading...</div>\n  </div>\n')
    parts.append('  <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8" id="top-stats"></div>\n')
    parts.append('  <div class="mb-8">\n')
    parts.append('    <h2 class="text-lg font-semibold text-white mb-4">Phase Progress</h2>\n')
    parts.append('    <div class="space-y-3" id="phase-timeline"></div>\n  </div>\n')
    parts.append('  <div class="mb-6 flex flex-wrap gap-3" id="filters-container">\n')
    parts.append('    <select id="filter-phase" class="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-sm"></select>\n')
    parts.append('    <select id="filter-type" class="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-sm"></select>\n')
    parts.append('    <select id="filter-assignee" class="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-sm"></select>\n')
    parts.append('    <select id="filter-priority" class="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-sm"></select>\n')
    parts.append('    <select id="filter-route" class="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-sm"></select>\n  </div>\n')
    parts.append('  <div class="mb-8">\n')
    parts.append('    <h2 class="text-lg font-semibold text-white mb-4">Work Items by Phase</h2>\n')
    parts.append('    <div class="space-y-6" id="phase-items"></div>\n  </div>\n')
    parts.append('  <div id="detail-overlay" class="fixed inset-0 bg-black/60 backdrop-blur-sm hidden items-end justify-center p-4 z-50">\n')
    parts.append('    <div id="detail-panel" class="detail-panel rounded-xl p-6 max-w-3xl w-full mb-8">\n')
    parts.append('      <div id="detail-content"></div>\n')
    parts.append('      <button onclick="closeDetail()" class="mt-4 px-4 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300 hover:bg-gray-700">Close</button>\n')
    parts.append('    </div>\n  </div>\n')
    parts.append('</div>\n  <script>\n')
    parts.append('    const data = ' + data_json + ';\n')
    parts.append(_JS)
    parts.append('\n  </script>\n</body>\n</html>\n')

    return ''.join(parts)


if __name__ == "__main__":
    # Standalone generation for local development
    html = render_dashboard_html()

    out_path = os.environ.get(
        "NXTDEAL_DASHBOARD_OUTPUT",
        "C:/Users/sambo/AppData/Local/hermes/cache/scratch/programming_schedule_dashboard.html"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Also write the data JSON for tooling that reads it separately
    data_path = os.environ.get(
        "NXTDEAL_DASHBOARD_DATA",
        "C:/Users/sambo/AppData/Local/hermes/cache/scratch/programming_schedule_data.json"
    )
    output = _build_dashboard_data()
    with open(data_path, "w") as f:
        f.write(json.dumps(output, indent=2, default=str))

    rc = output['route_counts']
    print("Dashboard written to " + out_path)
    print("Routes: local=" + str(rc['local']) + ", vps=" + str(rc['vps']) + ", sam_only=" + str(rc['sam_only']))
