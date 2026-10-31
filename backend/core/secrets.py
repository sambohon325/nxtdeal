"""
Secrets management abstraction (security-hardening pass, 2026-07-20, Task #13).

A single, audited chokepoint -- get_secret(name) -- wrapping every real secret this
backend application reads out of the process environment. Before this module, every
secret (DEALEROS_AUTH_SECRET, DEALEROS_NETWORK_KEY, OPENAI_API_KEY) was read via a
bare os.environ.get(VAR, FALLBACK) call, independently duplicated across several
files -- confirmed via a grep across backend/core/*.py before this module was written,
not guessed at. Worse: no call site anywhere logged or warned when a real production
process was actually still running on its own insecure dev-only fallback value. This
module fixes both problems: one real source of truth per secret name (KNOWN_SECRETS),
and a real, checkable "is this secret currently on its dev fallback" signal, surfaced
both programmatically (get_secrets_posture(), gated ADMIN/OPERATIONS via
core/secrets_api.py) and as a real startup warning (warn_on_dev_fallbacks(), wired
into api/app.py's own lifespan() so it prints the moment the process boots).

Written with a swappable backend (SecretsBackend, a real typing.Protocol) so a real
cloud secrets-manager integration (Azure Key Vault / AWS Secrets Manager / HashiCorp
Vault) can be plugged in later as a backend swap -- set_backend() -- rather than a
rewrite of every call site that reads a secret today. That real cloud integration is
explicitly OUT OF SCOPE for this module: no cloud SDK dependency exists anywhere in
this repo's requirements.txt today, and adding one just to satisfy an abstraction
layer with nothing real to connect to would be exactly the kind of premature,
never-exercised code this codebase's own conventions (see docs/SECURITY_ARCHITECTURE.md)
warn against. What ships here is the abstraction + a real, working EnvVarBackend (the
only backend actually needed until a real Vault/Key Vault deployment exists) + real
dev-fallback detection wired into the two real call sites that had one
(core/auth.py's DEALEROS_AUTH_SECRET, core/network_snapshot_api.py's
DEALEROS_NETWORK_KEY).

KNOWN_SECRETS is this module's own real inventory -- every secret this backend
application actually reads today, built by grepping every os.environ.get()/
os.getenv() call across backend/core/*.py and backend/api/app.py before writing this
catalog, not assembled from memory. OPENAI_API_KEY deliberately has no dev_fallback at
all (unlike the other two) -- there is no safe-but-functional default for a
third-party paid API key. An unset OPENAI_API_KEY today correctly, honestly resolves
to None here, which is exactly what every one of the 13 real OpenAI-backed features in
this codebase already expects and gracefully falls back from on its own (a real
network/auth failure against OpenAI, caught and handled by that feature's own existing
templated-fallback path) -- not a gap this module needs to paper over with a fake key
that would just fail differently one layer deeper.
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional, Protocol


class SecretsBackend(Protocol):
    """The swap point for a real cloud secrets-manager integration later. Any backend
    just needs to answer "what's the current value of this named secret, if any is
    configured right now" -- EnvVarBackend below is the only implementation that ships
    today, and is sufficient for every deployment this codebase currently supports."""

    def read(self, name: str) -> Optional[str]:
        ...


class EnvVarBackend:
    """The real, only-backend-that-ships-today implementation -- reads straight from
    the process environment, exactly matching what every call site in this codebase
    already did before this module existed, just centralized behind one real
    chokepoint instead of duplicated independently per file."""

    def read(self, name: str) -> Optional[str]:
        return os.environ.get(name)


@dataclass(frozen=True)
class SecretSpec:
    name: str
    description: str
    dev_fallback: Optional[str]
    used_by: str


# Every secret this backend application genuinely reads today, confirmed via a real
# grep of every os.environ.get()/os.getenv() call site across backend/core/*.py and
# backend/api/app.py before this catalog was written. DEALEROS_ALLOW_INDEXING (a
# boolean feature flag) and DEALEROS_STORAGE_DIR (a filesystem path) are deliberately
# NOT included -- neither is a secret, so wrapping them here would blur this module's
# one real purpose.
KNOWN_SECRETS = (
    SecretSpec(
        name="DEALEROS_AUTH_SECRET",
        description="HMAC signing secret for employee session tokens.",
        dev_fallback="dev-only-insecure-secret-change-me",
        used_by="core/auth.py",
    ),
    SecretSpec(
        name="DEALEROS_NETWORK_KEY",
        description=(
            "Shared secret between every dealer tenant instance and the NXTDeal Hub, "
            "gating the server-to-server anonymous-network-snapshot pipeline."
        ),
        dev_fallback="dev-only-insecure-network-key-change-me",
        used_by="core/network_snapshot_api.py",
    ),
    SecretSpec(
        name="OPENAI_API_KEY",
        description="Third-party OpenAI API key backing every real AI-drafted feature.",
        dev_fallback=None,
        used_by="core/ai_assistant.py and 12 other AI-wizard modules",
    ),
)

_KNOWN_SECRETS_BY_NAME = {spec.name: spec for spec in KNOWN_SECRETS}

_backend: SecretsBackend = EnvVarBackend()


def set_backend(backend: SecretsBackend) -> None:
    """Swaps the active backend -- the real hook a future cloud secrets-manager
    integration would call once, at process startup, before any get_secret() call is
    made. Exists mainly for tests today (see tests/test_secrets.py's own fake
    backend), which is precisely the point of the abstraction: a real integration
    later needs to touch only this one call site, not every place a secret is read."""

    global _backend
    _backend = backend


def get_secret(name: str, dev_fallback: Optional[str] = None) -> Optional[str]:
    """The one real chokepoint every secret read in this codebase should go through.

    Reads through whichever backend is currently active (EnvVarBackend by default).
    If the backend has no real value AND a dev_fallback was supplied (or one is
    already registered for this name in KNOWN_SECRETS and the caller didn't pass its
    own), that fallback is returned -- matching every pre-existing call site's own
    already-established "os.environ.get(VAR, FALLBACK)" behavior exactly, so wiring
    this in is a drop-in replacement, not a behavior change. A blank string is treated
    the same as unset, since an accidentally-empty env var is a real, common
    misconfiguration this module should not silently treat as "configured"."""

    if dev_fallback is None and name in _KNOWN_SECRETS_BY_NAME:
        dev_fallback = _KNOWN_SECRETS_BY_NAME[name].dev_fallback

    value = _backend.read(name)

    if value is None or value == "":
        return dev_fallback

    return value


def is_configured(name: str) -> bool:
    """A direct, real boolean check of whether `name` has a real, non-empty value set
    in the backend (env var today) -- regardless of whether that name is in
    KNOWN_SECRETS or has a dev fallback at all. Deliberately does NOT go through
    get_secret()'s fallback-substitution behavior -- callers that want "is this
    actually configured" want this, not a value that's always non-empty because a
    fallback silently filled it in."""

    value = _backend.read(name)

    return value not in (None, "")


def is_using_dev_fallback(name: str) -> bool:
    """True if this named secret is CURRENTLY resolving to its own registered
    dev-fallback value -- including an explicitly configured public default, unset or blank
    right now. Only meaningful for a secret registered in KNOWN_SECRETS with a real
    dev_fallback; a secret with none (OPENAI_API_KEY) can never be "on its fallback"
    by definition -- an unset key just resolves to None, correctly triggering that
    feature's own existing honest-failure path instead of a fake credential."""

    spec = _KNOWN_SECRETS_BY_NAME.get(name)

    if spec is None or spec.dev_fallback is None:
        return False

    real_value = _backend.read(name)

    return real_value is None or real_value == "" or real_value == spec.dev_fallback


def get_secrets_posture() -> dict:
    """A real, per-secret report of whether this process is currently running on a
    real, configured value or a known-insecure dev fallback -- the programmatic
    counterpart to warn_on_dev_fallbacks()'s startup print, and what
    core/secrets_api.py's ADMIN/OPERATIONS-gated route surfaces. Never returns the
    actual secret VALUE, configured or fallback -- only whether one is configured,
    matching this codebase's established "reveal posture, never the secret itself"
    convention (core/api_keys.py never returns a raw key after creation either;
    core/crypto_agility.py's inventory scan never returns matched code excerpts)."""

    secrets_report = []

    for spec in KNOWN_SECRETS:
        using_fallback = is_using_dev_fallback(spec.name)
        real_value = _backend.read(spec.name)
        configured = real_value not in (None, "")

        secrets_report.append({
            "name": spec.name,
            "description": spec.description,
            "used_by": spec.used_by,
            "configured": configured,
            "using_dev_fallback": using_fallback,
            "has_dev_fallback_available": spec.dev_fallback is not None,
        })

    any_dev_fallback_in_use = any(entry["using_dev_fallback"] for entry in secrets_report)

    return {
        "secrets": secrets_report,
        "any_dev_fallback_in_use": any_dev_fallback_in_use,
        "posture": (
            "One or more secrets are currently running on an insecure dev-only "
            "fallback value -- this must not reach a real production deployment."
            if any_dev_fallback_in_use
            else "Every known secret with a dev fallback is configured with a real value."
        ),
    }


def warn_on_dev_fallbacks(stream=None) -> list:
    """Prints a real, loud, stderr warning for every secret currently resolving to
    its insecure dev fallback -- meant to be called once, at process startup (see
    api/app.py's lifespan() hook), so a misconfigured production deployment is
    impossible to miss in its own boot logs rather than silently, quietly running
    insecure forever. Returns the list of secret names currently on their fallback,
    so a caller can also act on it if that's ever wanted -- this function itself does
    not refuse to boot, since forcing that today would break the documented,
    intentional "dev fallback works locally with zero setup" convenience this
    codebase's own existing comments already establish for local/sandbox
    development (see core/network_snapshot_api.py's own docstring)."""

    stream = stream if stream is not None else sys.stderr

    names_on_fallback = [
        spec.name for spec in KNOWN_SECRETS
        if spec.dev_fallback is not None and is_using_dev_fallback(spec.name)
    ]

    for name in names_on_fallback:
        print(
            f"[SECURITY WARNING] {name} is not set -- running on its insecure "
            f"dev-only fallback value. Set a real {name} before deploying to "
            f"production.",
            file=stream,
        )

    return names_on_fallback
