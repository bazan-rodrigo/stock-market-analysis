"""Reintento ante lock timeout/deadlock (1205/1213) del backfill de señales."""
from types import SimpleNamespace

from app.services.signal_backfill_range import _is_retryable_lock_error


def _err(errno):
    """Imita una sqlalchemy OperationalError: .orig.args[0] = errno de MySQL."""
    return SimpleNamespace(orig=SimpleNamespace(args=(errno,)))


def test_lock_timeout_es_reintentable():
    assert _is_retryable_lock_error(_err(1205))   # Lock wait timeout


def test_deadlock_es_reintentable():
    assert _is_retryable_lock_error(_err(1213))   # Deadlock found


def test_otro_error_no_es_reintentable():
    assert not _is_retryable_lock_error(_err(1146))       # tabla inexistente
    assert not _is_retryable_lock_error(SimpleNamespace(orig=None))
    assert not _is_retryable_lock_error(SimpleNamespace())
