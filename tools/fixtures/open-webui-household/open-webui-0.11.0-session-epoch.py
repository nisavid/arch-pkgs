"""Session-epoch enforcement seam for the exact Open WebUI 0.11.0 candidate.

The service receives the current epoch as a read-only systemd credential.  This
module deliberately has no ledger mutation API: only the root-owned external
helper may advance the epoch across a whole-runtime restore.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

CREDENTIALS_DIRECTORY_ENV = "CREDENTIALS_DIRECTORY"
CREDENTIAL_NAME = "session-epoch"
SESSION_EPOCH_CLAIM = "owui_session_epoch"
MAX_SESSION_EPOCH = (1 << 63) - 1
MAX_SERIALIZED_EPOCH_BYTES = len(str(MAX_SESSION_EPOCH))


class SessionEpochError(RuntimeError):
    """The current session epoch is absent, unsafe, or noncanonical."""


def parse_session_epoch(raw: bytes) -> int:
    """Parse the one canonical representation: unsigned ASCII decimal."""
    if not isinstance(raw, bytes):
        raise SessionEpochError("session epoch must be bytes")
    if not raw or len(raw) > MAX_SERIALIZED_EPOCH_BYTES:
        raise SessionEpochError("session epoch is empty or out of range")
    if not raw.isdigit() or (len(raw) > 1 and raw.startswith(b"0")):
        raise SessionEpochError("session epoch is not canonical unsigned decimal")

    value = int(raw)
    if value > MAX_SESSION_EPOCH:
        raise SessionEpochError("session epoch is out of range")
    return value


def _read_read_only_regular_file(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(path, flags)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise SessionEpochError("session epoch credential is not a regular file")
        if stat.S_IMODE(metadata.st_mode) & 0o222:
            raise SessionEpochError("session epoch credential is not read-only")
        return os.read(fd, MAX_SERIALIZED_EPOCH_BYTES + 1)
    except SessionEpochError:
        raise
    except OSError as error:
        raise SessionEpochError("session epoch credential is unavailable") from error
    finally:
        if fd is not None:
            os.close(fd)


def read_current_session_epoch() -> int:
    """Load the mandatory systemd credential without accepting a fallback."""
    credentials_directory = os.environ.get(CREDENTIALS_DIRECTORY_ENV)
    if not credentials_directory:
        raise SessionEpochError("systemd credentials directory is unavailable")

    directory = Path(credentials_directory)
    if not directory.is_absolute():
        raise SessionEpochError("systemd credentials directory must be absolute")

    return parse_session_epoch(
        _read_read_only_regular_file(directory / CREDENTIAL_NAME)
    )


def _validate_epoch_value(value: int) -> int:
    if type(value) is not int or value < 0 or value > MAX_SESSION_EPOCH:
        raise SessionEpochError("session epoch must be a bounded integer")
    return value


def with_current_session_epoch(
    payload: Mapping[str, Any], current_epoch: int
) -> dict[str, Any]:
    """Return a JWT payload whose epoch claim cannot be supplied by the caller."""
    epoch = _validate_epoch_value(current_epoch)
    stamped = dict(payload)
    stamped[SESSION_EPOCH_CLAIM] = epoch
    return stamped


def token_epoch_is_current(claims: Mapping[str, Any], current_epoch: int) -> bool:
    """Accept only an exact integer epoch; bool and numeric strings fail closed."""
    try:
        epoch = _validate_epoch_value(current_epoch)
    except SessionEpochError:
        return False
    claim = claims.get(SESSION_EPOCH_CLAIM)
    return type(claim) is int and claim == epoch
