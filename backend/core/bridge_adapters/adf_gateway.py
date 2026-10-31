"""Explicit NXTDeal ADF gateway v1 signature contract, not a vendor webhook schema."""
from datetime import datetime, timezone
import hashlib
import hmac
import re


class InvalidDelivery(ValueError):
    def __init__(self): super().__init__("Inbound delivery could not be verified")


def signing_bytes(endpoint_id, delivery_id, signed_at, body):
    if (not isinstance(endpoint_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{24,96}", endpoint_id) or
            not isinstance(delivery_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", delivery_id) or
            not isinstance(signed_at, str) or not re.fullmatch(r"[0-9]{10}", signed_at) or
            not isinstance(body, bytes) or not 1 <= len(body) <= 1_000_000):
        raise InvalidDelivery()
    return b"nxtdeal-adf-v1\n" + endpoint_id.encode("ascii") + b"\n" + signed_at.encode("ascii") + b"\n" + delivery_id.encode("ascii") + b"\n" + body


class ADFGatewayVerifier:
    def __init__(self, *, broker, system_id, secret_reference, account_ref, environment):
        self._broker, self._system_id = broker, system_id
        self._scope = dict(reference=secret_reference, account_ref=account_ref, environment=environment, objects=["adf_prospects"])

    def verify(self, endpoint_id, delivery_id, signed_at, signature, body):
        message = signing_bytes(endpoint_id, delivery_id, signed_at, body)
        if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature): raise InvalidDelivery()
        age = int(datetime.now(timezone.utc).timestamp()) - int(signed_at)
        if not -30 <= age <= 300: raise InvalidDelivery()
        material = self._broker.resolve(self._system_id, **self._scope)
        try:
            key = material.require("hmac_key").encode("utf-8")
            if not 32 <= len(key) <= 4096: raise InvalidDelivery()
            expected = hmac.new(key, message, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature): raise InvalidDelivery()
            material.assert_current()
            age = int(datetime.now(timezone.utc).timestamp()) - int(signed_at)
            if not -30 <= age <= 300: raise InvalidDelivery()
        except (UnicodeError, TypeError):
            raise InvalidDelivery() from None
