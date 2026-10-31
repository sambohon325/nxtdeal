"""Optional trusted-startup secret providers. No automatic binding or discovery."""
import json
import os
import re
from types import MappingProxyType

from core.bridge_credentials import CredentialUnavailable, _identifier, validate_secret_values


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CredentialUnavailable()
        result[key] = value
    return result


class EnvironmentSecretProvider:
    """Read one explicit JSON bundle from the process environment per reference.

    Configuration maps nonsecret references to exact variable names. This provider
    never enumerates the environment, loads .env files, executes commands, or
    installs broker grants. It reads the current Python environment mapping, not
    an external secret manager. Deployment-owned rotation/restart is separate.
    """
    __slots__ = ("__references",)

    def __init__(self, references):
        if (type(references) is not dict or not 1 <= len(references) <= 100 or
                any(not _identifier(reference) or not isinstance(name, str) or
                    not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", name)
                    for reference, name in references.items())):
            raise CredentialUnavailable()
        self.__references = MappingProxyType(dict(references))

    def __repr__(self):
        return "<EnvironmentSecretProvider configured references redacted>"

    def __reduce_ex__(self, protocol):
        raise TypeError("Connector secret-provider configuration cannot be serialized")

    def read(self, reference):
        try:
            name = self.__references[reference]
            raw = os.environ.get(name)
            if not isinstance(raw, str) or not 1 <= len(raw) <= 131072 or len(raw.encode("utf-8")) > 131072:
                raise CredentialUnavailable()
            values = json.loads(raw, object_pairs_hook=_unique_object)
            return validate_secret_values(values)
        except Exception:
            raise CredentialUnavailable() from None
