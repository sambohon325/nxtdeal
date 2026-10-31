import json
import os
import tempfile

from core.auth import credential_store


def _sync_parent_directory(destination):
    """Persist the replacement directory entry on POSIX; Windows has no equivalent here.

    Failure after replace is an uncertain commit, not proof the old file survived.
    Propagate it so callers cannot report a durable success.
    """
    if os.name != "posix":
        return
    descriptor = os.open(os.path.dirname(destination), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save_credentials(filepath):

    from core.storage import demo_persistence_disabled
    if demo_persistence_disabled():  # demo tenant never persists
        return

    # Each writer owns a private temporary file on the destination filesystem.
    # This avoids shared-temp collisions and flushes contents before replacement.
    # It does not serialize in-memory mutations or prevent stale multi-worker writes.
    destination = os.path.abspath(os.fspath(filepath))
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(destination),
            prefix=".credentials-", suffix=".tmp", delete=False,
        ) as file:
            tmp_path = file.name
            json.dump(credential_store.credentials, file, indent=4)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_path, destination)
        _sync_parent_directory(destination)
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass


def _recover_partial_object(text):
    """Best-effort salvage of a truncated JSON object of records.

    credentials.json is a flat mapping of employee_id -> record object
    ({"E1001": {...}, "E1002": {...}, ...}). An interrupted write leaves a well-formed
    prefix of complete `"key": {...}` pairs followed by a half-written final pair with
    no closing `}` for the outer object. This trims back to the last complete top-level
    record and closes the outer object, so every fully-written credential is recovered
    and only the partial trailing one is dropped. Walks candidate closing braces from
    the end so a `}` inside the half-written final record can't produce invalid JSON.
    Returns {} if nothing is salvageable."""

    close = text.rfind("}")

    while close != -1:

        candidate = text[:close + 1] + "}"

        try:

            recovered = json.loads(candidate)

        except (json.JSONDecodeError, ValueError):

            close = text.rfind("}", 0, close)

            continue

        if isinstance(recovered, dict):

            return recovered

        return {}

    return {}


def load_credentials(filepath):

    try:

        with open(
            filepath,
            "r",
            encoding="utf-8"
        ) as file:

            raw = file.read()

    except FileNotFoundError:

        return

    try:

        data = json.loads(raw)

    except (json.JSONDecodeError, ValueError):

        # A truncated / corrupt credentials file must never stop the backend from
        # booting (that would also lock everyone out of login). Recover whatever
        # complete records survived and carry on.
        data = _recover_partial_object(raw)

        print(
            "WARNING: storage/credentials.json was corrupt or truncated; "
            "recovered {} complete credential records and continued.".format(len(data))
        )

    credential_store.load_credentials(data)
