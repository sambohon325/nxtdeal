"""Inventory app surfaces without importing or running application code."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def build_inventory():
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "backend", "frontend", "hub", "network-connect-extension"],
        cwd=ROOT,
    ).decode().split("\0")
    sources, routes, pages, errors = [], [], [], []
    methods = {"get", "post", "put", "patch", "delete", "options", "head", "websocket", "api_route"}
    for name in sorted(n for n in names if n):
        path = ROOT / name
        if path.suffix not in {".py", ".ts", ".tsx", ".js", ".mjs"} or not path.is_file():
            continue
        data = path.read_bytes()
        sources.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
        if name.startswith("frontend/app/") and path.name in {"page.tsx", "route.ts"}:
            pages.append(name)
        if path.suffix != ".py" or not (name.startswith("backend/api/") or name in {"hub/app.py"}):
            continue
        try:
            tree = ast.parse(data.decode("utf-8-sig"), filename=name)
        except (SyntaxError, UnicodeError) as exc:
            errors.append({"path": name, "error": type(exc).__name__})
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr
                if method not in methods:
                    continue
                route = decorator.args[0] if decorator.args else None
                routes.append({"path": name, "line": node.lineno, "handler": node.name,
                               "method": method.upper(),
                               "declared_path": route.value if isinstance(route, ast.Constant) else None})
    return {
        "scope": "Tracked and non-ignored local source inventory; not proof of authorization, route registration or runtime readiness. Router prefixes and dynamic routes require runtime reconciliation.",
        "counts": {"source_files": len(sources), "route_declarations": len(routes), "frontend_entries": len(pages)},
        "source_files": sources, "route_declarations": routes, "frontend_entries": pages,
        "parse_errors": errors,
    }


if __name__ == "__main__":
    target = ROOT / "docs" / "compliance" / "workspace-inventory.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    inventory = build_inventory()
    target.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(target), **inventory["counts"], "parse_errors": len(inventory["parse_errors"])}))
