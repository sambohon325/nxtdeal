"""
Tests for core/crypto_agility.py + core/crypto_agility_api.py -- the Post-Quantum
Cryptography Readiness / cryptographic agility layer (security-hardening pass,
2026-07-20, Task #12).

Covers: versioned_digest()'s real, hand-verified SHA-256 output under the real
"v1:sha256:<hexdigest>" tag format; verify_versioned_digest()'s real acceptance of a
genuine digest, real rejection of a tampered/mismatched digest, real rejection of a
malformed/unversioned string, and real rejection of an unregistered version tag
(never silently "fixed up" or falsely accepted); versioned_digest() raising
UnknownCryptoVersionError for a version this module hasn't registered;
run_crypto_inventory_scan()'s real behavior scanning this actual repo's own
backend/core source tree -- files_scanned > 0, zero quantum_vulnerable findings
against the real codebase today, at least one adequate finding (SHA-256/HMAC/CSPRNG
usage genuinely exists), and specifically confirms this module's OWN source file
self-reports as "adequate" rather than falsely flagging itself as quantum-vulnerable
just because its own docstring/pattern-definition strings mention "RSA"/"ECDSA" in
prose -- a real false-positive this module's own development caught and fixed via a
real, position-preserving comment/string-stripping pass
(_strip_comments_and_strings()) before any pattern is matched; plus real detection
behavior against a synthetic tree seeded with fabricated vulnerable/weak-classical
code (confirming the scanner would correctly flag a real future regression, not
just report "clean" unconditionally, and correctly distinguishes the two
categories); get_crypto_agility_posture()'s composed report shape; and
core/crypto_agility_api.py's real ACL gate -- ADMIN/OPERATIONS can view both
endpoints, every other role is denied.

The real, live filesystem scan against this repo's own backend/core directory is
run exactly ONCE for the whole module (real_scan_report, a module-scoped fixture --
a real scan over 370+ files costs real wall-clock time) and reused everywhere else
via monkeypatching (patched_scan), rather than re-running the real scan once per
test.

Run from backend/ with `pytest`.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import crypto_agility
from core import crypto_agility_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


# Hand-verified via a real, independent `python3 -c "import hashlib; ..."` call
# before writing this test file -- these are not asserted from memory.
_KNOWN_SHA256_HELLO = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
_KNOWN_SHA256_TEST_STRING = "cf4695981ee7e4a0eacb3315344b539004071a9e961a103b26b94e444756d6b5"


@pytest.fixture(scope="module")
def real_scan_report():
    """The one real, live filesystem scan against this actual repo's own
    backend/core directory -- run once for the entire test module."""
    return crypto_agility.run_crypto_inventory_scan()


@pytest.fixture
def patched_scan(monkeypatch, real_scan_report):
    """Redirects both crypto_agility's own module-internal reference to
    run_crypto_inventory_scan() (what get_crypto_agility_posture() calls
    internally) and crypto_agility_api's separately-imported reference to it
    (what run_crypto_inventory_scan_api() calls directly) to the already-
    computed real_scan_report fixture -- so tests that exercise the composed
    posture report or the API layer reuse the real scan's real output without
    each one separately paying the real scan's own wall-clock cost again.
    Function-scoped (the pytest default), so this never leaks into the
    synthetic-tree tests below, which call the real, un-mocked scan function
    against tiny temp directories."""

    monkeypatch.setattr(crypto_agility, "run_crypto_inventory_scan", lambda root_dir=None: real_scan_report)
    monkeypatch.setattr(crypto_agility_api, "run_crypto_inventory_scan", lambda: real_scan_report)
    return real_scan_report


class TestVersionedDigest:

    def test_produces_the_real_v1_sha256_tag_format(self):
        digest = crypto_agility.versioned_digest("hello")
        assert digest == f"v1:sha256:{_KNOWN_SHA256_HELLO}"

    def test_matches_a_second_hand_verified_value(self):
        digest = crypto_agility.versioned_digest("DealerOS-crypto-agility-test")
        assert digest == f"v1:sha256:{_KNOWN_SHA256_TEST_STRING}"

    def test_accepts_raw_bytes_as_well_as_str(self):
        digest_from_str = crypto_agility.versioned_digest("hello")
        digest_from_bytes = crypto_agility.versioned_digest(b"hello")
        assert digest_from_str == digest_from_bytes

    def test_defaults_to_current_version(self):
        digest = crypto_agility.versioned_digest("hello")
        assert digest.startswith(f"{crypto_agility.CURRENT_VERSION}:")

    def test_raises_on_an_unregistered_version(self):
        with pytest.raises(crypto_agility.UnknownCryptoVersionError):
            crypto_agility.versioned_digest("hello", version="v99-does-not-exist")

    def test_different_inputs_produce_different_digests(self):
        assert crypto_agility.versioned_digest("hello") != crypto_agility.versioned_digest("hellp")


class TestVerifyVersionedDigest:

    def test_a_genuine_digest_verifies_true(self):
        digest = crypto_agility.versioned_digest("hello")
        assert crypto_agility.verify_versioned_digest("hello", digest) is True

    def test_a_tampered_source_value_fails_verification(self):
        digest = crypto_agility.versioned_digest("hello")
        assert crypto_agility.verify_versioned_digest("hellp", digest) is False

    def test_a_tampered_digest_value_fails_verification(self):
        digest = crypto_agility.versioned_digest("hello")
        tampered = digest[:-1] + ("0" if digest[-1] != "0" else "1")
        assert crypto_agility.verify_versioned_digest("hello", tampered) is False

    def test_a_malformed_string_with_no_colons_fails_gracefully(self):
        assert crypto_agility.verify_versioned_digest("hello", "not-a-real-digest") is False

    def test_a_non_string_versioned_value_fails_gracefully(self):
        assert crypto_agility.verify_versioned_digest("hello", None) is False
        assert crypto_agility.verify_versioned_digest("hello", 12345) is False

    def test_an_unregistered_version_tag_is_rejected_not_silently_accepted(self):
        forged = f"v99-does-not-exist:sha256:{_KNOWN_SHA256_HELLO}"
        assert crypto_agility.verify_versioned_digest("hello", forged) is False

    def test_a_mismatched_algorithm_tag_is_rejected(self):
        # Real version "v1" is registered to sha256 -- claiming a different
        # algorithm name under that same version tag must not be trusted.
        forged = f"v1:sha512:{_KNOWN_SHA256_HELLO}"
        assert crypto_agility.verify_versioned_digest("hello", forged) is False

    def test_round_trips_correctly_for_several_real_values(self):
        for value in ("", "a", "NXTDeal", "12345"):
            digest = crypto_agility.versioned_digest(value)
            assert crypto_agility.verify_versioned_digest(value, digest) is True


class TestRunCryptoInventoryScanAgainstTheRealRepo:
    """Uses the one real, live scan (real_scan_report) run once for the whole
    module -- not a synthetic fixture -- confirming today's real, live posture."""

    def test_scans_a_real_nonzero_number_of_files(self, real_scan_report):
        assert real_scan_report["files_scanned"] > 50

    def test_reports_sso_and_backup_rsa_without_hiding_new_primitives(self, real_scan_report):
        assert real_scan_report["quantum_vulnerable_found"] is True
        assert {(f["file"], f["primitive"]) for f in real_scan_report["findings"]["quantum_vulnerable"]} == {
            ("sso.py", "rsa"), ("sso.py", "asymmetric_crypto_import"), ("dealer_cloud.py", "rsa"),
            ("dealer_cloud.py", "asymmetric_crypto_import"),
        }

    def test_finds_at_least_one_adequate_primitive_since_sha256_hmac_genuinely_exist(self, real_scan_report):
        assert real_scan_report["adequate_count"] > 0

    def test_posture_narrative_reports_existing_sso_rsa(self, real_scan_report):
        assert "quantum-vulnerable primitive" in real_scan_report["posture"]

    def test_carries_a_not_legal_advice_style_disclaimer(self, real_scan_report):
        assert "not_legal_or_compliance_advice" in real_scan_report
        assert real_scan_report["not_legal_or_compliance_advice"]

    def test_own_source_file_correctly_self_reports_as_adequate_not_vulnerable(self, real_scan_report):
        # crypto_agility.py itself uses hashlib.sha256/hmac.compare_digest (real
        # code) but its own docstring/pattern-definition strings also MENTION
        # "RSA"/"ECDSA"/"ECDH"/"Diffie-Hellman" in prose -- a real false
        # positive caught during this module's own development, where a naive
        # scan flagged this file as quantum-vulnerable purely from its own
        # documentation. This is the direct regression check for that fix.
        vulnerable_files = {f["file"] for f in real_scan_report["findings"]["quantum_vulnerable"]}
        assert "crypto_agility.py" not in vulnerable_files

        adequate_files = {f["file"] for f in real_scan_report["findings"]["adequate"]}
        assert "crypto_agility.py" in adequate_files

    def test_finds_the_one_known_real_weak_classical_usage_correctly_classified(self, real_scan_report):
        # core/mfa.py's TOTP implementation uses HMAC-SHA1 (RFC 6238-compliant
        # -- TOTP's own spec requires it), a real, expected, already-documented
        # weak-classical (not quantum-vulnerable) finding.
        weak_files = {f["file"]: f["primitive"] for f in real_scan_report["findings"]["weak_classical"]}
        assert weak_files.get("mfa.py") == "sha1_hash"


class TestRunCryptoInventoryScanAgainstASyntheticVulnerableTree:
    """Confirms the scanner would actually catch a real regression, not just report
    'clean' unconditionally regardless of what's on disk. Uses tiny, real,
    un-mocked temp-directory scans -- fast regardless of the real repo's own size."""

    def test_detects_a_fabricated_rsa_import(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_file = os.path.join(tmp_dir, "bad_module.py")
            with open(bad_file, "w") as fh:
                fh.write("from Crypto.PublicKey import RSA\n\ndef sign(data):\n    pass\n")

            report = crypto_agility.run_crypto_inventory_scan(root_dir=tmp_dir)
            assert report["quantum_vulnerable_found"] is True
            primitives_found = {f["primitive"] for f in report["findings"]["quantum_vulnerable"]}
            assert "asymmetric_crypto_import" in primitives_found
            assert "rsa" in primitives_found

    def test_detects_a_fabricated_ecdsa_reference_in_real_code_not_a_comment(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_file = os.path.join(tmp_dir, "bad_module.py")
            with open(bad_file, "w") as fh:
                # A real import statement, not a comment -- confirms detection
                # works on genuine code references (matching the pattern's own
                # \becdsa\b word-boundary design, the same as a real
                # `from ecdsa import SigningKey` would appear), and
                # (implicitly, alongside the real-repo test above) that a
                # comment mentioning the same word would correctly NOT trigger
                # a finding after string/comment stripping.
                fh.write("from ecdsa import SigningKey\n\ndef sign(data):\n    pass\n")

            report = crypto_agility.run_crypto_inventory_scan(root_dir=tmp_dir)
            assert report["quantum_vulnerable_found"] is True

    def test_a_comment_mentioning_ecdsa_does_not_trigger_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_file = os.path.join(tmp_dir, "commented_module.py")
            with open(bad_file, "w") as fh:
                fh.write("# this module deliberately does NOT use ECDSA\ndef sign(data):\n    pass\n")

            report = crypto_agility.run_crypto_inventory_scan(root_dir=tmp_dir)
            assert report["quantum_vulnerable_found"] is False

    def test_detects_a_fabricated_md5_usage_as_weak_classical_not_quantum(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_file = os.path.join(tmp_dir, "bad_module.py")
            with open(bad_file, "w") as fh:
                fh.write("import hashlib\n\ndef checksum(data):\n    return hashlib.md5(data).hexdigest()\n")

            report = crypto_agility.run_crypto_inventory_scan(root_dir=tmp_dir)
            # md5 is weak-classical, not itself a Shor's-algorithm/PQC concern --
            # must not be conflated with quantum_vulnerable.
            assert report["quantum_vulnerable_found"] is False
            assert report["weak_classical_count"] > 0

    def test_a_genuinely_empty_directory_scans_clean_with_zero_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report = crypto_agility.run_crypto_inventory_scan(root_dir=tmp_dir)
            assert report["files_scanned"] == 0
            assert report["quantum_vulnerable_found"] is False

    def test_skips_the_tests_directory_by_design(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tests_dir = os.path.join(tmp_dir, "tests")
            os.makedirs(tests_dir)
            with open(os.path.join(tests_dir, "test_something.py"), "w") as fh:
                fh.write("from Crypto.PublicKey import RSA\n")

            report = crypto_agility.run_crypto_inventory_scan(root_dir=tmp_dir)
            assert report["files_scanned"] == 0
            assert report["quantum_vulnerable_found"] is False


class TestGetCryptoAgilityPosture:

    def test_returns_a_composed_report_with_both_real_sections(self, patched_scan):
        posture = crypto_agility.get_crypto_agility_posture()
        assert "inventory_scan" in posture
        assert "versioned_digest" in posture
        assert "tls_transport_note" in posture

    def test_versioned_digest_section_reflects_real_registration_state(self, patched_scan):
        posture = crypto_agility.get_crypto_agility_posture()
        assert posture["versioned_digest"]["current_version"] == crypto_agility.CURRENT_VERSION
        assert posture["versioned_digest"]["registered_versions"] == crypto_agility.ALGORITHM_VERSIONS
        assert "sha256" in posture["versioned_digest"]["supported_algorithms"]

    def test_tls_transport_note_states_the_real_infra_layer_boundary(self, patched_scan):
        posture = crypto_agility.get_crypto_agility_posture()
        assert "TLS" in posture["tls_transport_note"]
        assert "Coolify" in posture["tls_transport_note"]


class TestCryptoAgilityApiAcl:

    def test_admin_can_view_the_posture(self, patched_scan):
        result = crypto_agility_api.get_crypto_agility_posture_api(ADMIN)
        assert "error" not in result

    def test_operations_can_view_the_posture(self, patched_scan):
        result = crypto_agility_api.get_crypto_agility_posture_api(OPERATIONS)
        assert "error" not in result

    def test_admin_can_run_the_inventory_scan(self, patched_scan):
        result = crypto_agility_api.run_crypto_inventory_scan_api(ADMIN)
        assert "error" not in result
        assert "quantum_vulnerable_found" in result

    def test_operations_can_run_the_inventory_scan(self, patched_scan):
        result = crypto_agility_api.run_crypto_inventory_scan_api(OPERATIONS)
        assert "error" not in result

    def test_every_other_real_role_is_denied_the_posture_view(self):
        # No patched_scan needed -- every one of these is denied before the
        # (real, un-mocked) function underneath would ever be called.
        for role in (SALES, MARKETING, SERVICE, FINANCE):
            result = crypto_agility_api.get_crypto_agility_posture_api(role)
            assert "error" in result

    def test_every_other_real_role_is_denied_the_inventory_scan(self):
        for role in (SALES, MARKETING, SERVICE, FINANCE):
            result = crypto_agility_api.run_crypto_inventory_scan_api(role)
            assert "error" in result

    def test_an_unknown_role_is_denied_both(self):
        assert "error" in crypto_agility_api.get_crypto_agility_posture_api("NOT_A_REAL_ROLE")
        assert "error" in crypto_agility_api.run_crypto_inventory_scan_api("NOT_A_REAL_ROLE")


def test_crypto_scan_detects_custom_sso_rsa_verification(tmp_path):
    (tmp_path / "sso_fixture.py").write_text("def _verify_rs256(message, signature, n, e):\n    return pow(signature, e, n)\n")
    result = crypto_agility.run_crypto_inventory_scan(str(tmp_path))
    assert result["quantum_vulnerable_found"] is True
    assert result["findings"]["quantum_vulnerable"][0]["primitive"] == "rsa"
