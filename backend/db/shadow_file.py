"""Experimental POSIX file boundary, confined to private disposable test directories.

Not wired into legacy saves. All writers must cooperate with this lock before
it can protect an authoritative store. No journal receipts or recovery inference.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
from uuid import UUID, uuid4

from db.import_preflight import MAX_BYTES
from db.shadow_compare import GraphObservation, ShadowRejected


def _private(info, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or (not directory and info.st_nlink != 1)):
        raise ShadowRejected('unsafe_test_file')


class _LockedFile:
    def __init__(self, directory, workspace):
        self._directory = directory
        self.workspace = workspace
        self._active = True
        self._write_uncertain = False

    def read(self):
        if not self._active:
            raise ShadowRejected('writer_lock_required')
        try:
            fd = os.open('graph.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=self._directory)
            with os.fdopen(fd, 'rb') as source:
                _private(os.fstat(source.fileno()))
                data = source.read(MAX_BYTES + 1)
            GraphObservation(self.workspace, 1, data).evidence()
            return data
        except FileNotFoundError:
            return None
        except OSError:
            raise ShadowRejected('file_read_failed') from None

    def replace(self, observation, *, expected_bytes):
        """Return evidence only after file and directory fsync have succeeded.

        Failure after replacement is explicitly uncertain. A caller must stop
        and reconcile; this method never claims to undo an authoritative write.
        """
        if not self._active:
            raise ShadowRejected('writer_lock_required')
        if self._write_uncertain:
            raise ShadowRejected('file_reconciliation_required')
        if type(observation) is not GraphObservation:
            raise ShadowRejected('invalid_observation')
        evidence = observation.evidence()
        if evidence['workspace_id'] != self.workspace:
            raise ShadowRejected('workspace_mismatch')
        if expected_bytes is not None and type(expected_bytes) is not bytes:
            raise ShadowRejected('immutable_bytes_required')
        if self.read() != expected_bytes:
            raise ShadowRejected('stale_file_snapshot')
        temporary = '.graph-' + uuid4().hex
        replaced = False
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW, 0o600, dir_fd=self._directory)
            with os.fdopen(fd, 'wb') as target:
                target.write(observation.graph_bytes)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, 'graph.json', src_dir_fd=self._directory,
                       dst_dir_fd=self._directory)
            replaced = True
            os.fsync(self._directory)
            return evidence
        except OSError:
            if replaced:
                self._write_uncertain = True
            raise ShadowRejected('file_commit_uncertain' if replaced
                                 else 'file_commit_failed') from None
        finally:
            try:
                os.unlink(temporary, dir_fd=self._directory)
            except OSError:
                pass  # Orphan staging bytes are never adopted by recovery.


@contextmanager
def locked_test_file(path, workspace_id):
    """Nonblocking cooperative lock. Caller owns/trusts the directory's parents.

    Scope naming is an accident guard, not authorization. The lock file must
    never be unlinked while the directory is in use. Windows fails closed.
    """
    if os.name != 'posix':
        raise ShadowRejected('unsupported_file_platform')
    import fcntl
    try:
        workspace = str(UUID(workspace_id))
    except (ValueError, TypeError, AttributeError):
        raise ShadowRejected('invalid_workspace_uuid') from None
    path = Path(path)
    if path.name != 'nxtdeal_shadow_test_' + UUID(workspace).hex:
        raise ShadowRejected('disposable_test_directory_required')
    directory = lock = None
    store = None
    try:
        directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        _private(os.fstat(directory), directory=True)
        lock = os.open('.writer.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                       0o600, dir_fd=directory)
        _private(os.fstat(lock))
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ShadowRejected('writer_busy') from None
        # Verify directory fsync support before allowing a replacement.
        os.fsync(directory)
    except OSError:
        if lock is not None:
            os.close(lock)
        if directory is not None:
            os.close(directory)
        raise ShadowRejected('file_lock_failed') from None
    except BaseException:
        if lock is not None:
            os.close(lock)
        if directory is not None:
            os.close(directory)
        raise
    try:
        store = _LockedFile(directory, workspace)
        yield store
    finally:
        if store is not None:
            store._active = False
        os.close(lock)
        os.close(directory)
