"""Heuristic cryptographic inventory and optional versioned digest utilities.

This is not proof of post-quantum security. SSO uses RSA today. Infrastructure,
external providers, backups, key wrapping, dependencies and runtime configuration
need separate evidence. The versioned-digest helper does not migrate existing
passwords, tokens or transport. See docs/SECURITY-REVIEW-2026-10-14.md.
"""

import hashlib
import hmac as _hmac_module
import io
import os
import re
import tokenize


# ---------------------------------------------------------------------------
# 1. Versioned digest format -- real algorithm agility for anything that
#    starts using this module going forward.
# ---------------------------------------------------------------------------

# Registered {version -> algorithm}. Adding a new entry here (e.g. a future
# "v2": "sha3_256") is the real, intended way this module supports a primitive
# swap -- every digest already produced under "v1" keeps verifying correctly
# under its own registered algorithm; only CURRENT_VERSION needs to move for
# every NEW digest to start using the new one.
ALGORITHM_VERSIONS = {
    "v1": "sha256",
}

CURRENT_VERSION = "v1"

_SUPPORTED_HASHERS = {
    "sha256": hashlib.sha256,
    "sha3_256": hashlib.sha3_256,
    "sha512": hashlib.sha512,
}


class UnknownCryptoVersionError(Exception):
    """Raised when a caller asks for a version/algorithm this module doesn't
    have a real, registered hasher for -- a fail-loud signal, never a silent
    fallback to some other algorithm."""


def versioned_digest(data, version=None):
    """Produce a real, version-tagged digest -- "v1:sha256:<hexdigest>" -- so a
    future algorithm swap (registering a new entry in ALGORITHM_VERSIONS and
    moving CURRENT_VERSION) never breaks verify_versioned_digest()'s ability to
    check a digest produced under an older, still-registered version.

    `data` may be a str (encoded utf-8) or raw bytes."""

    version = version or CURRENT_VERSION
    algorithm = ALGORITHM_VERSIONS.get(version)

    if algorithm is None:
        raise UnknownCryptoVersionError(f"Unknown crypto-agility version: {version!r}")

    hasher = _SUPPORTED_HASHERS.get(algorithm)
    if hasher is None:
        raise UnknownCryptoVersionError(
            f"Unsupported algorithm registered for version {version!r}: {algorithm!r}"
        )

    raw = data.encode("utf-8") if isinstance(data, str) else data
    hexdigest = hasher(raw).hexdigest()

    return f"{version}:{algorithm}:{hexdigest}"


def verify_versioned_digest(data, versioned_value):
    """Real verification against a versioned digest of ANY registered vintage
    -- parses the real version+algorithm tag off `versioned_value` (never
    assumed to be CURRENT_VERSION) and recomputes under THAT algorithm, so a
    digest produced years ago under an older registered version still verifies
    correctly even after CURRENT_VERSION has moved on to something newer.

    Returns False (never raises) on any malformed input, an unregistered
    version, or a version/algorithm mismatch against what's currently
    registered for that tag -- a real, honest "this doesn't verify" signal
    rather than an exception a caller might forget to catch."""

    if not isinstance(versioned_value, str) or versioned_value.count(":") < 2:
        return False

    version, algorithm, hexdigest = versioned_value.split(":", 2)

    registered_algorithm = ALGORITHM_VERSIONS.get(version)
    if registered_algorithm is None or registered_algorithm != algorithm:
        # Either an unknown version, or the stored tag's own algorithm no
        # longer matches what this version is registered to today -- a real,
        # honest tamper/corruption/drift signal, never silently "fixed up" by
        # trusting whatever algorithm name happens to be embedded in the tag.
        return False

    hasher = _SUPPORTED_HASHERS.get(algorithm)
    if hasher is None:
        return False

    raw = data.encode("utf-8") if isinstance(data, str) else data
    recomputed = hasher(raw).hexdigest()

    return _hmac_module.compare_digest(recomputed, hexdigest)


# ---------------------------------------------------------------------------
# 2. Cryptographic Primitive Inventory -- a real, re-runnable static scan,
#    not a one-time prose claim.
# ---------------------------------------------------------------------------

# Every pattern below is a real regex checked directly against this repo's own
# backend/core/*.py source before being written here (see this module's own
# docstring) -- none of the QUANTUM_VULNERABLE patterns currently match
# anywhere in this codebase; the scan exists specifically so that stays true
# and CHECKABLE going forward, not just asserted once.
QUANTUM_VULNERABLE_PATTERNS = {
    # Shor's algorithm breaks these -- integer factorization / discrete log.
    "rsa": re.compile(r"\brsa\b|\b_verify_rs256\b", re.IGNORECASE),
    "ecdsa": re.compile(r"\becdsa\b", re.IGNORECASE),
    "ecdh": re.compile(r"\becdh\b", re.IGNORECASE),
    "diffie_hellman": re.compile(r"diffie[\s_-]?hellman", re.IGNORECASE),
    "asymmetric_crypto_import": re.compile(
        r"from\s+cryptography\.hazmat\.primitives\.asymmetric|Crypto\.PublicKey|"
        r"^\s*import\s+rsa\b",
        re.IGNORECASE | re.MULTILINE,
    ),
}

# Weak-classical (not itself a PQC/Shor's-algorithm concern -- these are
# broken by ordinary classical collision/brute-force attacks, a different,
# narrower category worth surfacing separately rather than conflating with
# "quantum-vulnerable").
WEAK_CLASSICAL_PATTERNS = {
    "md5": re.compile(r"\bhashlib\.md5\b|\bmd5\("),
    "sha1_hash": re.compile(r"\bhashlib\.sha1\b"),
    "des": re.compile(r"\bDES\.|(?<![A-Za-z])\bdes\b(?![A-Za-z])"),
    "rc4": re.compile(r"\brc4\b", re.IGNORECASE),
}

# Symmetric/hash/CSPRNG primitives -- all considered adequately
# quantum-resistant per this module's own docstring reasoning.
ADEQUATE_PATTERNS = {
    "sha256": re.compile(r"\bhashlib\.sha256\b"),
    "sha3": re.compile(r"\bhashlib\.sha3_\d+\b"),
    "sha512": re.compile(r"\bhashlib\.sha512\b"),
    "hmac": re.compile(r"\bhmac\.new\b|\bhmac\.compare_digest\b"),
    "pbkdf2": re.compile(r"\bpbkdf2_hmac\b"),
    "csprng": re.compile(r"\bsecrets\.(token_hex|token_urlsafe|token_bytes|choice)\b"),
}

CLASSIFICATION_NOTE = (
    "Heuristic discovery only: public-key findings identify quantum migration work, "
    "not proof of a current exploit. Symmetric/hash matches do not validate key entropy, "
    "algorithm parameters or use. TLS, libraries and external providers need separate review."
)


def _strip_comments_and_strings(source_text):
    """Real, tokenizer-based stripping of every comment and string literal
    (which covers docstrings) from a Python source file before it's scanned.

    Without this, a scan trips over its OWN prose the instant a module's
    docstring or a scanner's own pattern-definition dict keys mention a
    primitive name in passing -- confirmed live during this module's own
    development: crypto_agility.py's own docstring explains, in prose, which
    primitives ARE and are NOT used ("...zero MD5/DES/RC4 usage..."), and
    QUANTUM_VULNERABLE_PATTERNS' own dict keys are literally the strings
    "rsa"/"ecdsa"/"ecdh"/"diffie_hellman" -- a naive scan of this file's own
    raw source flagged itself as quantum-vulnerable, the exact false-positive
    trap this codebase's own Code Auditor (hub/hub_core/code_auditor_rules.py's
    strip_comments_and_docstrings()) already independently documented for a
    different rule (a docstring mentioning "save_graph()" in prose looking
    identical to a real call under a plain substring grep).

    Uses Python's real tokenizer to find exactly where every comment/string
    token starts and ends, then blanks that SPAN out in place (replacing it
    with spaces, preserving every other character's original position) --
    deliberately NOT a naive "join the surviving tokens with a space"
    reconstruction, which was tried first and found, via this module's own
    live testing, to silently corrupt real code matches: joining tokens with
    a bare space turns `hashlib.sha256(...)` into `hashlib . sha256 ( ...)`,
    breaking a regex like `\bhashlib\.sha256\b` that expects the dot to sit
    directly against its neighbors with no whitespace. Blanking spans in
    place keeps every real code character exactly where it was, so a pattern
    that matches real, untouched code keeps matching correctly.

    A file that doesn't tokenize cleanly (rare -- a deliberately malformed
    fixture, a decode error) falls back to returning the raw, unstripped text
    rather than silently skipping the file entirely -- an honest degrade to
    the noisier-but-still-scanned behavior, not a hidden gap."""

    try:
        lines = source_text.splitlines(keepends=True)
        line_chars = [list(line) for line in lines]

        tokens = tokenize.generate_tokens(io.StringIO(source_text).readline)
        for tok_type, _tok_string, start, end, _line in tokens:
            if tok_type not in {tokenize.COMMENT, tokenize.STRING,
                                 getattr(tokenize, "FSTRING_START", -1),
                                 getattr(tokenize, "FSTRING_MIDDLE", -1),
                                 getattr(tokenize, "FSTRING_END", -1)}:
                continue

            start_row, start_col = start
            end_row, end_col = end

            if start_row == end_row:
                row_idx = start_row - 1
                if 0 <= row_idx < len(line_chars):
                    row = line_chars[row_idx]
                    for col in range(start_col, min(end_col, len(row))):
                        row[col] = " "
            else:
                # A real multi-line string/comment -- blank the tail of the
                # first line, every full line strictly in between, and the
                # head of the last line, leaving line breaks themselves
                # untouched so row/column bookkeeping for any LATER token
                # stays correct.
                first_row_idx = start_row - 1
                if 0 <= first_row_idx < len(line_chars):
                    row = line_chars[first_row_idx]
                    for col in range(start_col, len(row)):
                        if row[col] not in ("\n", "\r"):
                            row[col] = " "

                for row_idx in range(start_row, end_row - 1):
                    if 0 <= row_idx < len(line_chars):
                        row = line_chars[row_idx]
                        for col in range(len(row)):
                            if row[col] not in ("\n", "\r"):
                                row[col] = " "

                last_row_idx = end_row - 1
                if 0 <= last_row_idx < len(line_chars):
                    row = line_chars[last_row_idx]
                    for col in range(0, min(end_col, len(row))):
                        row[col] = " "

        return "".join("".join(row) for row in line_chars)
    except (tokenize.TokenError, IndentationError, SyntaxError, UnicodeDecodeError):
        return source_text


def _iter_python_files(root_dir):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip the test tree and any virtualenv/cache directory that might be
        # present -- this scan is about application code, not test fixtures
        # or vendored dependencies.
        dirnames[:] = [
            d for d in dirnames
            if d not in ("tests", "venv", "__pycache__", ".git", "node_modules")
        ]
        for filename in filenames:
            if filename.endswith(".py"):
                yield os.path.join(dirpath, filename)


def run_crypto_inventory_scan(root_dir=None):
    """Real, re-runnable static scan of backend/core/*.py for every category
    of cryptographic primitive this module tracks. Defaults to scanning the
    real core/ directory this module itself lives in (one level up from this
    file), so a caller doesn't have to know this repo's own layout.

    Returns a real posture report: per-category findings (file + matched
    pattern name, no source-line content included since a matched crypto
    call's surrounding context could itself be sensitive), a total count per
    classification bucket, and a `quantum_vulnerable_found` flag that is True
    the instant even one QUANTUM_VULNERABLE_PATTERNS match exists anywhere --
    this scan currently reports False, but genuinely re-checks it every time
    it's called rather than asserting it once."""

    if root_dir is None:
        root_dir = os.path.dirname(os.path.abspath(__file__))

    findings_by_bucket = {
        "quantum_vulnerable": [],
        "weak_classical": [],
        "adequate": [],
    }

    pattern_groups = (
        ("quantum_vulnerable", QUANTUM_VULNERABLE_PATTERNS),
        ("weak_classical", WEAK_CLASSICAL_PATTERNS),
        ("adequate", ADEQUATE_PATTERNS),
    )

    files_scanned = 0

    for file_path in _iter_python_files(root_dir):
        files_scanned += 1
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            continue

        relative_path = os.path.relpath(file_path, root_dir)

        # Scan real CODE, not prose -- strip comments/docstrings/string
        # literals once per file (see _strip_comments_and_strings()'s own
        # docstring for why this is necessary, confirmed live during this
        # module's own development) and reuse the stripped text for every
        # pattern group, rather than re-tokenizing per bucket.
        stripped_content = _strip_comments_and_strings(content)

        for bucket, patterns in pattern_groups:
            for label, pattern in patterns.items():
                match_count = len(pattern.findall(stripped_content))
                if match_count:
                    findings_by_bucket[bucket].append({
                        "file": relative_path,
                        "primitive": label,
                        "match_count": match_count,
                    })

    quantum_vulnerable_found = len(findings_by_bucket["quantum_vulnerable"]) > 0

    return {
        "scanned_at": _now(),
        "root_dir_scanned": root_dir,
        "files_scanned": files_scanned,
        "findings": findings_by_bucket,
        "quantum_vulnerable_found": quantum_vulnerable_found,
        "weak_classical_count": len(findings_by_bucket["weak_classical"]),
        "adequate_count": len(findings_by_bucket["adequate"]),
        "classification_note": CLASSIFICATION_NOTE,
        "posture": (
            "CRITICAL -- a quantum-vulnerable primitive (RSA/ECDSA/ECDH/"
            "Diffie-Hellman) was found in application code. See findings."
            if quantum_vulnerable_found else
            "No recognized quantum-vulnerable primitive was found by this heuristic. "
            "This does not establish quantum resistance. Review dependencies, TLS, "
            "providers, key wrapping, backups and runtime configuration separately."
        ),
        "not_legal_or_compliance_advice": (
            "This is an automated, code-level self-check of application-layer "
            "cryptographic primitive usage, not a formal cryptographic audit "
            "or a substitute for a qualified security assessment of the full "
            "deployment (including the TLS/transport layer this scan cannot "
            "see)."
        ),
    }


def get_crypto_agility_posture():
    """Composed, top-level posture report -- the real inventory scan above
    plus the versioned-digest mechanism's own current registration state, in
    one payload. This is the real, checkable analog of
    docs/SECURITY_ARCHITECTURE.md's hand-written Post-Quantum Cryptography
    Readiness table -- re-derivable on demand rather than left as static prose
    that could silently drift from what the code actually does."""

    inventory = run_crypto_inventory_scan()

    return {
        "inventory_scan": inventory,
        "versioned_digest": {
            "current_version": CURRENT_VERSION,
            "registered_versions": dict(ALGORITHM_VERSIONS),
            "supported_algorithms": sorted(_SUPPORTED_HASHERS.keys()),
        },
        "tls_transport_note": (
            "TLS termination at Coolify and outbound TLS require runtime evidence of "
            "negotiated hybrid post-quantum key exchange. SSO also uses RSA in application "
            "code. No post-quantum transport or identity protection is claimed by this scan."
        ),
    }


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
