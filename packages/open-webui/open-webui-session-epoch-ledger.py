#!/usr/bin/env python3
"""Advance the root-owned Open WebUI session epoch outside restore state."""

from __future__ import annotations

import argparse
import fcntl
import os
import stat
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

DEFAULT_LEDGER_PATH = Path("/var/lib/open-webui-session-epoch/current")
MAX_SESSION_EPOCH = (1 << 63) - 1
MAX_SERIALIZED_EPOCH_BYTES = len(str(MAX_SESSION_EPOCH))


class SessionEpochLedgerError(RuntimeError):
    """The external ledger cannot be read or safely advanced."""


class SessionEpochLedgerMissingError(SessionEpochLedgerError):
    """The ledger has not been explicitly initialized."""


def parse_session_epoch(raw: bytes) -> int:
    if not isinstance(raw, bytes):
        raise SessionEpochLedgerError("session epoch must be bytes")
    if not raw or len(raw) > MAX_SERIALIZED_EPOCH_BYTES:
        raise SessionEpochLedgerError("session epoch is empty or out of range")
    if not raw.isdigit() or (len(raw) > 1 and raw.startswith(b"0")):
        raise SessionEpochLedgerError("session epoch is not canonical unsigned decimal")

    value = int(raw)
    if value > MAX_SESSION_EPOCH:
        raise SessionEpochLedgerError("session epoch is out of range")
    return value


def _validate_metadata(
    metadata: os.stat_result, *, required_owner_uid: int | None
) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise SessionEpochLedgerError("session epoch ledger is not a regular file")
    if metadata.st_nlink != 1:
        raise SessionEpochLedgerError("session epoch ledger must have exactly one link")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise SessionEpochLedgerError(
            "session epoch ledger is group- or world-writable"
        )
    if required_owner_uid is not None and metadata.st_uid != required_owner_uid:
        raise SessionEpochLedgerError("session epoch ledger has the wrong owner")


def _validate_parent_directory(path: Path, *, required_owner_uid: int | None) -> Path:
    if not path.is_absolute():
        raise SessionEpochLedgerError("session epoch ledger path must be absolute")

    parent = path.parent
    current = Path(parent.anchor)
    try:
        for part in parent.parts[1:]:
            current /= part
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                raise SessionEpochLedgerError(
                    "session epoch ledger path traverses a symlink"
                )
        metadata = os.lstat(parent)
    except FileNotFoundError as error:
        raise SessionEpochLedgerError(
            "session epoch ledger parent is missing"
        ) from error
    except OSError as error:
        raise SessionEpochLedgerError(
            "session epoch ledger parent is unavailable"
        ) from error

    if not stat.S_ISDIR(metadata.st_mode):
        raise SessionEpochLedgerError("session epoch ledger parent is not a directory")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise SessionEpochLedgerError(
            "session epoch ledger parent is group- or world-writable"
        )
    if required_owner_uid is not None and metadata.st_uid != required_owner_uid:
        raise SessionEpochLedgerError("session epoch ledger parent has the wrong owner")
    return parent


def _open_existing(path: Path, *, required_owner_uid: int | None) -> int:
    _validate_parent_directory(path, required_owner_uid=required_owner_uid)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError as error:
        raise SessionEpochLedgerMissingError(
            "session epoch ledger is not initialized"
        ) from error
    except OSError as error:
        raise SessionEpochLedgerError("session epoch ledger is unavailable") from error

    try:
        _validate_metadata(os.fstat(fd), required_owner_uid=required_owner_uid)
    except Exception:
        os.close(fd)
        raise
    return fd


def _read_all(fd: int) -> bytes:
    return os.read(fd, MAX_SERIALIZED_EPOCH_BYTES + 1)


def read_epoch_ledger(path: Path, *, required_owner_uid: int | None = 0) -> int:
    ledger = Path(path)
    fd = _open_existing(ledger, required_owner_uid=required_owner_uid)
    try:
        return parse_session_epoch(_read_all(fd))
    finally:
        os.close(fd)


def _write_all(stream: BinaryIO, raw: bytes) -> None:
    stream.write(raw)
    stream.flush()
    os.fsync(stream.fileno())


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(directory, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_epoch(
    path: Path, value: int, *, required_owner_uid: int | None
) -> None:
    raw = str(value).encode("ascii")
    if parse_session_epoch(raw) != value:
        raise SessionEpochLedgerError("refusing to write a noncanonical session epoch")

    _validate_parent_directory(path, required_owner_uid=required_owner_uid)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    replaced = False
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as stream:
            fd = -1
            _write_all(stream, raw)
        os.replace(temporary_path, path)
        replaced = True
        _fsync_directory(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        if not replaced:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


@contextmanager
def _exclusive_ledger_lock(
    path: Path, *, required_owner_uid: int | None
) -> Iterator[None]:
    _validate_parent_directory(path, required_owner_uid=required_owner_uid)
    lock_path = path.with_name(f"{path.name}.lock")
    flags = (
        os.O_CREAT
        | os.O_RDWR
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise SessionEpochLedgerError(
            "session epoch ledger lock is unavailable"
        ) from error

    try:
        os.fchmod(fd, 0o600)
        _validate_metadata(os.fstat(fd), required_owner_uid=required_owner_uid)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def initialize_epoch_ledger(path: Path, *, required_owner_uid: int | None = 0) -> int:
    """Explicitly create epoch zero; never reset or repair existing state."""
    ledger = Path(path)
    with _exclusive_ledger_lock(ledger, required_owner_uid=required_owner_uid):
        try:
            return read_epoch_ledger(ledger, required_owner_uid=required_owner_uid)
        except SessionEpochLedgerMissingError:
            _atomic_write_epoch(
                ledger,
                0,
                required_owner_uid=required_owner_uid,
            )
            return read_epoch_ledger(ledger, required_owner_uid=required_owner_uid)


def reserve_next_epoch(path: Path, *, required_owner_uid: int | None = 0) -> int:
    """Atomically reserve N+1 before a whole-runtime restore begins."""
    ledger = Path(path)
    with _exclusive_ledger_lock(ledger, required_owner_uid=required_owner_uid):
        current = read_epoch_ledger(ledger, required_owner_uid=required_owner_uid)
        if current == MAX_SESSION_EPOCH:
            raise SessionEpochLedgerError("session epoch is exhausted")
        reserved = current + 1
        _atomic_write_epoch(
            ledger,
            reserved,
            required_owner_uid=required_owner_uid,
        )
        return read_epoch_ledger(ledger, required_owner_uid=required_owner_uid)


def require_root_mutation_authority() -> None:
    if os.geteuid() != 0:
        raise SessionEpochLedgerError("session epoch mutations require root")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("initialize", "current", "reserve"),
        help="explicit ledger operation",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help=f"root-owned ledger outside restore state (default: {DEFAULT_LEDGER_PATH})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        if args.command == "current":
            value = read_epoch_ledger(args.ledger, required_owner_uid=0)
        else:
            require_root_mutation_authority()
            if args.command == "initialize":
                value = initialize_epoch_ledger(args.ledger, required_owner_uid=0)
            else:
                value = reserve_next_epoch(args.ledger, required_owner_uid=0)
    except SessionEpochLedgerError as error:
        print(f"open-webui-session-epoch-ledger: {error}", file=sys.stderr)
        return 1

    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
