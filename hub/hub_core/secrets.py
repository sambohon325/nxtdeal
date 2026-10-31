"""
Secrets management abstraction, NXTDeal Hub copy (security-hardening pass,
2026-07-20, Task #13).

A vendored, standalone sibling of backend/core/secrets.py -- same reasoning as
hub/hub_core/auth.py's own vendored copy of backend/core/auth.py's hashing
primitives (see that module's own docstring): hub/ is deployed as its own isolated
Coolify app whose Base Directory is `hub/`, so a runtime import reaching into the
sibling backend/ directory works locally but crashes in production the moment
Nixpacks/Coolify packages only hub/'s own contents into the built container. This
module is entirely stdlib (no third-party deps, no cross-directory imports), so a
straight, kept-in-sync copy is the safe fix, exactly like hub_core/auth.py already
established. **Keep this in sync with backend/core/secrets.py** if the chokepoint's
own behavior or interface ever changes there.

Wraps every real secret the Hub application reads: NXTDEAL_HUB_KEY (the Hub's own
shared-secret admin-API gate, hub/app.py's _check_hub_key), DEALEROS_NETWORK_KEY
(the same network-wide shared secret every dealer tenant uses too, read here by
every hub_core/*.py module that calls a tenant's own /network/* routes
server-to-server), and DEALEROS_AUTH_SECRET (read only by this package's own vendored
hub_core/auth.py, when hashing/signing a freshly-provisioned dealer's first ADMIN
credential during onboarding -- see that module's own docstring for why it must
match backend/core/auth.py's real value exactly).

Before this module, the identical DEALEROS_NETWORK_KEY fallback string
("dev-only-insecure-network-key-change-me") was independently copy-pasted into 8
separate files across hub/hub_core/ -- confirmed via a real grep across this whole
directory before writing this catalog, not assumed. Every one of those call sites is
migrated to call get_secret() here instead, so there's exactly one real source of
truth for that fallback string going forward, and exactly one place a real dev-
fallback-in-use detection needs to live for the whole Hub application.
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional, Protocol


class SecretsBackend(Protocol):
    def read(self, name: str) -> Optional[str]:
        ...


class EnvVarBackend:
    def read(self, name: str) -> Optional[str]:
        return os.environ.get(name)


@dataclass(frozen=True)
class SecretSpec:
    name: str
    description: str
    dev_fallback: Optional[str]
    used_by: str


# Every secret the Hub application genuinely reads today, confirmed via a real grep
# of every os.environ.get()/os.getenv() call across hub/app.py and hub/hub_core/*.py
# before this catalog was written.
KNOWN_SECRETS = (
    SecretSpec(
        name="NXTDEAL_HUB_KEY",
        description="Shared secret gating every NXTDeal-staff-only Hub console route.",
        dev_fallback="dev-only-insecure-hub-key-change-me",
        used_by="hub/app.py's _check_hub_key",
    ),
    SecretSpec(
        name="DEALEROS_NETWORK_KEY",
        description=(
            "Shared secret between every dealer tenant instance and the NXTDeal Hub, "
            "gating the server-to-server anonymous-network-snapshot/AI-management/"
            "operational-health/storage-snapshot pipelines the Hub console reads."
        ),
        dev_fallback="dev-only-insecure-network-key-change-me",
        used_by="hub_core/network_collector.py and 7 other hub_core/*.py modules",
    ),
    SecretSpec(
        name="DEALEROS_AUTH_SECRET",
        description=(
            "HMAC signing secret for employee session tokens -- read here only when "
            "hashing a freshly-provisioned dealer's first ADMIN credential, so it "
            "must match the real backend's own value exactly."
        ),
        dev_fallback="dev-only-insecure-secret-change-me",
        used_by="hub_core/auth.py",
    ),
)

_KNOWN_SECRETS_BY_NAME = {spec.name: spec for spec in KNOWN_SECRETS}

_backend: SecretsBackend = EnvVarBackend()


def set_backend(backend: SecretsBackend) -> None:
    global _backend
    _backend = backend


def get_secret(name: str, dev_fallback: Optional[str] = None) -> Optional[str]:
    """The one real chokepoint every secret read in the Hub application should go
    through -- see backend/core/secrets.py's get_secret() for the full behavior
    contract this mirrors exactly."""

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
    actually configured" (e.g. hub_core/infra_security.py's own Hub-key/network-key
    presence check) want this, not a value that's always non-empty because a fallback
    silently filled it in."""

    value = _backend.read(name)

    return value not in (None, "")


def is_using_dev_fallback(name: str) -> bool:
    spec = _KNOWN_SECRETS_BY_NAME.get(name)

    if spec is None or spec.dev_fallback is None:
        return False

    real_value = _backend.read(name)

    return real_value is None or real_value == "" or real_value == spec.dev_fallback


def get_secrets_posture() -> dict:
    """A real, per-secret report of whether this Hub process is currently running on
    a real, configured value or a known-insecure dev fallback. Never returns the
    actual secret VALUE, configured or fallback -- only whether one is configured."""

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
    its insecure dev fallback -- called once, at process startup, inside hub/app.py's
    lifespan() hook. See backend/core/secrets.py's warn_on_dev_fallbacks() for the
    full behavior contract this mirrors exactly."""

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
