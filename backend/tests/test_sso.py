"""OIDC regression tests. Positive signature tests use a generated 2048-bit key.
The legacy small-key signer remains only to construct weak-key rejection cases.
"""

import base64
import hashlib
import json
import math
import os
import random
import sys
import time

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core import auth as auth_module
from core.auth import verify_token, MAX_FAILED_ATTEMPTS

from core import audit as audit_module
from core import sso as sso_module
from core import sso_config as sso_config_module
from core import sso_config_api


# ---------------------------------------------------------------------------
# A small, real, from-scratch RSA keypair generator + RS256 signer --
# TEST-FIXTURE ONLY, see module docstring.
# ---------------------------------------------------------------------------

_SMALL_PRIMES = [
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61,
    67, 71, 73, 79, 83, 89, 97,
]


def _is_probable_prime(n, rounds=12):
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n == p:
            return True
        if n % p == 0:
            return False

    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1

    for _ in range(rounds):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _generate_prime(bits):
    while True:
        candidate = random.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


def _egcd(a, b):
    if b == 0:
        return a, 1, 0
    g, x1, y1 = _egcd(b, a % b)
    return g, y1, x1 - (a // b) * y1


def _modinv(a, m):
    g, x, _ = _egcd(a, m)
    if g != 1:
        raise ValueError("modular inverse does not exist")
    return x % m


def _generate_rsa_keypair(bits=512):
    half = bits // 2
    e = 65537
    while True:
        p = _generate_prime(half)
        q = _generate_prime(bits - half)
        if p == q:
            continue
        n = p * q
        if n.bit_length() < bits - 4:
            continue
        phi = (p - 1) * (q - 1)
        if math.gcd(e, phi) != 1:
            continue
        d = _modinv(e, phi)
        return {"n": n, "e": e, "d": d}


def _b64url(raw_bytes):
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("ascii")


def _int_to_b64url(value):
    byte_len = (value.bit_length() + 7) // 8
    return _b64url(value.to_bytes(byte_len, "big"))


def _sign_rs256(signing_input, private_key):
    """Mirrors core/sso.py's own _verify_rs256() EMSA-PKCS1-v1.5 padding
    exactly, in reverse -- reuses that module's real, hard-coded
    _SHA256_DIGESTINFO_PREFIX constant directly rather than re-deriving it a
    second time, so there is only ever one real copy of that RFC 8017
    constant anywhere in this codebase."""

    n = private_key["n"]
    d = private_key["d"]
    modulus_byte_len = (n.bit_length() + 7) // 8

    digest = hashlib.sha256(signing_input).digest()
    digest_info = sso_module._SHA256_DIGESTINFO_PREFIX + digest

    padding_len = modulus_byte_len - len(digest_info) - 3
    assert padding_len >= 8, "test RSA key too small for SHA-256 PKCS#1v1.5 padding"

    padded = b"\x00\x01" + (b"\xff" * padding_len) + b"\x00" + digest_info
    m_int = int.from_bytes(padded, "big")
    s_int = pow(m_int, d, n)
    return s_int.to_bytes(modulus_byte_len, "big")


def _build_signed_jwt(header, payload, private_key):
    header_seg = _b64url(json.dumps(header).encode("utf-8"))
    payload_seg = _b64url(json.dumps(payload).encode("utf-8"))
    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    signature = _sign_rs256(signing_input, private_key)
    signature_seg = _b64url(signature)
    return f"{header_seg}.{payload_seg}.{signature_seg}"


def _jwks_document(public_n, public_e, kid="test-key-1"):
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "n": _int_to_b64url(public_n),
                "e": _int_to_b64url(public_e),
            }
        ]
    }


@pytest.fixture(scope="session")
def rsa_keypair():
    """Generated once per test session -- the key material itself isn't what
    any test is exercising, only core/sso.py's real verification logic
    against tokens signed with it."""

    from cryptography.hazmat.primitives.asymmetric import rsa
    numbers = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_numbers()
    return {"n": numbers.public_numbers.n, "e": numbers.public_numbers.e, "d": numbers.d}


# ---------------------------------------------------------------------------
# Isolation fixtures -- every one of these matches an established convention
# already used elsewhere in this test suite (test_auth.py's
# fresh_credential_store/no_real_storage_writes, test_network.py's
# fresh_ledger).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture(autouse=True)
def fresh_credential_store():
    auth_module.credential_store.reset()
    yield
    auth_module.credential_store.reset()


@pytest.fixture(autouse=True)
def fresh_audit_log():
    audit_module.audit_log.reset()
    yield
    audit_module.audit_log.reset()


@pytest.fixture(autouse=True)
def reset_sso_module_state():
    """core/sso.py's pending-login registry and JWKS cache are both real,
    in-memory, module-level singletons (matching core/ws_manager.py's
    ConnectionManager precedent) -- reset between tests so one test's pending
    state/cached JWKS can never leak into the next."""

    sso_module.pending_logins.reset()
    sso_module.clear_jwks_cache()
    yield
    sso_module.pending_logins.reset()
    sso_module.clear_jwks_cache()


@pytest.fixture(autouse=True)
def no_real_storage_writes(monkeypatch):
    """core/sso_config.py's _get_or_create()/update_sso_config()/etc. all call
    save_graph(GRAPH_PATH) -- a hardcoded real path -- as a side effect.
    core/sso.py's _record_sso_failure()/complete_sso_login() likewise call
    save_audit_log(AUDIT_PATH). Both are monkeypatched to no-ops here, same
    reasoning as test_auth.py's own no_real_storage_writes fixture: without
    this, running this file writes real-looking data into the actual
    production storage/*.json files."""

    monkeypatch.setattr(sso_config_module, "save_graph", lambda filepath: None)
    monkeypatch.setattr(sso_module, "save_audit_log", lambda filepath: None)


# ---------------------------------------------------------------------------
# Helpers shared across many tests
# ---------------------------------------------------------------------------

FAKE_ISSUER = "https://login.example-idp.test/tenant-abc"
FAKE_CLIENT_ID = "dealeros-test-client-id"
FAKE_CLIENT_SECRET = "dealeros-test-client-secret"
FAKE_AUTHORIZATION_ENDPOINT = FAKE_ISSUER + "/authorize"
FAKE_TOKEN_ENDPOINT = FAKE_ISSUER + "/token"
FAKE_JWKS_URI = FAKE_ISSUER + "/.well-known/jwks.json"
FAKE_REDIRECT_URI = "https://dealer1.dealeros.xyz/sso/callback"


def _enable_real_sso_config():
    sso_config_module.update_sso_config(
        "EMP-00001",
        provider="generic_oidc",
        issuer=FAKE_ISSUER,
        client_id=FAKE_CLIENT_ID,
        client_secret=FAKE_CLIENT_SECRET,
        authorization_endpoint=FAKE_AUTHORIZATION_ENDPOINT,
        token_endpoint=FAKE_TOKEN_ENDPOINT,
        jwks_uri=FAKE_JWKS_URI,
        redirect_uri=FAKE_REDIRECT_URI,
    )
    result = sso_config_module.set_sso_enabled(True, "EMP-00001")
    assert "error" not in result, result
    return sso_config_module.get_sso_config()


def _valid_claims(nonce, email="jane.doe@dealeros.xyz", email_verified=True, exp_delta=600):
    return {
        "iss": FAKE_ISSUER,
        "aud": FAKE_CLIENT_ID,
        "exp": time.time() + exp_delta,
        "iat": time.time(),
        "nonce": nonce,
        "email": email,
        "email_verified": email_verified,
        "sub": "idp-subject-123",
    }


def _sign_claims(claims, keypair, kid="test-key-1", alg="RS256"):
    header = {"alg": alg, "typ": "JWT", "kid": kid}
    return _build_signed_jwt(header, claims, keypair)


def _install_jwks_mock(monkeypatch, keypair, kid="test-key-1", call_counter=None):
    """Monkeypatches core.sso._http_get_json so any GET to FAKE_JWKS_URI
    returns a real JWKS document built from the test keypair's real public
    component. call_counter, if given a list, gets one entry appended per
    invocation -- used by cache/force-refresh tests."""

    jwks = _jwks_document(keypair["n"], keypair["e"], kid=kid)

    def fake_get_json(url, timeout=None):
        if call_counter is not None:
            call_counter.append(url)
        if url == FAKE_JWKS_URI:
            return jwks
        raise AssertionError(f"unexpected GET in test: {url}")

    monkeypatch.setattr(sso_module, "_http_get_json", fake_get_json)


def _install_token_exchange_mock(monkeypatch, id_token):
    def fake_post_form(url, data, timeout=None):
        assert url == FAKE_TOKEN_ENDPOINT
        assert data["grant_type"] == "authorization_code"
        return {"id_token": id_token, "access_token": "fake-access-token", "token_type": "Bearer"}

    monkeypatch.setattr(sso_module, "_http_post_form", fake_post_form)


# ---------------------------------------------------------------------------
# verify_id_token() -- the full checklist
# ---------------------------------------------------------------------------

def test_verify_id_token_accepts_valid_token(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="the-real-nonce")
    id_token = _sign_claims(claims_in, rsa_keypair)

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="the-real-nonce")

    assert error is None
    assert claims_out["email"] == "jane.doe@dealeros.xyz"
    assert claims_out["iss"] == FAKE_ISSUER


def test_verify_id_token_rejects_wrong_alg(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="n1")
    id_token = _sign_claims(claims_in, rsa_keypair, alg="HS256")

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "HS256" in error
    assert "RS256" in error


def test_verify_id_token_rejects_none_alg():
    config = _enable_real_sso_config()

    header_seg = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
    payload_seg = _b64url(json.dumps(_valid_claims(nonce="n1")).encode("utf-8"))
    id_token = f"{header_seg}.{payload_seg}."

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "none" in error


def test_verify_id_token_rejects_wrong_issuer(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="n1")
    claims_in["iss"] = "https://not-the-configured-issuer.test"
    id_token = _sign_claims(claims_in, rsa_keypair)

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "issuer mismatch" in error


def test_verify_id_token_rejects_wrong_audience(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="n1")
    claims_in["aud"] = "some-other-clients-id"
    id_token = _sign_claims(claims_in, rsa_keypair)

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "audience" in error


def test_verify_id_token_accepts_audience_as_list_containing_client_id(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="n1")
    claims_in["aud"] = ["some-other-audience", FAKE_CLIENT_ID]
    claims_in["azp"] = config["client_id"]
    id_token = _sign_claims(claims_in, rsa_keypair)

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert error is None
    assert claims_out is not None


def test_verify_id_token_rejects_expired_token(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="n1", exp_delta=-(sso_module.CLOCK_SKEW_SECONDS + 120))
    id_token = _sign_claims(claims_in, rsa_keypair)

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "expired" in error


def test_verify_id_token_within_clock_skew_still_accepted(monkeypatch, rsa_keypair):
    """A token that expired 30 real seconds ago is still accepted -- inside
    CLOCK_SKEW_SECONDS (60s) -- matching real-world server-clock drift
    tolerance."""

    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="n1", exp_delta=-30)
    id_token = _sign_claims(claims_in, rsa_keypair)

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert error is None
    assert claims_out is not None


def test_verify_id_token_rejects_wrong_nonce(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="the-real-nonce")
    id_token = _sign_claims(claims_in, rsa_keypair)

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="a-different-nonce")

    assert claims_out is None
    assert "nonce" in error


def test_verify_id_token_rejects_explicit_email_verified_false_when_required(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    assert config["require_verified_email"] is True
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="n1", email_verified=False)
    id_token = _sign_claims(claims_in, rsa_keypair)

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "email_verified" in error


def test_verify_id_token_rejects_missing_email_verified_claim_when_required(monkeypatch, rsa_keypair):
    """A required verification claim must be explicitly true."""

    config = _enable_real_sso_config()
    assert config["require_verified_email"] is True
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="n1")
    del claims_in["email_verified"]
    id_token = _sign_claims(claims_in, rsa_keypair)

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "email_verified" in error


def test_verify_id_token_detects_signature_tampering(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="n1")
    id_token = _sign_claims(claims_in, rsa_keypair)

    header_seg, payload_seg, signature_seg = id_token.split(".")
    tampered_signature = ("A" if signature_seg[0] != "A" else "B") + signature_seg[1:]
    tampered_token = f"{header_seg}.{payload_seg}.{tampered_signature}"

    claims_out, error = sso_module.verify_id_token(tampered_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "signature" in error


def test_verify_id_token_detects_payload_tampering_after_signing(monkeypatch, rsa_keypair):
    """Flipping a claim after signing (e.g. an attacker trying to swap the
    email) invalidates the signature, since payload bytes are part of the
    signed signing_input."""

    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)

    claims_in = _valid_claims(nonce="n1", email="victim@dealeros.xyz")
    id_token = _sign_claims(claims_in, rsa_keypair)

    header_seg, payload_seg, signature_seg = id_token.split(".")
    forged_claims = dict(claims_in)
    forged_claims["email"] = "attacker@evil.test"
    forged_payload_seg = _b64url(json.dumps(forged_claims).encode("utf-8"))
    forged_token = f"{header_seg}.{forged_payload_seg}.{signature_seg}"

    claims_out, error = sso_module.verify_id_token(forged_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "signature" in error


def test_verify_id_token_rejects_malformed_jwt():
    config = _enable_real_sso_config()

    claims_out, error = sso_module.verify_id_token("not-a-real-jwt", config, expected_nonce="n1")

    assert claims_out is None
    assert "well-formed" in error


def test_verify_id_token_rejects_when_no_jwks_uri_configured(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    config = dict(config)
    config["jwks_uri"] = None

    claims_in = _valid_claims(nonce="n1")
    id_token = _sign_claims(claims_in, rsa_keypair)

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "jwks_uri" in error


def test_verify_id_token_rejects_unmatched_kid_after_forced_refresh(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    other_keypair = _generate_rsa_keypair(bits=512)
    # JWKS only ever publishes a DIFFERENT key than the one that signed this
    # token -- both the initial fetch and the forced-refresh retry return the
    # same (wrong) key, so this should still fail cleanly rather than crash.
    _install_jwks_mock(monkeypatch, other_keypair, kid="other-key")

    claims_in = _valid_claims(nonce="n1")
    id_token = _sign_claims(claims_in, rsa_keypair, kid="test-key-1")

    claims_out, error = sso_module.verify_id_token(id_token, config, expected_nonce="n1")

    assert claims_out is None
    assert "no matching signing key" in error


# ---------------------------------------------------------------------------
# fetch_jwks() -- caching + forced refresh
# ---------------------------------------------------------------------------

def test_fetch_jwks_caches_between_calls(monkeypatch, rsa_keypair):
    calls = []
    _install_jwks_mock(monkeypatch, rsa_keypair, call_counter=calls)

    keys_1, error_1 = sso_module.fetch_jwks(FAKE_JWKS_URI)
    keys_2, error_2 = sso_module.fetch_jwks(FAKE_JWKS_URI)

    assert error_1 is None and error_2 is None
    assert keys_1 == keys_2
    assert len(calls) == 1


def test_fetch_jwks_force_refresh_bypasses_cache(monkeypatch, rsa_keypair):
    calls = []
    _install_jwks_mock(monkeypatch, rsa_keypair, call_counter=calls)

    sso_module.fetch_jwks(FAKE_JWKS_URI)
    sso_module.fetch_jwks(FAKE_JWKS_URI, force_refresh=True)

    assert len(calls) == 2


def test_fetch_jwks_reports_error_on_malformed_response(monkeypatch):
    def fake_get_json(url, timeout=None):
        return {"not_a_keys_array": True}

    monkeypatch.setattr(sso_module, "_http_get_json", fake_get_json)

    keys, error = sso_module.fetch_jwks(FAKE_JWKS_URI)

    assert keys is None
    assert "keys" in error


def test_find_jwk_matches_by_kid():
    keys = [
        {"kid": "key-a", "kty": "RSA"},
        {"kid": "key-b", "kty": "RSA"},
    ]

    assert sso_module._find_jwk(keys, "key-b") == keys[1]
    assert sso_module._find_jwk(keys, "unknown") is None


def test_find_jwk_falls_back_to_single_key_when_kid_missing():
    keys = [{"kid": "only-key", "kty": "RSA"}]

    assert sso_module._find_jwk(keys, None) == keys[0]


def test_find_jwk_refuses_to_guess_among_multiple_keys_with_no_kid():
    keys = [{"kid": "a"}, {"kid": "b"}]

    assert sso_module._find_jwk(keys, None) is None


# ---------------------------------------------------------------------------
# Direct RSA verification sanity check
# ---------------------------------------------------------------------------

def test_verify_rs256_roundtrip(rsa_keypair):
    signing_input = b"header-segment.payload-segment"
    signature = _sign_rs256(signing_input, rsa_keypair)

    assert sso_module._verify_rs256(signing_input, signature, rsa_keypair["n"], rsa_keypair["e"])

    tampered_signature = bytes([signature[0] ^ 0xFF]) + signature[1:]
    assert not sso_module._verify_rs256(signing_input, tampered_signature, rsa_keypair["n"], rsa_keypair["e"])


# ---------------------------------------------------------------------------
# PendingSsoLoginRegistry -- state/nonce CSRF + replay protection
# ---------------------------------------------------------------------------

def test_pending_login_create_returns_state_and_nonce():
    pending = sso_module.pending_logins.create(FAKE_REDIRECT_URI)

    assert pending.state
    assert pending.nonce
    assert pending.state != pending.nonce
    assert pending.redirect_uri == FAKE_REDIRECT_URI


def test_pending_login_pop_consumes_state_exactly_once():
    pending = sso_module.pending_logins.create(FAKE_REDIRECT_URI)

    first, error_1 = sso_module.pending_logins.pop(pending.state)
    assert error_1 is None
    assert first.state == pending.state

    second, error_2 = sso_module.pending_logins.pop(pending.state)
    assert second is None
    assert "unknown or already-used state" in error_2


def test_pending_login_pop_rejects_unknown_state():
    result, error = sso_module.pending_logins.pop("a-state-that-was-never-created")

    assert result is None
    assert "unknown or already-used state" in error


def test_pending_login_pop_rejects_expired_state():
    pending = sso_module.pending_logins.create(FAKE_REDIRECT_URI)
    # Reach directly into the real stored record and simulate real time
    # having passed, rather than sleeping PENDING_LOGIN_TTL_SECONDS in a
    # test.
    sso_module.pending_logins._pending[pending.state].expires_at = time.time() - 1

    result, error = sso_module.pending_logins.pop(pending.state)

    assert result is None
    assert "expired" in error


# ---------------------------------------------------------------------------
# begin_sso_login()
# ---------------------------------------------------------------------------

def test_begin_sso_login_rejects_when_sso_not_enabled():
    result = sso_module.begin_sso_login()

    assert result == {"error": "SSO is not enabled for this dealer."}


def test_begin_sso_login_returns_real_authorization_url_and_state():
    _enable_real_sso_config()

    result = sso_module.begin_sso_login()

    assert "error" not in result
    assert result["authorization_url"].startswith(FAKE_AUTHORIZATION_ENDPOINT + "?")
    assert f"client_id={FAKE_CLIENT_ID}" in result["authorization_url"]
    assert "response_type=code" in result["authorization_url"]
    assert f"state={result['state']}" in result["authorization_url"]

    # The state actually registered a real pending login that can be popped.
    pending, error = sso_module.pending_logins.pop(result["state"])
    assert error is None
    assert pending.redirect_uri == FAKE_REDIRECT_URI


# ---------------------------------------------------------------------------
# complete_sso_login() -- the full orchestration
# ---------------------------------------------------------------------------

def _begin_and_prepare_valid_login(monkeypatch, rsa_keypair, email="jane.doe@dealeros.xyz"):
    """Shared setup for the happy-path-and-friends tests: enables SSO,
    begins a login (registering a real state+nonce), and wires the network
    mocks to return a real, validly-signed id_token for that exact nonce."""

    _enable_real_sso_config()
    begin_result = sso_module.begin_sso_login()
    state = begin_result["state"]

    pending = sso_module.pending_logins._pending[state]
    claims = _valid_claims(nonce=pending.nonce, email=email)
    id_token = _sign_claims(claims, rsa_keypair)

    _install_jwks_mock(monkeypatch, rsa_keypair)
    _install_token_exchange_mock(monkeypatch, id_token)

    return state


def test_complete_sso_login_happy_path_issues_real_token(monkeypatch, rsa_keypair):
    auth_module.credential_store.set_credential(
        "EMP-00001", "unused-password", "SALES", email="jane.doe@dealeros.xyz",
        must_change_password=False,
    )

    state = _begin_and_prepare_valid_login(monkeypatch, rsa_keypair)

    result = sso_module.complete_sso_login(state, "fake-authorization-code", client_ip="10.0.0.5")

    assert "error" not in result, result
    assert result["employee_id"] == "EMP-00001"
    assert result["role"] == "SALES"
    assert result["sso"] is True
    assert result["sso_provider"] == "generic_oidc"
    assert result["must_change_password"] is False

    payload = verify_token(result["token"])
    assert payload["employee_id"] == "EMP-00001"
    assert payload["role"] == "SALES"

    # A real sso_login_success audit event was recorded.
    success_events = audit_module.audit_log.get_by_type("sso_login_success")
    assert len(success_events) == 1
    assert success_events[0].entity_id == "EMP-00001"


def test_complete_sso_login_rejects_when_sso_disabled():
    result = sso_module.complete_sso_login("some-state", "some-code")

    assert result == {"error": "SSO is not enabled for this dealer."}


def test_complete_sso_login_rejects_unknown_state():
    _enable_real_sso_config()

    result = sso_module.complete_sso_login("a-state-that-was-never-issued", "some-code")

    assert "unknown or already-used state" in result["error"]


def test_complete_sso_login_state_cannot_be_replayed(monkeypatch, rsa_keypair):
    auth_module.credential_store.set_credential(
        "EMP-00001", "unused-password", "SALES", email="jane.doe@dealeros.xyz"
    )

    state = _begin_and_prepare_valid_login(monkeypatch, rsa_keypair)

    first = sso_module.complete_sso_login(state, "fake-code")
    assert "error" not in first

    second = sso_module.complete_sso_login(state, "fake-code")
    assert "unknown or already-used state" in second["error"]


def test_complete_sso_login_rejects_when_token_exchange_fails(monkeypatch):
    import urllib.error

    _enable_real_sso_config()
    begin_result = sso_module.begin_sso_login()

    def fake_post_form(url, data, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(sso_module, "_http_post_form", fake_post_form)

    result = sso_module.complete_sso_login(begin_result["state"], "fake-code")

    assert "SSO login failed" in result["error"]
    failure_events = audit_module.audit_log.get_by_type("sso_login_failed")
    assert len(failure_events) == 1


def test_complete_sso_login_rejects_invalid_signature(monkeypatch, rsa_keypair):
    _enable_real_sso_config()
    begin_result = sso_module.begin_sso_login()
    pending = sso_module.pending_logins._pending[begin_result["state"]]

    claims = _valid_claims(nonce=pending.nonce)
    id_token = _sign_claims(claims, rsa_keypair)
    header_seg, payload_seg, signature_seg = id_token.split(".")
    tampered_token = f"{header_seg}.{payload_seg}." + ("A" if signature_seg[0] != "A" else "B") + signature_seg[1:]

    _install_jwks_mock(monkeypatch, rsa_keypair)
    _install_token_exchange_mock(monkeypatch, tampered_token)

    result = sso_module.complete_sso_login(begin_result["state"], "fake-code")

    assert "SSO login failed" in result["error"]
    assert "signature" in result["error"]


def test_complete_sso_login_rejects_unknown_email_no_jit_provisioning(monkeypatch, rsa_keypair):
    """The real design-decision test -- a verified id_token for an email
    with no matching NXTDeal employee credential is rejected outright, not
    silently auto-provisioned into a new account."""

    state = _begin_and_prepare_valid_login(monkeypatch, rsa_keypair, email="nobody-provisioned@dealeros.xyz")

    result = sso_module.complete_sso_login(state, "fake-code")

    assert "no NXTDeal account exists" in result["error"]
    assert "admin must create your account" in result["error"]

    # No new credential was silently created for this email.
    assert auth_module.credential_store.resolve_identifier("nobody-provisioned@dealeros.xyz") == \
        "nobody-provisioned@dealeros.xyz"


def test_complete_sso_login_enforces_ip_allowlist(monkeypatch, rsa_keypair):
    auth_module.credential_store.set_credential(
        "EMP-00001", "unused-password", "SALES", email="jane.doe@dealeros.xyz"
    )
    auth_module.credential_store.set_ip_allowlist("EMP-00001", ["1.2.3.4"])

    state = _begin_and_prepare_valid_login(monkeypatch, rsa_keypair)

    blocked = sso_module.complete_sso_login(state, "fake-code", client_ip="9.9.9.9")
    assert blocked == {"error": "Login not allowed from this network."}


def test_complete_sso_login_allows_allowlisted_ip(monkeypatch, rsa_keypair):
    auth_module.credential_store.set_credential(
        "EMP-00001", "unused-password", "SALES", email="jane.doe@dealeros.xyz"
    )
    auth_module.credential_store.set_ip_allowlist("EMP-00001", ["1.2.3.4"])

    state = _begin_and_prepare_valid_login(monkeypatch, rsa_keypair)

    result = sso_module.complete_sso_login(state, "fake-code", client_ip="1.2.3.4")
    assert "error" not in result


def test_complete_sso_login_enforces_account_lockout(monkeypatch, rsa_keypair):
    auth_module.credential_store.set_credential(
        "EMP-00001", "unused-password", "SALES", email="jane.doe@dealeros.xyz"
    )
    for _ in range(MAX_FAILED_ATTEMPTS):
        auth_module.credential_store.record_failed_login("EMP-00001")
    assert auth_module.credential_store.get_lockout_status("EMP-00001")["locked"] is True

    state = _begin_and_prepare_valid_login(monkeypatch, rsa_keypair)

    result = sso_module.complete_sso_login(state, "fake-code")

    assert "locked" in result["error"]


def test_complete_sso_login_verification_failure_does_not_increment_lockout_counter(monkeypatch, rsa_keypair):
    """The other real design-decision test -- a bad/expired authorization
    code or a signature mismatch must NOT increment the same
    record_failed_login() counter a wrong password would, per core/sso.py's
    own documented reasoning (a technical/config failure isn't evidence of
    password-guessing)."""

    auth_module.credential_store.set_credential(
        "EMP-00001", "unused-password", "SALES", email="jane.doe@dealeros.xyz"
    )
    before = auth_module.credential_store.get_lockout_status("EMP-00001")["failed_attempts"]
    assert before == 0

    _enable_real_sso_config()
    begin_result = sso_module.begin_sso_login()
    pending = sso_module.pending_logins._pending[begin_result["state"]]

    # A verified-but-wrong-nonce token, forcing verify_id_token() to fail
    # AFTER the employee's email would otherwise have been resolvable --
    # the strongest version of this test, since it proves the counter isn't
    # touched even when the flow gets as far as knowing which real employee
    # this login attempt was for.
    claims = _valid_claims(nonce="a-nonce-that-does-not-match-the-pending-login")
    id_token = _sign_claims(claims, rsa_keypair)
    _install_jwks_mock(monkeypatch, rsa_keypair)
    _install_token_exchange_mock(monkeypatch, id_token)

    result = sso_module.complete_sso_login(begin_result["state"], "fake-code")
    assert "error" in result

    after = auth_module.credential_store.get_lockout_status("EMP-00001")["failed_attempts"]
    assert after == 0


def test_complete_sso_login_rejects_when_no_email_claim(monkeypatch, rsa_keypair):
    _enable_real_sso_config()
    begin_result = sso_module.begin_sso_login()
    pending = sso_module.pending_logins._pending[begin_result["state"]]

    claims = _valid_claims(nonce=pending.nonce)
    del claims["email"]
    id_token = _sign_claims(claims, rsa_keypair)

    _install_jwks_mock(monkeypatch, rsa_keypair)
    _install_token_exchange_mock(monkeypatch, id_token)

    result = sso_module.complete_sso_login(begin_result["state"], "fake-code")

    assert "did not return an email address" in result["error"]


def test_complete_sso_login_resolves_email_case_insensitively(monkeypatch, rsa_keypair):
    auth_module.credential_store.set_credential(
        "EMP-00001", "unused-password", "SALES", email="Jane.Doe@Dealeros.xyz"
    )

    state = _begin_and_prepare_valid_login(monkeypatch, rsa_keypair, email="jane.doe@dealeros.xyz")

    result = sso_module.complete_sso_login(state, "fake-code")

    assert result["employee_id"] == "EMP-00001"


def test_complete_sso_login_reports_must_change_password(monkeypatch, rsa_keypair):
    auth_module.credential_store.set_credential(
        "EMP-00001", "temp-pw", "SALES", email="jane.doe@dealeros.xyz", must_change_password=True
    )

    state = _begin_and_prepare_valid_login(monkeypatch, rsa_keypair)

    result = sso_module.complete_sso_login(state, "fake-code")

    assert result["must_change_password"] is True


def test_complete_sso_login_allowed_dashboards_matches_role():
    """A cheap, direct check on _allowed_dashboards() itself (the private
    helper complete_sso_login() calls) rather than re-running the whole
    flow -- ADMIN should see every dashboard key, matching
    core/auth_api.py's own equivalent behavior. However, 'audit' and
    'success_center' require system_admin_context (set only by the
    AdministrationBoundary middleware for verified system admins), which
    SSO login does not activate -- so they are correctly excluded from
    the SSO login's allowed_dashboards."""

    from core.permissions import DASHBOARD_ACCESS, ADMIN

    allowed = sso_module._allowed_dashboards(ADMIN)
    assert set(allowed) == set(DASHBOARD_ACCESS.keys()) - {"audit", "success_center"}


# ---------------------------------------------------------------------------
# exchange_code_for_tokens() / build_authorization_url()
# ---------------------------------------------------------------------------

def test_build_authorization_url_includes_required_params():
    config = _enable_real_sso_config()
    pending = sso_module.pending_logins.create(FAKE_REDIRECT_URI)

    url = sso_module.build_authorization_url(config, pending)

    assert url.startswith(FAKE_AUTHORIZATION_ENDPOINT + "?")
    assert f"state={pending.state}" in url
    assert f"nonce={pending.nonce}" in url
    assert "response_type=code" in url
    assert f"client_id={FAKE_CLIENT_ID}" in url
    assert "scope=openid" in url


def test_exchange_code_for_tokens_rejects_response_without_id_token(monkeypatch):
    config = _enable_real_sso_config()

    def fake_post_form(url, data, timeout=None):
        return {"access_token": "no-id-token-here"}

    monkeypatch.setattr(sso_module, "_http_post_form", fake_post_form)

    response, error = sso_module.exchange_code_for_tokens(config, "some-code", FAKE_REDIRECT_URI)

    assert response is None
    assert "did not contain an id_token" in error


def test_exchange_code_for_tokens_surfaces_http_error(monkeypatch):
    import urllib.error
    import io

    config = _enable_real_sso_config()

    def fake_post_form(url, data, timeout=None):
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(b'{"error":"invalid_grant"}'))

    monkeypatch.setattr(sso_module, "_http_post_form", fake_post_form)

    response, error = sso_module.exchange_code_for_tokens(config, "some-code", FAKE_REDIRECT_URI)

    assert response is None
    assert "HTTP 400" in error
    assert "invalid_grant" in error


# ---------------------------------------------------------------------------
# core/sso_config.py -- validation + the singleton pattern
# ---------------------------------------------------------------------------

def test_is_sso_enabled_false_by_default():
    assert sso_config_module.is_sso_enabled() is False


def test_get_sso_config_creates_singleton_with_real_defaults():
    config = sso_config_module.get_sso_config()

    assert config["id"] == "SSOCFG-00001"
    assert config["enabled"] is False
    assert config["scopes"] == ["openid", "email", "profile"]
    assert config["require_verified_email"] is True

    # Calling it again returns the SAME entity, not a second one.
    config_2 = sso_config_module.get_sso_config()
    assert config_2["id"] == config["id"]


def test_update_sso_config_rejects_invalid_provider():
    result = sso_config_module.update_sso_config("EMP-00001", provider="not_a_real_provider")

    assert "error" in result
    assert "provider" in result["error"]


def test_update_sso_config_rejects_scopes_not_a_list_of_strings():
    result = sso_config_module.update_sso_config("EMP-00001", scopes="openid email")

    assert "error" in result
    assert "list of strings" in result["error"]


def test_update_sso_config_rejects_scopes_missing_openid():
    result = sso_config_module.update_sso_config("EMP-00001", scopes=["email", "profile"])

    assert "error" in result
    assert "openid" in result["error"]


def test_update_sso_config_accepts_valid_fields_and_stamps_updated_by():
    result = sso_config_module.update_sso_config(
        "EMP-00001",
        provider="okta",
        issuer=FAKE_ISSUER,
        client_id=FAKE_CLIENT_ID,
    )

    assert "error" not in result
    assert result["provider"] == "okta"
    assert result["issuer"] == FAKE_ISSUER
    assert result["client_id"] == FAKE_CLIENT_ID
    assert result["updated_by"] == "EMP-00001"


def test_set_sso_enabled_refuses_without_required_fields():
    result = sso_config_module.set_sso_enabled(True, "EMP-00001")

    assert "error" in result
    assert "Cannot enable SSO" in result["error"]
    assert sso_config_module.is_sso_enabled() is False


def test_set_sso_enabled_succeeds_once_required_fields_present():
    config = _enable_real_sso_config()

    assert config["enabled"] is True
    assert sso_config_module.is_sso_enabled() is True


def test_set_sso_enabled_can_be_turned_back_off():
    _enable_real_sso_config()
    assert sso_config_module.is_sso_enabled() is True

    result = sso_config_module.set_sso_enabled(False, "EMP-00001")

    assert result["enabled"] is False
    assert sso_config_module.is_sso_enabled() is False


def test_discover_oidc_configuration_rejects_empty_issuer():
    result = sso_config_module.discover_oidc_configuration("")

    assert "error" in result
    assert "issuer is required" in result["error"]


def test_discover_oidc_configuration_rejects_non_url_issuer():
    result = sso_config_module.discover_oidc_configuration("not-a-url-at-all")

    assert "error" in result
    assert "full URL" in result["error"]


# ---------------------------------------------------------------------------
# core/sso_config_api.py -- ADMIN-only ACL layer
# ---------------------------------------------------------------------------

def test_get_sso_login_options_api_is_unauthenticated_and_minimal():
    """The one deliberate public exception -- no role argument at all, and
    never leaks client_id/client_secret even once SSO is configured."""

    result_disabled = sso_config_api.get_sso_login_options_api()
    assert result_disabled == {"enabled": False, "provider": None}

    _enable_real_sso_config()

    result_enabled = sso_config_api.get_sso_login_options_api()
    assert result_enabled == {"enabled": True, "provider": "generic_oidc"}
    assert "client_id" not in result_enabled
    assert "client_secret" not in result_enabled


def test_get_sso_config_api_requires_admin_role():
    from core.permissions import ADMIN, SALES

    non_admin = sso_config_api.get_sso_config_api(SALES)
    assert non_admin == {"error": "Admin role required."}

    admin = sso_config_api.get_sso_config_api(ADMIN)
    assert "error" not in admin
    assert admin["id"] == "SSOCFG-00001"


def test_update_sso_config_api_requires_admin_role():
    from core.permissions import SALES

    result = sso_config_api.update_sso_config_api(SALES, "EMP-00002", provider="okta")

    assert result == {"error": "Admin role required."}


def test_set_sso_enabled_api_requires_admin_role():
    from core.permissions import SALES

    result = sso_config_api.set_sso_enabled_api(SALES, "EMP-00002", True)

    assert result == {"error": "Admin role required."}


def test_discover_oidc_configuration_api_requires_admin_role():
    from core.permissions import SALES

    result = sso_config_api.discover_oidc_configuration_api(SALES, "EMP-00002", FAKE_ISSUER)

    assert result == {"error": "Admin role required."}


@pytest.mark.parametrize("claim", [None, False, "true", "false", 1, 0])
def test_verified_email_requires_boolean_true(monkeypatch, rsa_keypair, claim):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)
    claims = _valid_claims("n1", email_verified=claim)
    result, error = sso_module.verify_id_token(_sign_claims(claims, rsa_keypair), config, "n1")
    assert result is None and "email_verified" in error


@pytest.mark.parametrize("expiry", [float("nan"), float("inf"), True])
def test_nonfinite_expiry_rejected(monkeypatch, rsa_keypair, expiry):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)
    claims = _valid_claims("n1")
    claims["exp"] = expiry
    assert sso_module.verify_id_token(_sign_claims(claims, rsa_keypair), config, "n1")[0] is None


def test_weak_rsa_key_rejected():
    key = _generate_rsa_keypair(bits=512)
    message = b"header.payload"
    assert not sso_module._verify_rs256(message, _sign_rs256(message, key), key["n"], key["e"])


def test_multiple_audiences_need_authorized_party(monkeypatch, rsa_keypair):
    config = _enable_real_sso_config()
    _install_jwks_mock(monkeypatch, rsa_keypair)
    claims = _valid_claims("n1")
    claims["aud"] = [config["client_id"], "another-client"]
    assert sso_module.verify_id_token(_sign_claims(claims, rsa_keypair), config, "n1")[0] is None


def test_discovery_rejects_issuer_mismatch(monkeypatch):
    from core import outbound_http
    monkeypatch.setattr(outbound_http, "public_https_json", lambda *a, **k: {
        "issuer": "https://wrong.example", "authorization_endpoint": "https://id.example/authorize",
        "token_endpoint": "https://id.example/token", "jwks_uri": "https://id.example/keys"})
    result = sso_config_module.discover_oidc_configuration("https://id.example")
    assert "error" in result and "issuer" in result["error"]


def test_discovery_rejects_plaintext_transport():
    assert "error" in sso_config_module.discover_oidc_configuration("http://id.example")


def test_sso_cannot_bypass_enrolled_local_mfa(monkeypatch, rsa_keypair):
    from core import auth_api, mfa
    store = auth_module.credential_store
    store.set_credential("EMP-00001", "unused-password", "ADMIN",
                         email="jane.doe@dealeros.xyz", must_change_password=False)
    secret = store.begin_mfa_enrollment("EMP-00001")["secret"]
    assert store.confirm_mfa_enrollment("EMP-00001", mfa.totp_now(secret))["success"]
    monkeypatch.setattr(auth_api, "credential_store", store)
    monkeypatch.setattr(auth_api, "save_credentials", lambda *_: None)
    monkeypatch.setattr(auth_api, "save_audit_log", lambda *_: None)
    state = _begin_and_prepare_valid_login(monkeypatch, rsa_keypair)
    result = sso_module.complete_sso_login(state, "synthetic-code")
    assert result["mfa_required"] is True and "token" not in result
    challenge = result["mfa_challenge_token"]
    assert auth_module.is_mfa_challenge_token(verify_token(challenge))
    assert not audit_module.audit_log.get_by_type("sso_login_success")
    assert "error" in auth_api.verify_mfa_login(challenge, "invalid-code")
    completed = auth_api.verify_mfa_login(challenge, mfa.totp_now(secret))
    assert "error" not in completed
    payload = verify_token(completed["token"])
    assert payload["employee_id"] == "EMP-00001"
    assert not auth_module.is_mfa_challenge_token(payload)
    assert payload.get("mfa_authenticated") is True
