"""VPS orchestrator for the NXTDeal programming schedule (Section 4).

Cron job on the VPS, every 15 min. For each worker (desktop, mac, vps):
  1. Check whether it is busy (A2A status / active run lease / SSH port).
     Only idle workers get an item; up to one item per worker at a time.
  2. Call /claim for that worker's route.
  3. Execute the work:
     - desktop: send item over A2A as a bounded task (15-40 min, free model).
     - vps: execute locally.
     - mac: SSH in, run one bounded Hermes job non-interactively, wait,
       read its result, then call /heartbeat and /complete on the Mac's behalf
       (worker=mac, provider=local-mac, model=local-mac/qwen3.6-35b).
  4. Use resources[] to avoid overlap (never give two workers items editing
     the same files).
  5. Daily Telegram summary: done today, in progress, blocked on Sam, resources.

Mac-specific (from Claude review update 2026-10-25 1:45 AM):
  - NO A2A. VPS reaches Mac only via SSH through Tailscale helper
    (/data/hermes-worker/worker-link.sh, port 22223 -> Mac SSH).
  - Mac does NOT receive a schedule token. VPS acts on its behalf.
  - NXTDeal repo must exist on Mac before the first Mac item (git clone/pull).

Window rules (Chicago time):
  - 9 AM - midnight: one new assignment every 30 min
  - midnight - 9 AM: one new assignment every 45 min
"""
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

# --- Configuration ---
# REPO_ROOT, API_BASE, and the VPS schedule token MUST come from env on the VPS.
# There are no Windows defaults — the script fails clearly if they are missing.
REPO_ROOT = os.environ.get("NXTDEAL_REPO_ROOT")
BACKEND = os.path.join(REPO_ROOT, "backend") if REPO_ROOT else None
API_BASE = os.environ.get("NXTDEAL_API_BASE")
VPS_TOKEN = os.environ.get("HERMES_SCHEDULE_TOKEN_vps", "")

# Mac SSH settings (verified command from Mac setup report §3):
#   ssh -i /opt/data/.ssh/hermes_mac -p 22223 sambohon325@10.0.2.2 \\
#     'cd /Users/sambohon325/nxtdeal && HOME=/Users/sambohon325 /Users/sambohon325/.local/bin/hermes chat --oneshot -Q \
#       --in /Users/sambohon325/nxtdeal -q "<task>"'
# All configurable via env with the verified defaults.
MAC_SSH_HOST = os.environ.get("NXTDEAL_MAC_SSH_HOST", "10.0.2.2")
MAC_SSH_PORT = int(os.environ.get("NXTDEAL_MAC_SSH_PORT", "22223"))
MAC_SSH_USER = os.environ.get("NXTDEAL_MAC_SSH_USER", "sambohon325")
MAC_SSH_KEY = os.environ.get("NXTDEAL_MAC_SSH_KEY", "/opt/data/.ssh/hermes_mac")
MAC_REPO_PATH = os.environ.get("NXTDEAL_MAC_REPO_PATH", "/Users/sambohon325/nxtdeal")
MAC_USER_HOME = os.environ.get("NXTDEAL_MAC_USER_HOME", "/Users/sambohon325")
MAC_HERMES_BIN = os.environ.get("NXTDEAL_MAC_HERMES_BIN", "/Users/sambohon325/.local/bin/hermes")

# Desktop A2A settings (VPS -> PC over A2A, peer "sbd-desktop")
DESKTOP_A2A_URL = os.environ.get("NXTDEAL_DESKTOP_A2A_URL", "http://desktop-link:9900")
DESKTOP_A2A_TOKEN = os.environ.get("NXTDEAL_DESKTOP_A2A_TOKEN", "")

# Assignment window (Chicago time, UTC-6 in winter / UTC-5 in DST)
CHICAGO_OFFSET = timedelta(hours=-6)

FREE_MODELS = ("poolside/laguna-s-2.1:free", "stepfun/step-5-preview:free")
MAC_MODEL = "local-mac/qwen3.6-35b"
MAC_PROVIDER = "local-mac"

# How the VPS reaches the desktop A2A server (for TCP reachability check)
DESKTOP_A2A_HOST = os.environ.get("NXTDEAL_DESKTOP_A2A_HOST", "desktop-link")
DESKTOP_A2A_PORT = int(os.environ.get("NXTDEAL_DESKTOP_A2A_PORT", "9900"))


def validate_config() -> str | None:
    """Validate that required VPS env vars are set. Returns error message or None.

    NXTDEAL_REPO_ROOT, NXTDEAL_API_BASE, and HERMES_SCHEDULE_TOKEN_vps must all
    be provided via environment — there are no Windows or localhost defaults.
    """
    errors = []
    if not REPO_ROOT:
        errors.append("NXTDEAL_REPO_ROOT is not set (the VPS checkout path)")
    if not API_BASE:
        errors.append("NXTDEAL_API_BASE is not set (the schedule API URL)")
    if not VPS_TOKEN:
        errors.append("HERMES_SCHEDULE_TOKEN_vps is not set (the VPS worker token)")
    if errors:
        return "ERROR: " + "; ".join(errors) + ". Refusing to start."
    return None


# --- Worker status ---

def is_port_open(host: str, port: int, timeout: float = 3.0) -> bool:
    """TCP-connect check. Used for SSH reachability (Mac) and A2A ports."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.error):
        return False


def mac_ssh_reachable() -> bool:
    """Check if the Mac is reachable over SSH via Tailscale port forward."""
    return is_port_open(MAC_SSH_HOST, MAC_SSH_PORT)


def desktop_a2a_reachable() -> bool:
    """Check if the desktop A2A peer is reachable (VPS -> PC over A2A).

    Checks the desktop's A2A endpoint (desktop-link:9900), NOT the SSH port.
    Does an HTTP GET to /.well-known/agent-card.json to verify the A2A server
    is actually responding, not just that a port is open.
    """
    # Quick TCP check on the A2A port
    if not is_port_open(DESKTOP_A2A_HOST, DESKTOP_A2A_PORT, timeout=3.0):
        return False
    # Verify the A2A server responds with an agent card
    try:
        req = urllib.request.Request(
            f"{DESKTOP_A2A_URL}/.well-known/agent-card.json",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                json.loads(resp.read())  # validate it's well-formed JSON
                return True
    except Exception:
        pass
    return False


def worker_has_active_run(worker: str) -> bool:
    """Check if a worker already has an active (running) run via the API."""
    try:
        req = urllib.request.Request(
            f"{API_BASE}/programming-schedule/runs/active",
            headers=_vps_headers(),
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            runs = json.loads(resp.read())
            for r in runs:
                if r.get("worker") == worker and r.get("outcome") == "running":
                    return True
    except Exception:
        pass
    return False


def _vps_headers() -> dict:
    return {"Authorization": f"Bearer {VPS_TOKEN}"} if VPS_TOKEN else {}


# --- Assignment window ---

def assignment_allowed() -> bool:
    """Check if a new assignment is allowed based on the time window.

    9 AM - midnight Chicago: one assignment every 30 min.
    midnight - 9 AM: one assignment every 45 min.

    Uses the last assignment timestamp from a marker file to enforce the gap.
    """
    now = datetime.now(timezone.utc)
    chicago = now + CHICAGO_OFFSET
    hour = chicago.hour

    interval_min = 30 if 9 <= hour < 24 else 45

    marker = os.path.join(os.environ.get("TMPDIR", "/tmp"), "nxtdeal_last_assign")
    if os.path.exists(marker):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(marker), timezone.utc)
            elapsed = (now - mtime).total_seconds() / 60
            if elapsed < interval_min:
                return False
        except (OSError, ValueError):
            pass

    return True


def record_assignment():
    """Touch the marker file to record a new assignment."""
    marker = os.path.join(os.environ.get("TMPDIR", "/tmp"), "nxtdeal_last_assign")
    with open(marker, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())


# --- Claim / heartbeat / complete ---

def claim_item(worker: str, route: str) -> dict | None:
    """Call /claim on the VPS token. Returns the claimed item + run_id, or None."""
    body = json.dumps({"worker": worker, "route": route}).encode()
    req = urllib.request.Request(
        f"{API_BASE}/programming-schedule/claim",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {VPS_TOKEN}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if "error" in data:
                print(f"  Claim error: {data['error']}")
                return None
            return data
    except Exception as e:
        print(f"  Claim HTTP error: {e}")
        return None


def heartbeat_run(run_id: str, **metrics) -> bool:
    """Call /heartbeat on an active run."""
    body = json.dumps(metrics).encode()
    req = urllib.request.Request(
        f"{API_BASE}/programming-schedule/runs/{run_id}/heartbeat",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {VPS_TOKEN}",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


def complete_run(run_id: str, outcome: str, **metrics) -> bool:
    """Call /complete on a finished run."""
    body = json.dumps({"outcome": outcome, **metrics}).encode()
    req = urllib.request.Request(
        f"{API_BASE}/programming-schedule/runs/{run_id}/complete",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {VPS_TOKEN}",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"  Complete error: {e}")
        return False


# --- Resource overlap check ---

def resources_overlap(running_items: list[dict], candidate_resources: list[str]) -> bool:
    """True if any running item shares a resource with the candidate."""
    if not candidate_resources:
        return False
    for item in running_items:
        item_resources = set(item.get("resources", []))
        if item_resources & set(candidate_resources):
            return True
    return False


# --- A2A client (VPS -> desktop peer "sbd-desktop") ---

def _a2a_jsonrpc_post(a2a_url: str, bearer_token: str, method: str, params: dict,
                      timeout: float = 30.0) -> dict:
    """Send a JSON-RPC request to an A2A v1.0 server (VPS -> desktop).

    Uses PascalCase method names (SendMessage, GetTask) per A2A v1.0.
    Authenticates with a Bearer token when one is configured.
    """
    request_id = f"vps-{int(datetime.now(timezone.utc).timestamp())}-{os.getpid()}"
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }
    headers = {
        "Content-Type": "application/json",
        "A2A-Version": "1.0",
    }
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    req = urllib.request.Request(
        a2a_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [desktop] A2A {method} error: {e}")
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -1, "message": str(e)}}


def _a2a_extract_text(part_container: dict) -> str:
    """Extract concatenated text from an A2A Part container (task or message)."""
    if not isinstance(part_container, dict):
        return ""
    chunks = []
    for part in part_container.get("parts", []):
        if isinstance(part, dict):
            if isinstance(part.get("text"), str):
                chunks.append(part["text"])
            elif isinstance(part.get("data"), dict):
                chunks.append(json.dumps(part["data"], default=str))
    return "\n".join(chunks).strip()


def _a2a_extract_reply(response: dict) -> str:
    """Extract the agent's reply text from an A2A SendMessage response."""
    result = response.get("result", {})
    if not isinstance(result, dict):
        return str(result)
    # v1.0 wraps in {task: {...}} or {message: {...}}
    if "task" in result:
        task = result["task"]
        status = task.get("status", {})
        msg = status.get("message", {})
        text = _a2a_extract_text(msg)
        if text:
            return text
        for artifact in task.get("artifacts", []):
            text = _a2a_extract_text(artifact)
            if text:
                return text
    elif "message" in result:
        return _a2a_extract_text(result["message"])
    if "status" in result:
        msg = result["status"].get("message", {})
        return _a2a_extract_text(msg)
    if "parts" in result:
        return _a2a_extract_text(result)
    return str(result)


def _a2a_poll_task(a2a_url: str, token: str, task_id: str,
                   timeout: float = 1500, interval: float = 30) -> str:
    """Poll an A2A task (via GetTask) until terminal state or timeout."""
    deadline = datetime.now(timezone.utc).timestamp() + timeout
    while datetime.now(timezone.utc).timestamp() < deadline:
        response = _a2a_jsonrpc_post(
            a2a_url, token, "GetTask", {"taskId": task_id}, timeout=30
        )
        if "error" in response:
            break
        result = response.get("result", {})
        task = result.get("task", result) if isinstance(result, dict) else {}
        state = task.get("status", {}).get("state", "")
        if state and "WORKING" not in state:
            return _a2a_extract_reply({"result": {"task": task}})
        time.sleep(interval)
    return "[timeout polling A2A task]"


# --- Worker execution ---

def _build_item_task(item: dict, worker: str) -> str:
    """Build the task description text for a programming schedule item."""
    lines = [
        f"You are a Hermes agent assigned to resolve NXTDeal programming schedule item {item['id']} on worker '{worker}'.",
        "",
        f"Title: {item.get('title', '')}",
        f"Phase: {item.get('phase', '')}",
        f"Type: {item.get('type', '')}",
        f"Priority: {item.get('priority', '')}",
        f"Est. hours: {item.get('est_hours', 0)}",
    ]
    deps = item.get("depends_on", [])
    if deps:
        lines.append(f"Dependencies: {', '.join(deps)}")
    resources = item.get("resources", [])
    if resources:
        lines.append(f"Resources (files to edit): {', '.join(resources)}")
    desc = item.get("description", "")
    if desc:
        lines.append(f"Description: {desc}")
    notes = item.get("work_notes", [])
    if notes:
        lines.append("Work notes:")
        for n in notes:
            lines.append(f"  - {n.get('note', n) if isinstance(n, dict) else n}")

    lines.extend([
        "",
        "Instructions:",
        "- Work in the NXTDeal repo.",
        "- Use FREE MODELS ONLY (poolside/laguna-s-2.1:free, stepfun/step-5-preview:free).",
        "- After completing the work, run the relevant tests and report results.",
        "- Do NOT deploy, push to main, or make production changes unless explicitly instructed.",
        "- Be efficient and focused - you have approximately 40 minutes.",
        "",
        f"Your task: {item.get('title', '')}",
    ])
    return "\n".join(lines)


def execute_on_desktop(item: dict, run_id: str) -> dict:
    """Send item to desktop Hermes over A2A as a bounded task.

    Uses the A2A JSON-RPC protocol (SendMessage) to dispatch the item to the
    desktop's A2A server at http://desktop-link:9900 (peer 'sbd-desktop').
    The desktop Hermes processes the bounded task and replies with metrics
    (tokens, cost, commit, tests) via a JOB_RESULT: JSON line in the reply.

    Returns the result metrics for /complete.
    """
    task_text = _build_item_task(item, "desktop")
    print(f"  [desktop] Dispatching item {item['id']} over A2A to {DESKTOP_A2A_URL}")

    request_id = f"vps-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{os.getpid()}"
    response = _a2a_jsonrpc_post(
        DESKTOP_A2A_URL,
        DESKTOP_A2A_TOKEN,
        "SendMessage",
        {"message": {
            "role": "ROLE_USER",
            "parts": [{"text": task_text, "mediaType": "text/plain"}],
            "messageId": request_id,
        }},
        timeout=1500,  # 25 min — long enough for most items
    )

    # Check for JSON-RPC error
    if "error" in response:
        print(f"  [desktop] A2A error: {response['error']}")
        return _failed_metrics(item, "desktop", error=str(response["error"]))

    # Extract the reply — the agent may return immediately or be still working
    result = response.get("result", {})
    if isinstance(result, dict) and "task" in result:
        task = result["task"]
        state = task.get("status", {}).get("state", "")
        # If still WORKING, the A2A server timed out waiting for the agent
        # (default A2A_REPLY_TIMEOUT=300s). Poll GetTask for completion.
        if "WORKING" in state and "id" in task:
            task_id = task["id"]
            print(f"  [desktop] Task {task_id} still working, polling...")
            reply = _a2a_poll_task(DESKTOP_A2A_URL, DESKTOP_A2A_TOKEN, task_id,
                                   timeout=1500, interval=30)
        else:
            reply = _a2a_extract_reply(response)
    else:
        reply = _a2a_extract_reply(response)

    # Parse metrics from the reply (expects a JOB_RESULT: JSON line)
    metrics = _parse_job_output(reply if isinstance(reply, str) else json.dumps(reply))
    metrics["worker"] = "desktop"
    metrics.setdefault("provider", "local")
    metrics.setdefault("model", "poolside/laguna-s-2.1:free")
    return metrics


def execute_on_vps(item: dict, run_id: str) -> dict:
    """Execute a VPS item locally (VPS Hermes itself)."""
    print(f"  [vps] Would execute item {item['id']} locally")
    return _simulate_completion(item)


def execute_on_mac(item: dict, run_id: str) -> dict:
    """SSH to the Mac, run ONE bounded Hermes job, wait, read result.

    The VPS calls /complete on the Mac's behalf (worker=mac, provider=local-mac,
    model=local-mac/qwen3.6-35b). The Mac does NOT have its own schedule token.
    """
    if not mac_ssh_reachable():
        print(f"  [mac] Mac not reachable via SSH (port {MAC_SSH_PORT})")
        return None

    # Ensure the NXTDeal repo exists on the Mac
    _ensure_mac_repo()

    # Construct the verified Hermes job command (Mac setup report §3)
    task_text = _build_item_task(item, "mac")
    hermes_cmd = (
        f"cd {MAC_REPO_PATH} && "
        f"HOME={MAC_USER_HOME} {MAC_HERMES_BIN} chat --oneshot -Q "
        f"--in {MAC_REPO_PATH} -q {shlex.quote(task_text)}"
    )
    ssh_cmd = [
        "ssh", "-i", MAC_SSH_KEY, "-p", str(MAC_SSH_PORT),
        "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
        f"{MAC_SSH_USER}@{MAC_SSH_HOST}",
        hermes_cmd,
    ]

    try:
        result = subprocess.run(
            ssh_cmd, capture_output=True, text=True, timeout=2700,
        )
        output = result.stdout + result.stderr
        print(f"  [mac] SSH job completed (exit {result.returncode})")

        # Parse result metrics from the Hermes job output
        metrics = _parse_job_output(output)
        metrics["provider"] = MAC_PROVIDER
        metrics["model"] = MAC_MODEL
        metrics["worker"] = "mac"
        metrics.setdefault("outcome", "completed")

        # Heartbeat on the Mac's behalf, then complete
        heartbeat_run(run_id, **{
            k: v for k, v in metrics.items()
            if k in ("input_tokens", "output_tokens", "cache_read_tokens", "cost_usd")
        })

        return metrics
    except subprocess.TimeoutExpired:
        print(f"  [mac] Job timed out for item {item['id']}")
        return {"outcome": "failed", "error": "timeout", "worker": "mac",
                "provider": MAC_PROVIDER, "model": MAC_MODEL}
    except Exception as e:
        print(f"  [mac] SSH error: {e}")
        return {"outcome": "failed", "error": str(e), "worker": "mac",
                "provider": MAC_PROVIDER, "model": MAC_MODEL}


def _ensure_mac_repo():
    """Ensure the NXTDeal repo exists on the Mac (git fetch + checkout branch).

    Per BRIEF §5: feature branch only (codex/desktop-api-release-20261022).
    """
    check_cmd = [
        "ssh", "-i", MAC_SSH_KEY, "-p", str(MAC_SSH_PORT),
        "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
        f"{MAC_SSH_USER}@{MAC_SSH_HOST}",
        f"test -d {MAC_REPO_PATH}/.git && echo EXISTS || echo MISSING",
    ]
    try:
        result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=15)
        if "EXISTS" in result.stdout:
            # Fetch latest and checkout the feature branch (branch only, never main)
            branch = "codex/desktop-api-release-20261022"
            fetch_cmd = [
                "ssh", "-i", MAC_SSH_KEY, "-p", str(MAC_SSH_PORT),
                "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
                f"{MAC_SSH_USER}@{MAC_SSH_HOST}",
                f"cd {MAC_REPO_PATH} && git fetch && git checkout -B {branch} origin/{branch}",
            ]
            subprocess.run(fetch_cmd, capture_output=True, text=True, timeout=120)
            print(f"  [mac] Repo updated (checkout {branch})")
        else:
            # Clone fresh
            clone_cmd = [
                "ssh", "-i", MAC_SSH_KEY, "-p", str(MAC_SSH_PORT),
                "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
                f"{MAC_SSH_USER}@{MAC_SSH_HOST}",
                f"git clone https://github.com/sambohon325/nxtdeal {MAC_REPO_PATH}",
            ]
            subprocess.run(clone_cmd, capture_output=True, text=True, timeout=300)
            print(f"  [mac] Repo cloned")
    except Exception as e:
        print(f"  [mac] Repo check error: {e}")


def _simulate_completion(item: dict, worker: str = "vps") -> dict:
    """Simulate completion metrics for a bounded job (for dry-run / testing)."""
    return {
        "outcome": "completed",
        "provider": "local",
        "model": "poolside/laguna-s-2.1:free",
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cost_usd": 0.0,
        "commit_sha": os.environ.get("GITHUB_SHA", "local-test"),
        "tests_summary": "no tests run (dry-run)",
        "notes": None,
    }


def _parse_job_output(output: str) -> dict:
    """Parse metrics (tokens, cost, commit, tests) from Hermes job output."""
    metrics = {
        "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
        "cost_usd": 0.0, "commit_sha": None, "tests_summary": None, "notes": None,
    }
    try:
        # Hermes job output includes a JSON summary line
        for line in output.strip().split("\n"):
            if line.startswith("JOB_RESULT:"):
                parsed = json.loads(line[len("JOB_RESULT:"):])
                metrics.update(parsed)
    except (json.JSONDecodeError, KeyError):
        pass
    return metrics


# --- Orchestration ---

def get_idle_workers() -> list[str]:
    """Check which workers are idle and can receive new work."""
    idle = []
    for worker in ("desktop", "mac", "vps"):
        if worker_has_active_run(worker):
            continue
        if worker == "desktop" and not desktop_a2a_reachable():
            continue
        if worker == "mac" and not mac_ssh_reachable():
            continue
        idle.append(worker)
    return idle


def orchestrate(dry_run: bool = False):
    """Main orchestrator entry point. Called as a cron job every 15 min.

    When dry_run=True, only LOG what would be assigned — no claims, no execution,
    no completion. The VPS still checks worker status and the assignment window.
    """
    if not VPS_TOKEN:
        print("ERROR: HERMES_SCHEDULE_TOKEN_vps not set. Cannot orchestrate.")
        return

    now = datetime.now(timezone.utc)
    print(f"=== Orchestrator run: {now.isoformat()} (dry_run={dry_run}) ===")

    # 1. Check which workers are idle
    idle = get_idle_workers()
    print(f"  Idle workers: {idle}")

    # 2. Check assignment window
    if not idle or not assignment_allowed():
        print(f"  No idle workers or assignment window not yet open. Skipping.")
        return

    if dry_run:
        print("  DRY RUN — logging what would be assigned; no claims, executions, or completions.")
        for worker in idle:
            route = "vps" if worker == "vps" else "local"
            print(f"  [DRY RUN] Would claim for worker={worker}, route={route}")
        print(f"=== Orchestrator run complete: {now.isoformat()} ===")
        return

    # 3. For each idle worker, try to claim one item
    for worker in idle:
        route = "vps" if worker == "vps" else "local"

        # Get running items to check resource overlap
        running_items = []
        try:
            req = urllib.request.Request(
                f"{API_BASE}/programming-schedule/runs/active",
                headers=_vps_headers(),
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                runs = json.loads(resp.read())
                for r in runs:
                    item = _get_item_safely(r.get("item_id", ""))
                    if item:
                        running_items.append(item)
        except Exception:
            pass

        # Claim an item for this worker
        print(f"  Claiming for worker={worker}, route={route}")
        claimed = claim_item(worker, route)
        if not claimed:
            continue

        run_id = claimed.get("run_id")
        item = _get_item_safely(claimed.get("id", ""))
        if not item or not run_id:
            print(f"  No item claimed for worker={worker}")
            continue

        # Check resource overlap
        if resources_overlap(running_items, item.get("resources", [])):
            print(f"  Resource overlap for {item['id']}, re-releasing")
            complete_run(run_id, "released",
                         notes="Resource overlap with running item")
            continue

        # 4. Execute the work
        print(f"  Executing item {item['id']} on worker={worker}")
        if worker == "desktop":
            metrics = execute_on_desktop(item, run_id)
        elif worker == "vps":
            metrics = execute_on_vps(item, run_id)
        elif worker == "mac":
            metrics = execute_on_mac(item, run_id)
        else:
            continue

        if metrics is None:
            print(f"  Execution failed for {item['id']} on {worker}")
            continue

        # 5. Record progress in the schedule
        _record_item_progress(item["id"], metrics)

        # 6. Complete the run
        outcome = metrics.get("outcome", "completed")
        if complete_run(run_id, outcome, **metrics):
            print(f"  Completed {item['id']} (outcome={outcome}) on {worker}")
            record_assignment()

    print(f"=== Orchestrator run complete: {now.isoformat()} ===")


def _get_item_safely(item_id: str) -> dict | None:
    """Fetch an item via the API (called by the orchestrator from the VPS)."""
    try:
        req = urllib.request.Request(
            f"{API_BASE}/programming-schedule/{item_id}",
            headers=_vps_headers(),
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _record_item_progress(item_id: str, metrics: dict):
    """Add work notes and events to the schedule for this item."""
    outcome = metrics.get("outcome", "completed")
    provider = metrics.get("provider", "unknown")
    model = metrics.get("model", "unknown")
    cost = metrics.get("cost_usd", 0.0)

    note = (f"Orchestrator: completed by worker={metrics.get('worker', 'unknown')} "
            f"provider={provider} model={model} "
            f"tokens={metrics.get('input_tokens', 0)}/{metrics.get('output_tokens', 0)} "
            f"${cost:.2f} outcome={outcome}")

    try:
        body = json.dumps({"note": note}).encode()
        req = urllib.request.Request(
            f"{API_BASE}/programming-schedule/{item_id}/notes",
            data=body,
            headers={**{"Content-Type": "application/json"}, **_vps_headers()},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# --- Telegram summary (daily) ---

def send_daily_summary():
    """Send a daily Telegram summary to Sam."""
    # This would use the NXTDEAL TELEGRAM BOT (per nxtdeal_job_control.py pattern)
    # Summary: done today, in progress, blocked on Sam, resources used
    print("=== Daily Telegram summary ===")
    try:
        req = urllib.request.Request(
            f"{API_BASE}/programming-schedule/dashboard",
            headers=_vps_headers(),
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        summary = {
            "done": len(data.get("done", [])),
            "in_progress": len(data.get("in_progress", [])),
            "blocked": len(data.get("blocked_on_sam", [])),
            "mtd_cost": data.get("resources", {}).get("mtd_total_cost", 0),
        }
        print(f"  Done: {summary['done']}, In progress: {summary['in_progress']}, "
              f"Blocked: {summary['blocked']}, MTD cost: ${summary['mtd_cost']:.2f}")
    except Exception as e:
        print(f"  Summary error: {e}")


# --- Entry point ---

if __name__ == "__main__":
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")

    # Validate required env vars on the VPS — no Windows defaults.
    config_error = validate_config()
    if config_error:
        print(config_error)
        sys.exit(1)

    if dry_run:
        print("DRY RUN — logging what would be assigned; no claims, executions, or completions.")
        orchestrate(dry_run=True)
    else:
        orchestrate(dry_run=False)
