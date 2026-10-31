"""Malformed bearer input must be a normal authentication denial."""
import pytest
from core.auth import verify_token


@pytest.mark.parametrize('token', [None, b'bytes.token', 42, 'invalid.\u00e9', '\ud800.signature'])
def test_malformed_staff_token_is_rejected_without_exception(token):
    assert verify_token(token) is None
