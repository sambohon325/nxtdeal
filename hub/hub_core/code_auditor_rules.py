"""
NXTDeal Hub -- AI-Powered Self-Auditing Code Layer: the real detection rules.

See hub_core/code_auditor.py's own module docstring for the full design, Sam's
three governing decisions, and the severity ladder. This file holds only the
actual rule functions -- each one walks real files on disk and returns a list
of plain finding dicts (not yet wrapped in a CodeAuditFinding/persisted); the
orchestrator in code_auditor.py turns those into real, tracked findings.

"Real rules, never fake AI" -- matching this codebase's own established
convention (hub_core/network_audit.py, hub_core/collections.py's risk scoring,
hub_core/readiness_recommendations.py): every rule below is a deterministic,
re-runnable static-analysis check over real file content, with a real file
path + line number + matched snippet attached to every finding. Nothing here
asks an LLM "is this a bug" -- that would be exactly the un-auditable
judgment call Sam's own kickoff message was worried about.

AREAS SCANNED (Sam's own scope decision, 2026-07-19): the ONE real shared
codebase every dealer tenant runs (process-per-tenant, identical code --
see CLAUDE.md's "NXTDeal Hub / Multi-Tenant Architecture") plus the Hub
itself and the Network Connect browser extension. Per-tenant RUNTIME health
is a fully separate, already-built concern (Infrastructure & Platform
Operations / NOC) -- not duplicated here.
"""

import ast
import os
import re


# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------

def repo_root():
    """The real repo root, two levels up from this file
    (hub/hub_core/code_auditor_rules.py -> hub/core -> hub -> repo root)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))


AREA_DIRS = {
    "backend": "backend",
    "hub": "hub",
    "frontend": "frontend",
    "extension": "network-connect-extension",
}

# Directories never worth scanning inside any area -- generated output,
# dependency installs, build artifacts, and this session's own storage data.
_SKIP_DIR_NAMES = {
    "node_modules", ".next", "venv", "__pycache__", ".git", "storage",
    "dist", "build", ".turbo", "out", "seed_data",
}


def _walk_files(area, extensions):
    root = os.path.join(repo_root(), AREA_DIRS[area])
    if not os.path.isdir(root):
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")]
        for name in filenames:
            if any(name.endswith(ext) for ext in extensions):
                yield os.path.join(dirpath, name)


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def _rel(path):
    return os.path.relpath(path, repo_root()).replace("\\", "/")


# ---------------------------------------------------------------------------
# Comment / docstring stripping -- a real, line-based pass so a rule's own
# pattern match never fires on a line that only MENTIONS a symbol in prose.
# This is the exact false-negative trap CLAUDE.md's own "codebase-wide
# missing-save_graph() audit" documents hitting with a plain substring grep
# (a docstring saying "...saved via save_graph()..." looked identical to a
# real call). Line-based, not a full tokenizer -- good enough for detecting
# whether a real call/keyword appears as CODE on a given line, and keeps
# line numbers intact for evidence snippets.
# ---------------------------------------------------------------------------

def strip_comments_and_docstrings(source):

    lines = source.split("\n")
    out_lines = []
    in_triple = None

    for line in lines:

        if in_triple:
            idx = line.find(in_triple)
            if idx == -1:
                out_lines.append("")
                continue
            line = line[idx + len(in_triple):]
            in_triple = None

        working = line

        hash_idx = working.find("#")
        if hash_idx != -1:
            working = working[:hash_idx]

        for triple in ('"""', "'''"):
            t_idx = working.find(triple)
            if t_idx != -1:
                closing = working.find(triple, t_idx + 3)
                if closing != -1:
                    working = working[:t_idx] + working[closing + 3:]
                else:
                    working = working[:t_idx]
                    in_triple = triple
                break

        out_lines.append(working)

    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# Rule A -- missing save_graph() persistence discipline (backend only; this
# is a real, specifically backend/core bug class -- the shared graph ledger
# and its save_graph()/GRAPH_PATH convention has no Hub-side analog, Hub
# modules each have their own differently-named save_X() function, see
# hub_core/code_auditor.py's own docstring). Independently found and fixed ~19+
# times across this codebase's own history per CLAUDE.md's dedicated
# "codebase-wide missing-save_graph() audit" section -- this rule is what
# makes that class of bug detectable going forward instead of only found by
# accident.
# ---------------------------------------------------------------------------

_MUTATION_SIGNAL_RE = re.compile(
    r"ledger\.add_entity\(|ledger\.add_relationship\(|"
    r"\.attributes\[[^\]]+\]\s*=|\.attributes\.setdefault\(|\.attributes\.update\("
)
_SAVE_GRAPH_CALL_RE = re.compile(r"(?m)^\s*save_graph\(")
_SKIP_SAVE_RE = re.compile(r"_skip_save")

_EXCLUDED_BACKEND_MODULE_SUFFIXES = ("_storage.py",)
_EXCLUDED_BACKEND_MODULE_NAMES = {
    "entity_types.py", "id_generator.py", "storage.py", "storage_paths.py",
    "repository.py", "dealeros.py", "entities.py", "relationships.py",
}


def rule_missing_save_graph():
    """A backend/core/*.py module that mutates the ledger (adds an entity/
    relationship, or writes an .attributes[...] value on an already-loaded
    entity) but never calls save_graph( anywhere in the file. Deliberately
    file-level, not function-level -- a module that saves ANYWHERE for its
    own mutations is not flagged, since a shared save-at-the-end-of-a-batch
    helper (the exact pattern this codebase's own websites.py/
    dealership_events.py/trigger_alerts.py use via _skip_save) is a real,
    correct design, not a bug -- confirmed via the _SKIP_SAVE_RE check below,
    which downgrades (doesn't suppress) a file using that pattern, since a
    _skip_save-capable module can still genuinely forget to save at its own
    top-level orchestration point."""

    findings = []

    for path in _walk_files("backend", (".py",)):

        name = os.path.basename(path)
        if "core" not in path.replace("\\", "/").split("/"):
            continue
        if name.endswith(_EXCLUDED_BACKEND_MODULE_SUFFIXES) or name in _EXCLUDED_BACKEND_MODULE_NAMES:
            continue
        if name.startswith("test_"):
            continue

        source = _read(path)
        if not source:
            continue

        stripped = strip_comments_and_docstrings(source)

        has_mutation = bool(_MUTATION_SIGNAL_RE.search(stripped))
        has_save = bool(_SAVE_GRAPH_CALL_RE.search(stripped))

        if has_mutation and not has_save:

            match = _MUTATION_SIGNAL_RE.search(stripped)
            line_no = stripped[: match.start()].count("\n") + 1 if match else None
            evidence_line = source.split("\n")[line_no - 1].strip() if line_no else ""

            uses_skip_save = bool(_SKIP_SAVE_RE.search(stripped))

            findings.append({
                "rule_key": "missing_save_graph",
                "rule_title": "Missing save_graph() -- real mutation with no persistence call",
                "severity": "small",
                "area": "backend",
                "file_path": _rel(path),
                "line_number": line_no,
                "description": (
                    "This module writes real data onto the shared graph ledger "
                    "(ledger.add_entity/add_relationship, or a direct "
                    ".attributes[...] write) but never calls save_graph( "
                    "anywhere in the file. Per this codebase's own documented "
                    "history (~19+ prior instances of this exact bug class), "
                    "this means every real mutation through this module is "
                    "silently discarded the next time the server restarts."
                    + (
                        " Note: this file DOES use the _skip_save batching "
                        "pattern elsewhere, so double-check this isn't a "
                        "legitimate batched-save call site before treating "
                        "this as the missing save -- flag reviewed as "
                        "small-tier regardless since the underlying risk "
                        "(a real code path with zero save_graph reachable) "
                        "is the same either way."
                        if uses_skip_save else ""
                    )
                ),
                "evidence": evidence_line,
                "recommendation": (
                    "Add a real save_graph(GRAPH_PATH) call immediately before "
                    "every return in the mutating function(s) in this file "
                    "(or one batched save_graph(GRAPH_PATH) call at the end of "
                    "the top-level orchestration function, if this file "
                    "already uses the _skip_save batching pattern)."
                ),
            })

    return findings


# ---------------------------------------------------------------------------
# Rule B -- route registration shadowing. A dynamic {id}-shaped path
# registered before a static sibling path of the identical shape under the
# same HTTP method permanently shadows the static route (FastAPI/Starlette
# match by registration order) -- a real, repeatedly-documented bug class in
# this codebase (e.g. the /collateral/* vs. pre-existing /assets/{asset_id}
# near-miss, and multiple sessions' own "static path registered before
# dynamic sibling" discipline notes).
# ---------------------------------------------------------------------------

_ROUTE_DECORATOR_RE = re.compile(
    r'@app\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']'
)


def _extract_routes(path):
    source = _read(path)
    if not source:
        return []

    stripped = strip_comments_and_docstrings(source)
    routes = []

    for match in _ROUTE_DECORATOR_RE.finditer(stripped):
        method = match.group(1)
        route_path = match.group(2)
        line_no = stripped[: match.start()].count("\n") + 1
        routes.append((method, route_path, line_no))

    return routes


def _segments(route_path):
    return [seg for seg in route_path.strip("/").split("/") if seg != ""]


def _segment_is_dynamic(seg):
    return seg.startswith("{") and seg.endswith("}")


def _route_would_shadow(earlier_segs, later_segs):
    """True if a request matching later_segs would actually be routed to
    the earlier pattern first (earlier has a dynamic segment exactly where
    later has a different literal, at every other position they're
    identical or the earlier side is also dynamic)."""

    if len(earlier_segs) != len(later_segs):
        return False

    if earlier_segs == later_segs:
        return False  # identical pattern, not a shadowing bug (a duplicate route, different concern)

    for e, l in zip(earlier_segs, later_segs):
        if e == l:
            continue
        if _segment_is_dynamic(e):
            continue
        return False  # earlier has a literal that doesn't match later's segment at all

    return True


def rule_route_shadowing():

    findings = []

    route_files = {
        "backend": os.path.join(repo_root(), "backend", "api", "app.py"),
        "hub": os.path.join(repo_root(), "hub", "app.py"),
    }

    for area, path in route_files.items():
        if not os.path.isfile(path):
            continue

        routes = _extract_routes(path)

        by_method = {}
        for method, route_path, line_no in routes:
            by_method.setdefault(method, []).append((route_path, line_no))

        for method, entries in by_method.items():
            for i, (earlier_path, earlier_line) in enumerate(entries):
                earlier_segs = _segments(earlier_path)
                for later_path, later_line in entries[i + 1:]:
                    later_segs = _segments(later_path)
                    if _route_would_shadow(earlier_segs, later_segs):
                        findings.append({
                            "rule_key": "route_shadowing",
                            "rule_title": "Route registration shadowing",
                            "severity": "medium",
                            "area": area,
                            "file_path": _rel(path),
                            "line_number": later_line,
                            "description": (
                                f"{method.upper()} {later_path} (line {later_line}) is "
                                f"registered AFTER {method.upper()} {earlier_path} "
                                f"(line {earlier_line}), and {earlier_path}'s dynamic "
                                f"segment matches every real request to {later_path} "
                                f"first. FastAPI/Starlette match routes in registration "
                                f"order -- {later_path} is permanently unreachable."
                            ),
                            "evidence": f"{method.upper()} {earlier_path}  (line {earlier_line})  -->  shadows  -->  {method.upper()} {later_path}  (line {later_line})",
                            "recommendation": (
                                f"Move the {method.upper()} {later_path} route "
                                f"registration to before {method.upper()} {earlier_path}, "
                                f"or rename one of the two paths so they no longer "
                                f"collide under the same segment shape."
                            ),
                        })

    return findings


# ---------------------------------------------------------------------------
# Rule C -- a mutating *_api.py function with no visible role/ACL check in
# its own body. Heuristic and intentionally conservative (medium, never
# auto-fixed) -- a thin pass-through *_api.py function that simply forwards
# to an already-gated core function is a real, correct pattern elsewhere in
# this codebase, so this rule can't safely auto-fix or even assert a false
# positive is a bug; it flags for human review, honestly labeled as such.
# ---------------------------------------------------------------------------

_MUTATION_VERB_RE = re.compile(
    r"^(create|update|set|delete|remove|approve|reject|cancel|mark|record|"
    r"submit|assign|toggle|apply|generate|revoke|resolve|override|"
    r"escalate|publish|activate|deactivate|enable|disable|reduce|"
    r"adopt|convert|promote|log|schedule)_"
)

_ROLE_CHECK_SIGNAL_RE = re.compile(
    r"role\s*not\s*in|role\s*!=|role\s*==|_ROLES\b|ROLES\b|"
    r"['\"]?role['\"]?\s+required|not authorized|permission denied|"
    r"_check_hub_key|x_nxtdeal_hub_key|_authenticate\("
)


def rule_missing_acl_gate():

    findings = []

    for area in ("backend", "hub"):
        for path in _walk_files(area, (".py",)):

            name = os.path.basename(path)
            if not name.endswith("_api.py"):
                continue

            source = _read(path)
            if not source:
                continue

            stripped = strip_comments_and_docstrings(source)

            try:
                tree = ast.parse(stripped)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if not _MUTATION_VERB_RE.match(node.name):
                    continue
                if node.name.startswith("_"):
                    continue

                func_lines = stripped.split("\n")[node.lineno - 1: (node.end_lineno or node.lineno)]
                func_source = "\n".join(func_lines)

                if _ROLE_CHECK_SIGNAL_RE.search(func_source):
                    continue

                # A short pass-through (<= 4 real statement lines) that just
                # forwards args to another function is a common, legitimate
                # thin-wrapper shape in this codebase -- still worth a
                # medium-tier flag (the gate might live one hop away, or
                # might genuinely be missing), never dropped silently.
                findings.append({
                    "rule_key": "missing_acl_gate",
                    "rule_title": "Mutating API function with no visible role/ACL check",
                    "severity": "medium",
                    "area": area,
                    "file_path": _rel(path),
                    "line_number": node.lineno,
                    "description": (
                        f"{node.name}() in {_rel(path)} looks like a mutating action "
                        f"(name starts with a mutation verb) but its own function body "
                        f"has no visible role/ACL check. This may be a legitimate thin "
                        f"pass-through to an already-gated core function -- verify before "
                        f"treating this as a real gap."
                    ),
                    "evidence": f"def {node.name}(...): ...  (line {node.lineno})",
                    "recommendation": (
                        f"Confirm whether {node.name}() (or the core function it calls) "
                        f"enforces a real role/ACL check. If not, add one matching this "
                        f"module's own established role-set convention."
                    ),
                })

    return findings


# ---------------------------------------------------------------------------
# Rule D -- structural / architecture smells. Always large/systemic: no
# single-file fix exists for any of these, so this rule never proposes an
# auto-fix or a drafted patch -- only a real, concrete recommendation.
# ---------------------------------------------------------------------------

_GOD_FILE_LINE_THRESHOLD = 3000
_GOD_COMPONENT_LINE_THRESHOLD = 1200


def rule_structural_smells():

    findings = []

    # -- god-file: backend/api/app.py --
    app_py = os.path.join(repo_root(), "backend", "api", "app.py")
    source = _read(app_py)
    if source:
        line_count = source.count("\n") + 1
        route_count = len(_ROUTE_DECORATOR_RE.findall(strip_comments_and_docstrings(source)))
        if line_count >= _GOD_FILE_LINE_THRESHOLD or route_count >= 200:
            findings.append({
                "rule_key": "god_file_app_py",
                "rule_title": "backend/api/app.py is a god-file",
                "severity": "large",
                "area": "backend",
                "file_path": "backend/api/app.py",
                "line_number": None,
                "description": (
                    f"backend/api/app.py is {line_count} lines with roughly "
                    f"{route_count} route decorators, all in one file. Every new "
                    f"department's routes are appended here, which makes the file "
                    f"progressively harder to navigate, review, and merge cleanly "
                    f"as more sessions touch it concurrently (this codebase's own "
                    f"history documents several real merge/route-shadowing "
                    f"incidents directly caused by this file's size)."
                ),
                "evidence": f"{line_count} lines, ~{route_count} route decorators in one module",
                "recommendation": (
                    "Split into FastAPI APIRouter modules per department "
                    "(sales_routes.py, service_routes.py, finance_routes.py, "
                    "etc.), each mounted via app.include_router(...) in "
                    "app.py. This is a large, deliberate refactor -- not a "
                    "small/medium change -- and should be scoped and "
                    "reviewed as its own project, not auto-applied."
                ),
            })

    # -- duplicate top-level `core` package name (backend/core vs hub/core) --
    backend_core = os.path.join(repo_root(), "backend", "core")
    hub_core = os.path.join(repo_root(), "hub", "core")
    if os.path.isdir(backend_core) and os.path.isdir(hub_core):
        findings.append({
            "rule_key": "duplicate_core_package_name",
            "rule_title": "backend/core and hub/core share the same package name",
            "severity": "large",
            "area": "backend",
            "file_path": "backend/core/ + hub/hub_core/",
            "line_number": None,
            "description": (
                "backend/ and hub/ each have their own top-level package "
                "literally named `core`, with no shared namespace. This is "
                "already a documented, repeated source of real mistakes "
                "across this codebase's own session history -- a `python -c "
                "\"import hub_core.X\"` smoke test run from the wrong "
                "directory silently imports the WRONG core package, and any "
                "code that tried to import both backend/core and hub/core "
                "in the same process would collide outright."
            ),
            "evidence": "backend/core/__init__ (implicit) vs. hub/hub_core/__init__ (implicit) -- same package name, two codebases",
            "recommendation": (
                "Rename one package (e.g. hub/core -> hub/hubcore) to remove "
                "the ambiguity permanently, or explicitly document (as this "
                "codebase's own CLAUDE.md already does in several places) "
                "that any process/test touching either package must run "
                "with the correct directory first on sys.path. A rename is "
                "the more durable fix but touches every import statement in "
                "hub/ -- a large, deliberate refactor, not a small/medium "
                "change."
            ),
        })

    # -- oversized frontend dispatch component --
    menu_dash_panel = os.path.join(repo_root(), "frontend", "components", "MenuDashPanel.tsx")
    fe_source = _read(menu_dash_panel)
    if fe_source:
        fe_lines = fe_source.count("\n") + 1
        if fe_lines >= _GOD_COMPONENT_LINE_THRESHOLD:
            findings.append({
                "rule_key": "god_component_menu_dash_panel",
                "rule_title": "MenuDashPanel.tsx is an oversized dispatch component",
                "severity": "large",
                "area": "frontend",
                "file_path": "frontend/components/MenuDashPanel.tsx",
                "line_number": None,
                "description": (
                    f"frontend/components/MenuDashPanel.tsx is {fe_lines} lines, "
                    f"almost entirely a long department+itemKey ternary/if chain "
                    f"dispatching to each department's own bespoke board "
                    f"component. This codebase's own history documents a real "
                    f"bug caused by this exact shape (an unconditional earlier "
                    f"branch in the chain silently shadowing a later, more "
                    f"specific one -- the same root-cause pattern as the "
                    f"backend route-shadowing rule above, just in JSX)."
                ),
                "evidence": f"{fe_lines} lines, one large department/itemKey dispatch chain",
                "recommendation": (
                    "Replace the manual ternary chain with a real lookup table "
                    "keyed by `${department}:${itemKey}` mapping to a component "
                    "reference, resolved with a single object lookup instead of "
                    "sequential conditions -- removes the whole class of "
                    "order-dependent shadowing bugs this file's current shape "
                    "allows. A structural refactor, not a small/medium change."
                ),
            })

    # -- missing test coverage: backend/core/*.py modules with no matching
    #    backend/tests/test_*.py file. Reported as ONE aggregate finding
    #    (a real, systemic gap), not one finding per untested file, matching
    #    the "systemic, not per-instance" framing this rule tier is for.
    backend_core_dir = os.path.join(repo_root(), "backend", "core")
    backend_tests_dir = os.path.join(repo_root(), "backend", "tests")
    if os.path.isdir(backend_core_dir):
        core_modules = {
            os.path.splitext(f)[0]
            for f in os.listdir(backend_core_dir)
            if f.endswith(".py") and not f.startswith("__")
        }
        tested_modules = set()
        if os.path.isdir(backend_tests_dir):
            for f in os.listdir(backend_tests_dir):
                if f.startswith("test_") and f.endswith(".py"):
                    tested_modules.add(f[len("test_"):-len(".py")])

        untested = sorted(core_modules - tested_modules)
        coverage_pct = (
            round(100 * (len(core_modules) - len(untested)) / len(core_modules), 1)
            if core_modules else 0
        )

        if coverage_pct < 25:
            findings.append({
                "rule_key": "missing_test_coverage",
                "rule_title": "backend/core/ has minimal real pytest coverage",
                "severity": "large",
                "area": "backend",
                "file_path": "backend/tests/",
                "line_number": None,
                "description": (
                    f"Only {len(tested_modules & core_modules)} of "
                    f"{len(core_modules)} backend/core/*.py modules "
                    f"({coverage_pct}%) have a matching backend/tests/"
                    f"test_*.py file. This codebase's own CLAUDE.md already "
                    f"documents this as a known gap (76 loose, print-based "
                    f"test_*.py scripts at the repo root, not real pytest "
                    f"assertions) -- reported here as a real, systemic "
                    f"finding rather than left as an unenforced note."
                ),
                "evidence": f"{len(untested)} untested modules, e.g.: {', '.join(untested[:8])}{'...' if len(untested) > 8 else ''}",
                "recommendation": (
                    "Prioritize real pytest coverage for the highest-risk "
                    "modules first (anything with a documented history of "
                    "the missing-save_graph() bug class, and every module "
                    "backing a compliance/funding/payment action), landing "
                    "new tests under backend/tests/ per this codebase's own "
                    "established convention -- a large, ongoing effort, not "
                    "a single change."
                ),
            })

    return findings


ALL_RULES = [
    rule_missing_save_graph,
    rule_route_shadowing,
    rule_missing_acl_gate,
    rule_structural_smells,
]
