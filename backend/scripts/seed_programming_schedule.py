"""Seed the programming schedule with items from the PRODUCTION-BRIDGE plan."""
import json
from core.dealeros import ledger
from core import programming_schedule as ps

ledger.reset()

# Route mapping: title → (resource_route, owner)
# local = desktop Hermes handles it; vps = VPS agent with Tailscale; sam_only = Sam must authorize
ROUTE_MAP = {
    "Fix GitHub Actions billing": ("sam_only", "sam"),
    "Restore Coolify dashboard access": ("vps", "sam"),
    "Unblock browser tool policy": ("vps", "sam"),
    "Marketing delivery authorization": ("sam_only", "sam"),
    "PrivateEmail SMTP credentials": ("sam_only", "sam"),
    "Twilio SMS credentials": ("sam_only", "sam"),
    "Install signing certificate": ("sam_only", "sam"),
    "Configure Hub signing/network keys": ("sam_only", "sam"),
    "Enable customer Verify/Garage/Retail boundaries": ("sam_only", "sam"),
}

# Work notes and resources to attach per item (by title)
ITEM_NOTES_RESOURCES = {
    "AI config backend module": (
        ["Created core/ai_config.py with get_config/set_byok/set_routing/set_ai_enabled/get_byok",
         "Added MySales delegation: get_config delegates to mysales_ai.get_config, set_byok delegates to mysales_ai.set_byok, all 5 functions delegate for app_slug='mysales'",
         "Fixed _mask to use bullet chars matching mysales_ai.py"],
        ["backend/core/ai_config.py", "backend/core/mysales_ai.py"]),
    "AI config API routes in app.py": (
        ["Added AIConfigRequest, AIBYOKRequest, AIRoutingRequest, AIApiKeyRequest models",
         "6 routes: GET/POST /ai-config/app, POST /ai-config/app/byok, POST /ai-config/app/routing, GET /ai-config/app/resolve"],
        ["backend/api/app.py"]),
    "AI config frontend component": (
        ["Created AiConfig.tsx: shared component handling staff full-config + customer read-only views",
         "Created aiConfig.ts: exports getAiConfig, setAiEnabled, setAiByok, clearAiByok, setAiRouting, resolveAiModel, BYOK_PROVIDERS",
         "Fixed TypeScript *** type annotations to string in aiConfig.ts:76 and AiConfig.tsx:261"],
        ["frontend/lib/aiConfig.ts", "frontend/components/apps/screens/AiConfig.tsx"]),
    "AI config registry wiring": (
        ["Added aiconfig screen entries to all 7 companion apps in registry.ts",
         "AiConfig import + 6 wiring entries in components/apps/screens/index.tsx"],
        ["frontend/lib/apps/registry.ts", "frontend/components/apps/screens/index.tsx"]),
    "TypeScript *** type fix": (
        ["Replaced *** with string type in aiConfig.ts:76 (API_BASE param)",
         "Replaced *** with string type in AiConfig.tsx:261 (apiKey param)"],
        ["frontend/lib/aiConfig.ts:76", "frontend/components/apps/screens/AiConfig.tsx:261"]),
    "AI config tests": (
        ["Created backend/tests/test_ai_config.py with 15 test functions, all PASS"],
        ["backend/tests/test_ai_config.py"]),
    "Fix GitHub Actions billing": (
        [],
        ["Sam must resolve GitHub Actions billing at github.com/settings/billing"]),
    "Restore Coolify dashboard access": (
        [],
        ["coolify.sambohon.digital"]),
    "Unblock browser tool policy": (
        [],
        ["Browser tool policy configuration"]),
    "Wire showroom:saved screen": (
        [],
        ["frontend/components/apps/screens/SavedVehicles.tsx"]),
    "Wire mygarage:book screen": (
        [],
        ["frontend/components/apps/screens/CustomerBooking.tsx"]),
    "Wire mygarage:alerts screen": (
        [],
        ["frontend/components/apps/screens/CustomerAlerts.tsx"]),
    "Configure bridge_chrono analysis_engine": (
        ["Read bridge_chrono.py — current analysis_engine = 'not_configured_by_bridge'",
         "Need Chrono Engine endpoints configured (Chrono 0.394.41 local-only)"],
        ["backend/core/bridge_chrono.py", "backend/intelligence/chrono_remote.py", "backend/intelligence/facade.py"]),
    "Strip ai_management.py to Engine pass-through": (
        ["Analyzed: ai_management.py (6,347 chars partial) — 18 AI modules identified needing pass-through"],
        ["backend/core/ai_management.py", "backend/core/ai_management_api.py"]),
    "Strip bot_fleet.py to Engine pass-through": (
        [],
        ["backend/core/bot_fleet.py", "backend/core/bot_fleet_api.py"]),
    "Strip ai_spend.py to Engine pass-through": (
        [],
        ["backend/core/ai_spend.py", "backend/core/ai_spend_network_api.py"]),
    "Strip agent_fabric.py to Engine pass-through": (
        ["Analyzed: agent_fabric.py (4,549 chars partial) — agent pipeline entry point"],
        ["backend/core/agent_fabric.py", "backend/routers/agent_fabric.py"]),
    "Strip ai_assistant.py to Engine pass-through": (
        [],
        ["backend/core/ai_assistant.py"]),
    "Strip ai_api.py to Engine pass-through": (
        [],
        ["backend/core/ai_api.py"]),
    "Strip ai_kill_switch.py to Engine pass-through": (
        [],
        ["backend/core/ai_kill_switch.py", "backend/routers/ai_kill_switch.py"]),
    "Strip ai_worker.py to Engine pass-through": (
        [],
        ["backend/core/ai_worker.py", "backend/core/ai_worker_api.py"]),
    "Strip ai_tools.py to Engine pass-through": (
        [],
        ["backend/core/ai_tools.py"]),
    "Admin AI management pages to Engine consumer": (
        [],
        ["frontend/components/apps/AppMenu.tsx"]),
    "Marketing AI flags to Engine pass-through": (
        ["Identified 21 FEATURE_FLAGS in frontend that control AI features"],
        ["frontend/lib/flags.ts"]),
    "Marketing delivery authorization": (
        [],
        ["env:NXTDEAL_MARKETING_DELIVERY_ENABLED=true"]),
    "PrivateEmail SMTP credentials": (
        [],
        ["credentials: SMTP password (PrivateEmail)"]),
    "Twilio SMS credentials": (
        [],
        ["credentials: Twilio account SID + auth token"]),
    "Marketing journey execution engine": (
        [],
        ["backend/core/marketing_journey.py"]),
    "Enable customer Verify/Garage/Retail boundaries": (
        [],
        ["frontend/app/verify", "frontend/app/garage", "frontend/app/retail"]),
    "Real banking adapter": (
        [],
        ["backend/core/banking.py"]),
    "Install signing certificate": (
        [],
        ["credentials: code-signing certificate"]),
    "Configure Hub signing/network keys": (
        ["Hub currently uses dev fallback for session signing"],
        ["hub/hub_core/config.py"]),
    "Production image/source parity": (
        [],
        ["frontend/.next/"]),
    "PostgreSQL authority switch": (
        ["Production frontend: 510d0965 (Oct 22 03:50 UTC)",
         "Production backend: b2895a18 (Oct 22 03:40 UTC)",
         "Security RC2: 2dae3dd6 — 14177 tests pass, 0 failures"],
        ["Production frontend git tag 510d0965", "Production backend git tag b2895a18"]),
    "Configure monitoring + alert recipient": (
        [],
        ["monitoring config"]),
    "Database migration cutover": (
        ["47 employees across 5 departments, single tenant graph with RBAC"],
        ["backend/core/storage_paths.py"]),
    "Deploy Chrono Engine 0.8.3": (
        ["Chrono Platform 0.394.41 (8c349b5) exists locally but is NOT deployed"],
        ["Chrono Engine 0.8.3 build"]),
    "Chrono Platform 0.394.41 deployment": (
        ["Chrono Platform 0.394.41 (8c349b5) is local-only, NOT deployed"],
        ["Chrono Platform build output"]),
    "Seven catalog features lack AI execution tier": (
        ["Catalog has 7 AI features with no execution tier mapping"],
        ["backend/catalog/features.py"]),
    "Hub admin session revocation fix pending": (
        ["Token credential binding deployed locally but NOT on hosted staging"],
        ["hub/hub_core/session.py"]),
    "Frontend auto-deploy needs release pins": (
        ["Coolify URL: coolify.sambohon.digital — auto-deploys on branch push"],
        ["coolify.sambohon.digital"]),
}

items = [
    # Phase 0: AI Config Generalization (this session)
    ("AI config backend module", "Generalized ai_config.py with BYOK + routing, MySales delegation", "feature", "Phase 0", "high", "backend", 8, None, None),
    ("AI config API routes in app.py", "6 routes + 4 request models for /ai-config/app", "feature", "Phase 0", "high", "backend", 4, None, None),
    ("AI config frontend component", "AiConfig.tsx + aiConfig.ts shared across 7 apps", "feature", "Phase 0", "high", "frontend", 12, None, None),
    ("AI config registry wiring", "aiconfig screens in all 7 companion apps + index.tsx wiring", "feature", "Phase 0", "medium", "frontend", 4, None, None),
    ("TypeScript *** type fix", "Fix *** type annotations to string in aiConfig.ts and AiConfig.tsx", "bug", "Phase 0", "medium", "frontend", 1, None, None),
    ("AI config tests", "15 test functions covering defaults, BYOK, routing, delegation", "feature", "Phase 0", "medium", "backend", 4, None, None),
    # Phase 1: CI/Verification restoration
    ("Fix GitHub Actions billing", "Billing failure since Oct 19 blocks all CI verification", "bug", "Phase 1", "critical", "sample", 2, None, None),
    ("Restore Coolify dashboard access", "Requires Sam session for image/source inspection", "feature", "Phase 1", "high", "sample", 1, None, None),
    ("Unblock browser tool policy", "Blocks inventory browser acceptance testing", "feature", "Phase 1", "medium", "sample", 3, None, None),
    # Phase 2: Companion App Completion
    ("Wire showroom:saved screen", "Build SavedVehicles component, currently CustomerUnavailable shell", "feature", "Phase 2", "medium", "frontend", 16, None, None),
    ("Wire mygarage:book screen", "Build CustomerBooking component, currently CustomerUnavailable shell", "feature", "Phase 2", "high", "frontend", 20, None, None),
    ("Wire mygarage:alerts screen", "Build CustomerAlerts component, currently CustomerUnavailable shell", "feature", "Phase 2", "medium", "frontend", 12, None, None),
    # Phase 3: AI Architectural Refactor
    ("Configure bridge_chrono analysis_engine", "Point bridge_chrono.py at Chrono Engine endpoints", "feature", "Phase 3", "high", "backend", 4, None, None),
    ("Strip ai_management.py to Engine pass-through", "Convert core/ai_management.py + ai_management_api.py to Engine client", "tech-debt", "Phase 3", "high", "backend", 16, None, None),
    ("Strip bot_fleet.py to Engine pass-through", "Convert core/bot_fleet.py + bot_fleet_api.py to Engine client", "tech-debt", "Phase 3", "high", "backend", 12, None, None),
    ("Strip ai_spend.py to Engine pass-through", "Convert core/ai_spend.py + ai_spend_network_api.py to Engine client", "tech-debt", "Phase 3", "high", "backend", 12, None, None),
    ("Strip agent_fabric.py to Engine pass-through", "Convert core/agent_fabric.py + routers/agent_fabric.py to Engine client", "tech-debt", "Phase 3", "high", "backend", 16, None, None),
    ("Strip ai_assistant.py to Engine pass-through", "Convert core/ai_assistant.py to Engine client", "tech-debt", "Phase 3", "high", "backend", 8, None, None),
    ("Strip ai_api.py to Engine pass-through", "Convert core/ai_api.py to Engine client", "tech-debt", "Phase 3", "high", "backend", 8, None, None),
    ("Strip ai_kill_switch.py to Engine pass-through", "Convert core/ai_kill_switch.py + routers/ai_kill_switch.py", "tech-debt", "Phase 3", "high", "backend", 8, None, None),
    ("Strip ai_worker.py to Engine pass-through", "Convert core/ai_worker.py + ai_worker_api.py", "tech-debt", "Phase 3", "medium", "backend", 8, None, None),
    ("Strip ai_tools.py to Engine pass-through", "Convert core/ai_tools.py", "tech-debt", "Phase 3", "medium", "backend", 8, None, None),
    ("Admin AI management pages to Engine consumer", "Convert administration_menu.py AI Agents/AI Management to Engine API consumer views", "feature", "Phase 3", "high", "frontend", 20, None, None),
    ("Marketing AI flags to Engine pass-through", "Convert 21 FEATURE_FLAGS (ai_assistant, marketing_studio, etc.)", "tech-debt", "Phase 3", "medium", "backend", 24, None, None),
    # Phase 4: Marketing/Customer Workflows
    ("Marketing delivery authorization", "Sam sets NXTDEAL_MARKETING_DELIVERY_ENABLED=true + credentials", "feature", "Phase 4", "critical", "sample", 1, None, None),
    ("PrivateEmail SMTP credentials", "Obtain and configure SMTP password for email delivery", "feature", "Phase 4", "high", "sample", 1, None, None),
    ("Twilio SMS credentials", "Obtain and configure Twilio credentials for SMS delivery", "feature", "Phase 4", "high", "sample", 1, None, None),
    ("Marketing journey execution engine", "Implement customer enrollment, condition evaluation, step dispatch", "feature", "Phase 4", "high", "backend", 24, None, None),
    ("Enable customer Verify/Garage/Retail boundaries", "Open public customer routes after identity verification", "feature", "Phase 4", "high", "sample", 8, None, None),
    ("Real banking adapter", "Replace _simulate_accounts with genuine banking adapter", "feature", "Phase 4", "high", "backend", 24, None, None),
    # Phase 5: Hub/Infrastructure
    ("Install signing certificate", "Required for Chrono Engine 0.8.3 + Windows SmartScreen", "feature", "Phase 5", "critical", "sample", 2, None, None),
    ("Configure Hub signing/network keys", "Replace dev fallback for session signing", "feature", "Phase 5", "high", "sample", 2, None, None),
    ("Production image/source parity", "Complete frontend compiled-asset/dependency reconciliation", "feature", "Phase 5", "medium", "devops", 16, None, None),
    ("PostgreSQL authority switch", "Runtime authorization, shadow parity, rollback rehearsal", "feature", "Phase 5", "high", "devops", 24, None, None),
    ("Configure monitoring + alert recipient", "External alert delivery to configured destination", "feature", "Phase 5", "medium", "devops", 8, None, None),
    ("Database migration cutover", "Coordinated tenant graph backup/restore, RPO/RTO", "feature", "Phase 5", "high", "devops", 16, None, None),
    # Phase 6: Chrono Engine Deployment
    ("Deploy Chrono Engine 0.8.3", "Requires signing cert + bridge_chrono configuration", "feature", "Phase 6", "critical", "backend", 8, None, None),
    ("Chrono Platform 0.394.41 deployment", "Local-only build, needs deployment", "feature", "Phase 6", "high", "backend", 8, None, None),
    # Security items
    ("Seven catalog features lack AI execution tier", "customer_journey_recommendation, accessories_pitch, equity_upgrade_offer, inventory_ad_copy, success_qbr_insights, ai_consulting_engine, ai_assist", "security", "Phase 3", "high", "backend", 8, "high", None),
    ("Hub admin session revocation fix pending", "Token credential binding deployed locally, not on hosted staging", "security", "Phase 5", "high", "backend", 4, "medium", None),
    ("Frontend auto-deploy needs release pins", "Coolify webhook auto-deploys branch pushes, needs release control", "security", "Phase 6", "medium", "devops", 4, "medium", None),
]

created = 0
for title, desc, itype, phase, priority, assignee, est, sec_sev, deps in items:
    route, owner = ROUTE_MAP.get(title, ("local", "auto"))
    item = ps.create_item(title, desc, item_type=itype, phase=phase,
                          priority=priority, assignee=assignee,
                          est_hours=est, depends_on=deps,
                          security_severity=sec_sev,
                          resource_route=route, owner=owner)
    if "error" in item:
        print(f"  ERROR: {title}: {item['error']}")
    else:
        created += 1
        item_id = item["id"]
        notes, resources = ITEM_NOTES_RESOURCES.get(title, ([], []))
        for note in notes:
            ps.add_work_note(item_id, note)
        for res in resources:
            ps.add_resource(item_id, res)

print(f"\nCreated {created} items")
dash = ps.get_dashboard()
print(f"Total: {dash['total']}")
print(f"By type: {dash['by_type']}")
print(f"By assignee: {dash['by_assignee']}")
print(f"By phase: {json.dumps(dash['by_phase'], indent=2)}")
print(f"Completed: {dash['completed']}")
print(f"Remaining hours: {dash['remaining_hours']}")
print(f"Security issues: {dash['security_issues']}")
print(f"Blockers: {dash['blockers']}")
