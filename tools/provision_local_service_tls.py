#!/usr/bin/env python3
"""Provision a persistent, root-owned TLS identity for one loopback service."""

import argparse
import ctypes
import grp
import os
from pathlib import Path
import ssl
import stat
import subprocess
import tempfile


def protected_directory(path: Path, *, create: bool = True) -> None:
    if not path.is_absolute():
        raise ValueError("TLS directory must be absolute")
    for parent in reversed((path, *path.parents)):
        if not parent.exists():
            if not create:
                raise ValueError("TLS directory must already exist")
            parent.mkdir(mode=0o755)
            # Provisioning often runs under umask 077. Consumers need to
            # traverse new directories to read the public certificate.
            parent.chmod(0o755)
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("TLS directory and its parents must be root-owned, non-writable directories")
        if info.st_mode & 0o011 != 0o011:
            raise ValueError("TLS directory and its parents must be traversable by group and other users")


def validate_identity(directory: Path, gid: int, *, minimum_seconds: int | None = 0) -> None:
    """Check protected identity files, their key match, IP SAN, and validity."""
    protected_directory(directory, create=False)
    cert, key = directory / "cert.pem", directory / "key.pem"
    for path, expected_gid, mode in ((cert, 0, 0o644), (key, gid, 0o640)):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != expected_gid or stat.S_IMODE(info.st_mode) != mode:
            raise ValueError("existing TLS identity has unsafe ownership or permissions")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-checkip", "127.0.0.1"], check=True, stdout=subprocess.DEVNULL)
    if minimum_seconds is not None:
        subprocess.run(["openssl", "verify", "-CAfile", str(cert), "-purpose", "sslserver", "-verify_ip", "127.0.0.1", str(cert)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-checkend", str(minimum_seconds)], check=True, stdout=subprocess.DEVNULL)


def exchange_directories(first: Path, second: Path) -> None:
    """Atomically exchange two Linux directories, with no partial fallback."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as error:
        raise OSError("atomic TLS directory exchange is unavailable") from error
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    # AT_FDCWD and RENAME_EXCHANGE; existing paths must share a filesystem.
    if renameat2(-100, os.fsencode(first), -100, os.fsencode(second), 2) != 0:
        error = ctypes.get_errno()
        raise OSError(error, "atomic TLS directory exchange refused: " + os.strerror(error))


def rotate(directory: Path, replacement: Path, group: str, *, rollback: bool = False) -> None:
    """Exchange validated identities; preserve the previous pair for rollback."""
    if os.geteuid() != 0:
        raise ValueError("rotation requires root")
    if directory == replacement or directory.parent != replacement.parent:
        raise ValueError("live and replacement identities must be distinct sibling directories")
    gid = grp.getgrnam(group).gr_gid
    # Expired live identities still need a recovery path. Rollback may restore
    # a nearly expired certificate, but must never reactivate an expired one.
    validate_identity(directory, gid, minimum_seconds=None)
    validate_identity(replacement, gid, minimum_seconds=0 if rollback else 30 * 86400)
    for path in (directory, replacement):
        if {item.name for item in path.iterdir()} != {"cert.pem", "key.pem"}:
            raise ValueError("rotation directories must contain only cert.pem and key.pem")
    exchange_directories(directory, replacement)


def provision(directory: Path, group: str) -> None:
    if os.geteuid() != 0:
        raise ValueError("provisioning requires root")
    gid = grp.getgrnam(group).gr_gid
    protected_directory(directory)
    cert, key = directory / "cert.pem", directory / "key.pem"
    present = [p.exists() or p.is_symlink() for p in (cert, key)]
    if any(present):
        if not all(present):
            raise ValueError("incomplete TLS identity; restore it or deliberately rotate it before retrying")
        validate_identity(directory, gid)
        return
    # Generate privately; publish the key first. A partial publication fails
    # closed on re-entry instead of silently replacing an established identity.
    with tempfile.TemporaryDirectory(prefix=".tls-", dir=directory) as temporary:
        staging = Path(temporary)
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-nodes", "-days", "365", "-subj", "/CN=localhost",
            "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
            "-addext", "extendedKeyUsage=serverAuth",
            "-keyout", str(staging / "key.pem"), "-out", str(staging / "cert.pem"),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chown(staging / "key.pem", 0, gid)
        os.chmod(staging / "key.pem", 0o640)
        os.chmod(staging / "cert.pem", 0o644)
        # Hard links refuse replacement, including concurrent provisioning.
        os.link(staging / "key.pem", key)
        os.link(staging / "cert.pem", cert)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--group", required=True)
    rotation = parser.add_mutually_exclusive_group()
    rotation.add_argument("--rotate-with", type=Path, help="explicitly exchange with a staged sibling identity valid for more than 30 days")
    rotation.add_argument("--rollback-with", type=Path, help="explicitly exchange with a retained sibling identity that is still valid")
    args = parser.parse_args()
    try:
        replacement = args.rotate_with or args.rollback_with
        if replacement is None:
            provision(args.directory, args.group)
        else:
            rotate(args.directory, replacement, args.group, rollback=args.rollback_with is not None)
            print(f"TLS identities exchanged; previous identity retained at {replacement}")
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"TLS provisioning refused: {error}\n")


if __name__ == "__main__":
    main()
