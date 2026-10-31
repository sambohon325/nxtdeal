"""Explicitly configured SQLite replay journal; does not activate kiosk routes.

Commit a pending marker before calling the legacy graph writer. A crash leaves an
uncertain result for staff reconciliation, never permission to repeat that write.
"""
from contextlib import contextmanager
import hmac
import json
from pathlib import Path
import sqlite3
import time

from core.kiosk_checkin import CheckinConflict, CheckinThrottled, CheckinUnconfirmed


class KioskJournal:
    MAX_RECEIPTS = 1024
    MAX_PER_MINUTE = 5

    def __init__(self, path, fingerprint_key, *, initialize=False):
        if not isinstance(initialize, bool):
            raise ValueError('initialize must be an explicit boolean')
        if not isinstance(fingerprint_key, bytes) or len(fingerprint_key) < 32:
            raise ValueError('A stable server-owned key of at least 32 bytes is required')
        self.path = Path(path).resolve()
        self._key = fingerprint_key
        if not initialize:
            self.inspect_snapshot(self.path, self._key)
            return
        # Provisioning is explicit and cannot overwrite even an empty/corrupt file.
        with self.path.open('xb'):
            pass
        try:
            with self._connect() as db:
                db.execute('CREATE TABLE metadata (id INTEGER PRIMARY KEY, proof BLOB NOT NULL)')
                db.execute('''CREATE TABLE receipts (
                    tenant TEXT NOT NULL, device TEXT NOT NULL, request TEXT NOT NULL,
                    fingerprint BLOB NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','confirmed')),
                    created REAL NOT NULL, PRIMARY KEY(tenant, device, request))''')
                db.execute('CREATE INDEX receipt_rate ON receipts(tenant, device, created)')
                proof = hmac.digest(self._key, b'nxtdeal-kiosk-journal-v1', 'sha256')
                db.execute('INSERT INTO metadata(id,proof) VALUES(1,?)', (proof,))
        except BaseException:
            self.path.unlink()  # Only the exclusively-created provisioning file.
            raise

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw',
                             uri=True, timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def _check_key(self, db):
        proof = hmac.digest(self._key, b'nxtdeal-kiosk-journal-v1', 'sha256')
        row = db.execute('SELECT proof FROM metadata WHERE id=1').fetchone()
        if not row or not hmac.compare_digest(row[0], proof):
            raise ValueError('Kiosk journal key changed or metadata is missing')

    def pending_report(self, tenant_id, *, limit=50, offset=0):
        """Read-only, tenant-scoped evidence for an internal staff review tool.

        No public route: caller must bind tenant and staff authorization. Pending
        includes active writers; a report never authorizes retry or proves absence
        of a graph write. Quiesce and reconcile against graph evidence separately.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip() or len(tenant_id) > 128:
            raise ValueError('A server-owned tenant ID is required')
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise ValueError('Invalid report page')
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
        try:
            db.execute('BEGIN')
            self._check_key(db)
            scope = (tenant_id.strip(),)
            total = db.execute("SELECT COUNT(*) FROM receipts WHERE tenant=? AND state='pending'", scope).fetchone()[0]
            rows = db.execute('''SELECT device,request,created FROM receipts
                WHERE tenant=? AND state='pending' ORDER BY created,device,request LIMIT ? OFFSET ?''',
                (*scope, limit, offset)).fetchall()
            return {
                'pending_count': total,
                'items': [{'device_id': device, 'request_id': request, 'reserved_at': created}
                          for device, request, created in rows],
                'next_offset': offset + len(rows) if offset + len(rows) < total else None,
                'retry_safe': False,
                'requires_quiesced_graph_review': True,
            }
        finally:
            db.close()

    def run(self, identity, request_id, fields, writer):
        scope = (identity.tenant_id, identity.device_id, request_id)
        fingerprint = hmac.digest(self._key, json.dumps(fields, sort_keys=True).encode(), 'sha256')
        receipt = {'status': 'checked_in', 'receipt': request_id}
        try:
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                self._check_key(db)
                old = db.execute('SELECT fingerprint,state FROM receipts WHERE tenant=? AND device=? AND request=?', scope).fetchone()
                if old:
                    if not hmac.compare_digest(old[0], fingerprint):
                        raise CheckinConflict('Request ID was already used for different input')
                    if old[1] != 'confirmed':
                        raise CheckinUnconfirmed('Check-in could not be confirmed. Ask the front desk.')
                    return receipt
                if db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0] >= self.MAX_RECEIPTS:
                    raise CheckinThrottled('Check-in journal is full. Ask the front desk.')
                now = time.time()
                count = db.execute('SELECT COUNT(*) FROM receipts WHERE tenant=? AND device=? AND created>?',
                                   (*scope[:2], now - 60)).fetchone()[0]
                if count >= self.MAX_PER_MINUTE:
                    raise CheckinThrottled('Too many check-ins. Ask the front desk.')
                db.execute('INSERT INTO receipts VALUES(?,?,?,?,?,?)', (*scope, fingerprint, 'pending', now))
            # The reservation is durable and visible to other instances before
            # any graph mutation. Do not hold a SQL transaction across the writer.
            writer()
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                self._check_key(db)
                changed = db.execute('''UPDATE receipts SET state=?
                    WHERE tenant=? AND device=? AND request=? AND state=? AND fingerprint=?''',
                    ('confirmed', *scope, 'pending', fingerprint))
                if changed.rowcount != 1:
                    raise CheckinUnconfirmed('Check-in could not be confirmed. Ask the front desk.')
            return receipt
        except (CheckinConflict, CheckinThrottled, CheckinUnconfirmed):
            raise
        except Exception:
            raise CheckinUnconfirmed('Check-in could not be confirmed. Ask the front desk.') from None

    @staticmethod
    def inspect_snapshot(path, fingerprint_key):
        """Read-only validation: never create or repair a missing/broken journal."""
        if not isinstance(fingerprint_key, bytes) or len(fingerprint_key) < 32:
            raise ValueError('A stable server-owned key of at least 32 bytes is required')
        source = Path(path).resolve()
        db = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
        try:
            if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise ValueError('Kiosk journal integrity check failed')
            proof = hmac.digest(fingerprint_key, b'nxtdeal-kiosk-journal-v1', 'sha256')
            row = db.execute('SELECT proof FROM metadata WHERE id=1').fetchone()
            if not row or not hmac.compare_digest(row[0], proof):
                raise ValueError('Kiosk journal key does not match')
            counts = dict(db.execute('SELECT state,COUNT(*) FROM receipts GROUP BY state').fetchall())
            if set(counts) - {'pending', 'confirmed'}:
                raise ValueError('Kiosk journal contains invalid receipt states')
            return {'pending': counts.get('pending', 0), 'confirmed': counts.get('confirmed', 0)}
        finally:
            db.close()

    def backup_to(self, destination):
        """SQLite-consistent snapshot to a new file; no replacement or live restore.

        This snapshots the journal only. Pause kiosk writes and coordinate a graph
        snapshot separately before treating the pair as a recovery point.
        """
        target = Path(destination).resolve()
        # Exclusive creation protects existing backups, including the live file.
        with target.open('xb'):
            pass
        try:
            source = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
            try:
                backup = sqlite3.connect(target)
                try:
                    source.backup(backup)
                finally:
                    backup.close()
            finally:
                source.close()
            return self.inspect_snapshot(target, self._key)
        except BaseException:
            target.unlink()  # Only the new file exclusively created above.
            raise
