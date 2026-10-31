"""Explicit, transactional migrations; no application startup side effects."""
import hashlib
import os
from pathlib import Path

MIGRATIONS = Path(__file__).with_name("migrations")
LOCK_ID = 718624091


def migrate(connection, directory=MIGRATIONS):
    """Apply a checksummed prefix under one transaction and database advisory lock.

    Caller supplies a dedicated migration connection; never an application pool.
    Any failure rolls back the entire batch, including migration tracking.
    """
    files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    versions = [p.name.split("_", 1)[0] for p in files]
    if len(set(versions)) != len(versions):
        raise ValueError("Duplicate migration version")
    # Normalize checkout line endings so Windows and Linux agree on checksums.
    migrations = [(p.name, p.read_text(encoding="utf-8-sig").encode("utf-8")) for p in files]
    applied = []
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
        connection.execute("CREATE SCHEMA IF NOT EXISTS nxtdeal_migrations")
        connection.execute("REVOKE ALL ON SCHEMA nxtdeal_migrations FROM PUBLIC")
        connection.execute("""CREATE TABLE IF NOT EXISTS nxtdeal_migrations.versions (
            name text PRIMARY KEY, sha256 text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now())""")
        existing = connection.execute(
            "SELECT name, sha256 FROM nxtdeal_migrations.versions ORDER BY name"
        ).fetchall()
        if [r[0] for r in existing] != [r[0] for r in migrations[:len(existing)]]:
            raise ValueError("Database migration history is not a prefix of this release")
        for index, (name, data) in enumerate(migrations):
            digest = hashlib.sha256(data).hexdigest()
            if index < len(existing):
                if existing[index][1] != digest:
                    raise ValueError(f"Applied migration checksum mismatch: {name}")
                continue
            connection.execute(data.decode("utf-8-sig"), prepare=False)
            connection.execute(
                "INSERT INTO nxtdeal_migrations.versions (name, sha256) VALUES (%s, %s)",
                (name, digest),
            )
            applied.append(name)
    return applied


def main():
    import psycopg
    dsn = os.environ.get("NXTDEAL_MIGRATION_DSN")
    if not dsn:
        raise SystemExit("Set NXTDEAL_MIGRATION_DSN for an explicitly selected database")
    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            applied = migrate(connection)
    except Exception as error:
        # Connection strings and server diagnostics can contain credentials or data.
        raise SystemExit(f"Migration failed ({type(error).__name__}); batch rolled back") from None
    print(f"Applied {len(applied)} migration(s)")


if __name__ == "__main__":
    main()
