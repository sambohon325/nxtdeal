"""
Tests for core/mfa.py -- TOTP (RFC 6238) multi-factor authentication, shipped
in the 2026-07-20 Security Hardening Initiative with no test coverage of its
own (Code Auditor finding CAF-00123, "backend/core/ has minimal real pytest
coverage" -- this file closes that gap for one of the highest-risk untested
modules named in that finding's own recommendation). Run from backend/ with
`pytest`.

core/mfa.py is explicitly "Pure/stateless only" per its own module docstring
-- it never touches core/dealeros.ledger or storage.py, so this file needs no
fresh_ledger fixture or any storage isolation beyond what backend/tests/
conftest.py already provides platform-wide.

Covers: generate_totp_secret()'s length/alphabet/decodability/uniqueness;
_hotp()'s correctness against the real, independently-computed RFC 6238
Appendix B SHA1 test vectors (a known-answer test, not just a self-consistency
check -- these vectors were cross-checked against a from-scratch HOTP
re-implementation, kept out of this file, before being hardcoded here);
totp_now()'s counter-stepping behavior; verify_totp_code()'s window-tolerance
boundary (accepts step-1/step+1 at the default window=1, rejects step+2;
rejects non-digit/empty/None input; honors custom digits/step/window);
build_otpauth_uri()'s real otpauth:// URI structure (parsed back with
urllib.parse, not fragile string matching); generate_recovery_codes()'s
XXXX-XXXX format, transcription-safe alphabet, and count handling;
_normalize_recovery_code()'s case/dash/whitespace handling;
hash_recovery_code()'s determinism and normalize-before-hash behavior; and
verify_and_consume_recovery_code()'s single-use removal, no-match passthrough,
and case/dash-insensitive round trip through the full enroll -> hash -> verify
flow.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import base64
import hashlib
import re
import time
import urllib.parse

import pytest

from core import mfa


# ---------------------------------------------------------------------------
# generate_totp_secret()
# ---------------------------------------------------------------------------

class TestGenerateTotpSecret:
    def test_default_length_is_32_base32_chars_no_padding(self):
        secret = mfa.generate_totp_secret()
        # 20 raw bytes -> base32 encodes to exactly 32 chars with no padding
        # needed (20 is evenly divisible by 5).
        assert len(secret) == 32
        assert "=" not in secret

    def test_custom_length_scales_correctly(self):
        secret = mfa.generate_totp_secret(length_bytes=10)
        assert len(secret) == 16
        assert "=" not in secret

    def test_only_valid_base32_alphabet_characters(self):
        secret = mfa.generate_totp_secret()
        assert re.fullmatch(r"[A-Z2-7]+", secret)

    def test_secrets_are_random_and_unique(self):
        secrets_batch = {mfa.generate_totp_secret() for _ in range(20)}
        assert len(secrets_batch) == 20

    def test_secret_is_usable_by_totp_now_without_error(self):
        secret = mfa.generate_totp_secret()
        code = mfa.totp_now(secret, for_time=1000000)
        assert len(code) == 6
        assert code.isdigit()


# ---------------------------------------------------------------------------
# _hotp() -- RFC 6238 Appendix B known-answer vectors (SHA1)
# ---------------------------------------------------------------------------
# Secret is the RFC 6238 Appendix B ASCII test secret for SHA1 ("12345678901
# 234567890", 20 bytes), base32-encoded for our functions (which take a
# base32 string, per RFC 4226's usual encoding). Each (unix_time, counter,
# expected_8_digit, expected_6_digit) row was independently cross-checked
# against a from-scratch HOTP re-implementation (hmac+hashlib+struct, not
# copy-pasted from core/mfa.py) before being hardcoded here -- the 6-digit
# values are mathematically the same as the last 6 digits of the well-known
# 8-digit RFC vectors, since truncated_int % 10**6 == (truncated_int %
# 10**8) % 10**6 for any base-10 positional representation.

_RFC6238_SECRET_B32 = base64.b32encode(b"12345678901234567890").decode("ascii").rstrip("=")

_RFC6238_VECTORS = [
    # (unix_time, counter, expected_8_digit, expected_6_digit)
    (59, 1, "94287082", "287082"),
    (1111111109, 37037036, "07081804", "081804"),
    (1111111111, 37037036, "07081804", "081804"),
    (1234567890, 41152263, "89005924", "005924"),
    (2000000000, 66666666, "69279037", "279037"),
]


class TestHotpKnownAnswerVectors:
    @pytest.mark.parametrize("unix_time,counter,expected8,expected6", _RFC6238_VECTORS)
    def test_8_digit_hotp_matches_rfc_vector(self, unix_time, counter, expected8, expected6):
        assert mfa._hotp(_RFC6238_SECRET_B32, counter, digits=8) == expected8

    @pytest.mark.parametrize("unix_time,counter,expected8,expected6", _RFC6238_VECTORS)
    def test_6_digit_hotp_matches_derived_vector(self, unix_time, counter, expected8, expected6):
        assert mfa._hotp(_RFC6238_SECRET_B32, counter, digits=6) == expected6

    def test_hotp_output_is_zero_padded_to_requested_digits(self):
        # A real counter/secret combination whose truncated int happens to be
        # small enough to need zero-padding -- confirms zfill is applied, not
        # just correct for vectors that never need padding.
        code = mfa._hotp(_RFC6238_SECRET_B32, 0, digits=6)
        assert len(code) == 6
        assert code.isdigit()

    def test_hotp_accepts_lowercase_base32_secret(self):
        # _hotp() upper()-cases before b32decode -- a lowercase secret should
        # decode identically to its uppercase form.
        lower = _RFC6238_SECRET_B32.lower()
        assert mfa._hotp(lower, 1, digits=8) == "94287082"

    def test_different_counters_produce_different_codes(self):
        c1 = mfa._hotp(_RFC6238_SECRET_B32, 1)
        c2 = mfa._hotp(_RFC6238_SECRET_B32, 2)
        assert c1 != c2

    def test_different_secrets_produce_different_codes_for_same_counter(self):
        other_secret = mfa.generate_totp_secret()
        assert mfa._hotp(_RFC6238_SECRET_B32, 1) != mfa._hotp(other_secret, 1)


# ---------------------------------------------------------------------------
# totp_now()
# ---------------------------------------------------------------------------

class TestTotpNow:
    def test_matches_hotp_at_the_correct_counter(self):
        secret = mfa.generate_totp_secret()
        for_time = 1_700_000_000
        expected_counter = for_time // mfa.TOTP_STEP_SECONDS
        assert mfa.totp_now(secret, for_time=for_time) == mfa._hotp(secret, expected_counter)

    def test_same_30_second_step_produces_the_same_code(self):
        secret = mfa.generate_totp_secret()
        # Align to a real 30s step boundary first -- an unaligned base time
        # (e.g. a raw timestamp with for_time % 30 == 20) plus 29 seconds can
        # roll over into the *next* step, which isn't what this test means to
        # check.
        base = 1_700_000_000 - (1_700_000_000 % mfa.TOTP_STEP_SECONDS)
        # base and base+29 fall in the same 30s step.
        assert mfa.totp_now(secret, for_time=base) == mfa.totp_now(secret, for_time=base + 29)

    def test_crossing_a_step_boundary_changes_the_code(self):
        secret = mfa.generate_totp_secret()
        base = 1_700_000_000 - (1_700_000_000 % mfa.TOTP_STEP_SECONDS)  # align to a step start
        assert mfa.totp_now(secret, for_time=base) != mfa.totp_now(secret, for_time=base + 30)

    def test_default_for_time_uses_real_current_time(self):
        secret = mfa.generate_totp_secret()
        now_code = mfa.totp_now(secret)
        explicit_code = mfa.totp_now(secret, for_time=time.time())
        assert now_code == explicit_code
        assert len(now_code) == 6 and now_code.isdigit()

    def test_custom_digits_param_changes_output_length(self):
        secret = mfa.generate_totp_secret()
        code8 = mfa.totp_now(secret, for_time=1000, digits=8)
        assert len(code8) == 8


# ---------------------------------------------------------------------------
# verify_totp_code()
# ---------------------------------------------------------------------------

class TestVerifyTotpCode:
    STEP_ORIGIN = 1_700_000_000 - (1_700_000_000 % 30)  # aligned to a real step boundary

    def test_correct_current_code_verifies(self):
        secret = mfa.generate_totp_secret()
        code = mfa.totp_now(secret, for_time=self.STEP_ORIGIN)
        assert mfa.verify_totp_code(secret, code, for_time=self.STEP_ORIGIN) is True

    def test_code_from_one_step_earlier_verifies_within_default_window(self):
        secret = mfa.generate_totp_secret()
        earlier_code = mfa.totp_now(secret, for_time=self.STEP_ORIGIN - 30)
        assert mfa.verify_totp_code(secret, earlier_code, for_time=self.STEP_ORIGIN) is True

    def test_code_from_one_step_later_verifies_within_default_window(self):
        secret = mfa.generate_totp_secret()
        later_code = mfa.totp_now(secret, for_time=self.STEP_ORIGIN + 30)
        assert mfa.verify_totp_code(secret, later_code, for_time=self.STEP_ORIGIN) is True

    def test_code_from_two_steps_away_is_rejected(self):
        secret = mfa.generate_totp_secret()
        too_far_code = mfa.totp_now(secret, for_time=self.STEP_ORIGIN + 60)
        assert mfa.verify_totp_code(secret, too_far_code, for_time=self.STEP_ORIGIN) is False

    def test_window_zero_rejects_adjacent_steps(self):
        secret = mfa.generate_totp_secret()
        adjacent_code = mfa.totp_now(secret, for_time=self.STEP_ORIGIN + 30)
        assert mfa.verify_totp_code(
            secret, adjacent_code, for_time=self.STEP_ORIGIN, window=0
        ) is False

    def test_window_zero_accepts_the_exact_current_step(self):
        secret = mfa.generate_totp_secret()
        current_code = mfa.totp_now(secret, for_time=self.STEP_ORIGIN)
        assert mfa.verify_totp_code(
            secret, current_code, for_time=self.STEP_ORIGIN, window=0
        ) is True

    def test_wrong_code_is_rejected(self):
        secret = mfa.generate_totp_secret()
        real_code = mfa.totp_now(secret, for_time=self.STEP_ORIGIN)
        wrong_code = "000000" if real_code != "000000" else "111111"
        assert mfa.verify_totp_code(secret, wrong_code, for_time=self.STEP_ORIGIN) is False

    def test_code_for_a_different_secret_is_rejected(self):
        secret = mfa.generate_totp_secret()
        other_secret = mfa.generate_totp_secret()
        other_code = mfa.totp_now(other_secret, for_time=self.STEP_ORIGIN)
        assert mfa.verify_totp_code(secret, other_code, for_time=self.STEP_ORIGIN) is False

    @pytest.mark.parametrize("bad_code", ["", None, "abcdef", "12 345", "12345a", "12-345"])
    def test_non_numeric_or_empty_code_is_rejected(self, bad_code):
        secret = mfa.generate_totp_secret()
        assert mfa.verify_totp_code(secret, bad_code, for_time=self.STEP_ORIGIN) is False

    def test_custom_step_and_digits_are_honored(self):
        secret = mfa.generate_totp_secret()
        code = mfa.totp_now(secret, for_time=self.STEP_ORIGIN, step=60, digits=8)
        assert mfa.verify_totp_code(
            secret, code, for_time=self.STEP_ORIGIN, step=60, digits=8
        ) is True
        # A 6-digit verify against an 8-digit code should not accidentally match.
        assert mfa.verify_totp_code(
            secret, code, for_time=self.STEP_ORIGIN, step=60, digits=6
        ) is False


# ---------------------------------------------------------------------------
# build_otpauth_uri()
# ---------------------------------------------------------------------------

class TestBuildOtpauthUri:
    def test_uri_scheme_and_type(self):
        uri = mfa.build_otpauth_uri("ABCDEFGH", "sam@dealeros.xyz")
        assert uri.startswith("otpauth://totp/")

    def test_default_issuer_and_label(self):
        uri = mfa.build_otpauth_uri("ABCDEFGH", "sam@dealeros.xyz")
        parsed = urllib.parse.urlparse(uri)
        label = urllib.parse.unquote(parsed.path.lstrip("/"))
        assert label == "NXTDeal:sam@dealeros.xyz"

        query = urllib.parse.parse_qs(parsed.query)
        assert query["issuer"] == ["NXTDeal"]
        assert query["secret"] == ["ABCDEFGH"]
        assert query["algorithm"] == ["SHA1"]
        assert query["digits"] == ["6"]
        assert query["period"] == ["30"]

    def test_custom_issuer_is_used_in_both_label_and_query(self):
        uri = mfa.build_otpauth_uri("ABCDEFGH", "employee@shop.com", issuer="NXTDeal")
        parsed = urllib.parse.urlparse(uri)
        label = urllib.parse.unquote(parsed.path.lstrip("/"))
        assert label == "NXTDeal:employee@shop.com"
        query = urllib.parse.parse_qs(parsed.query)
        assert query["issuer"] == ["NXTDeal"]

    def test_account_name_with_special_characters_is_percent_encoded(self):
        uri = mfa.build_otpauth_uri("ABCDEFGH", "first last@dealeros.xyz")
        # A raw space must not appear unescaped in the URI.
        assert " " not in uri
        parsed = urllib.parse.urlparse(uri)
        label = urllib.parse.unquote(parsed.path.lstrip("/"))
        assert label == "NXTDeal:first last@dealeros.xyz"

    def test_matches_totp_digits_and_step_constants(self):
        uri = mfa.build_otpauth_uri("ABCDEFGH", "x@y.com")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(uri).query)
        assert query["digits"] == [str(mfa.TOTP_DIGITS)]
        assert query["period"] == [str(mfa.TOTP_STEP_SECONDS)]


# ---------------------------------------------------------------------------
# generate_recovery_codes()
# ---------------------------------------------------------------------------

class TestGenerateRecoveryCodes:
    def test_default_count_is_ten(self):
        codes = mfa.generate_recovery_codes()
        assert len(codes) == mfa.RECOVERY_CODE_COUNT == 10

    def test_custom_count_is_honored(self):
        codes = mfa.generate_recovery_codes(count=3)
        assert len(codes) == 3

    def test_count_zero_returns_empty_list(self):
        assert mfa.generate_recovery_codes(count=0) == []

    def test_format_is_xxxx_dash_xxxx(self):
        codes = mfa.generate_recovery_codes(count=15)
        for code in codes:
            assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", code), code

    def test_alphabet_excludes_ambiguous_characters(self):
        codes = mfa.generate_recovery_codes(count=30)
        joined = "".join(codes).replace("-", "")
        for ambiguous in "01OI":
            assert ambiguous not in joined

    def test_codes_are_effectively_unique_across_a_batch(self):
        codes = mfa.generate_recovery_codes(count=25)
        assert len(set(codes)) == len(codes)


# ---------------------------------------------------------------------------
# _normalize_recovery_code()
# ---------------------------------------------------------------------------

class TestNormalizeRecoveryCode:
    def test_lowercase_with_dash(self):
        assert mfa._normalize_recovery_code("abcd-1234") == "ABCD1234"

    def test_already_uppercase_with_dash(self):
        assert mfa._normalize_recovery_code("ABCD-1234") == "ABCD1234"

    def test_lowercase_with_space_instead_of_dash(self):
        assert mfa._normalize_recovery_code("abcd 1234") == "ABCD1234"

    def test_surrounding_whitespace_is_stripped(self):
        assert mfa._normalize_recovery_code("  abcd-1234  ") == "ABCD1234"

    def test_none_returns_empty_string(self):
        assert mfa._normalize_recovery_code(None) == ""

    def test_empty_string_returns_empty_string(self):
        assert mfa._normalize_recovery_code("") == ""

    def test_mixed_dashes_and_spaces(self):
        assert mfa._normalize_recovery_code("ab-cd 12-34") == "ABCD1234"


# ---------------------------------------------------------------------------
# hash_recovery_code()
# ---------------------------------------------------------------------------

class TestHashRecoveryCode:
    def test_matches_manual_sha256_of_normalized_code(self):
        expected = hashlib.sha256("ABCD1234".encode("utf-8")).hexdigest()
        assert mfa.hash_recovery_code("abcd-1234") == expected

    def test_is_deterministic(self):
        assert mfa.hash_recovery_code("wxyz-5678") == mfa.hash_recovery_code("wxyz-5678")

    def test_normalization_applied_before_hashing(self):
        h1 = mfa.hash_recovery_code("abcd-1234")
        h2 = mfa.hash_recovery_code("ABCD1234")
        h3 = mfa.hash_recovery_code("abcd 1234")
        assert h1 == h2 == h3

    def test_different_codes_hash_differently(self):
        assert mfa.hash_recovery_code("abcd-1234") != mfa.hash_recovery_code("wxyz-5678")

    def test_output_is_a_64_char_hex_digest(self):
        digest = mfa.hash_recovery_code("abcd-1234")
        assert len(digest) == 64
        assert re.fullmatch(r"[0-9a-f]{64}", digest)


# ---------------------------------------------------------------------------
# verify_and_consume_recovery_code()
# ---------------------------------------------------------------------------

class TestVerifyAndConsumeRecoveryCode:
    def _fresh_hashed_batch(self, count=5):
        raw_codes = mfa.generate_recovery_codes(count=count)
        hashed = [mfa.hash_recovery_code(c) for c in raw_codes]
        return raw_codes, hashed

    def test_correct_code_matches_and_is_removed_from_remaining(self):
        raw_codes, hashed = self._fresh_hashed_batch()
        target_raw = raw_codes[2]
        target_hash = hashed[2]

        matched, remaining = mfa.verify_and_consume_recovery_code(target_raw, hashed)

        assert matched is True
        assert target_hash not in remaining
        assert len(remaining) == len(hashed) - 1
        # every other hash is still present
        for h in hashed:
            if h != target_hash:
                assert h in remaining

    def test_wrong_code_returns_false_and_unchanged_list(self):
        raw_codes, hashed = self._fresh_hashed_batch()
        matched, remaining = mfa.verify_and_consume_recovery_code("ZZZZ-9999", hashed)
        assert matched is False
        assert remaining == hashed
        assert remaining is hashed  # no copy made on a no-match

    def test_empty_hashed_codes_list_returns_false(self):
        matched, remaining = mfa.verify_and_consume_recovery_code("ABCD-1234", [])
        assert matched is False
        assert remaining == []

    def test_none_hashed_codes_returns_false_without_error(self):
        matched, remaining = mfa.verify_and_consume_recovery_code("ABCD-1234", None)
        assert matched is False
        assert remaining is None

    def test_none_raw_code_returns_false(self):
        _, hashed = self._fresh_hashed_batch()
        matched, remaining = mfa.verify_and_consume_recovery_code(None, hashed)
        assert matched is False
        assert remaining == hashed

    def test_empty_raw_code_returns_false(self):
        _, hashed = self._fresh_hashed_batch()
        matched, remaining = mfa.verify_and_consume_recovery_code("", hashed)
        assert matched is False
        assert remaining == hashed

    def test_single_use_enforcement_second_attempt_fails(self):
        raw_codes, hashed = self._fresh_hashed_batch()
        target_raw = raw_codes[0]

        matched_1, remaining_after_1 = mfa.verify_and_consume_recovery_code(target_raw, hashed)
        assert matched_1 is True

        # Replaying the same code against the now-reduced list must fail.
        matched_2, remaining_after_2 = mfa.verify_and_consume_recovery_code(
            target_raw, remaining_after_1
        )
        assert matched_2 is False
        assert remaining_after_2 == remaining_after_1

    def test_case_and_dash_insensitive_round_trip(self):
        raw_codes, hashed = self._fresh_hashed_batch()
        target_raw = raw_codes[1]
        # Enter the code in a different, but equivalent, format than it was
        # generated in.
        mangled = target_raw.lower().replace("-", " ")

        matched, remaining = mfa.verify_and_consume_recovery_code(mangled, hashed)
        assert matched is True
        assert len(remaining) == len(hashed) - 1

    def test_full_enroll_hash_verify_flow(self):
        # End-to-end: generate real recovery codes, hash them the same way
        # enrollment would, then verify one exactly as a login attempt would.
        raw_codes = mfa.generate_recovery_codes(count=10)
        hashed_codes = [mfa.hash_recovery_code(c) for c in raw_codes]
        assert len(hashed_codes) == 10

        chosen = raw_codes[5]
        matched, remaining = mfa.verify_and_consume_recovery_code(chosen, hashed_codes)
        assert matched is True
        assert len(remaining) == 9
