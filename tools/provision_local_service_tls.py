#!/usr/bin/env python3
"""Provision a persistent, root-owned TLS identity for one loopback service."""

import argparse
import grp
import os
from pathlib import Path
import ssl
import stat
import subprocess
import tempfile


def protected_directory(path: Path) -> None:
    if not path.is_absolute():
        raise ValueError("TLS directory must be absolute")
    for parent in reversed((path, *path.parents)):
        if not parent.exists():
            parent.mkdir(mode=0o755)
            # Provisioning often runs under umask 077. Consumers need to
            # traverse new directories to read the public certificate.
            parent.chmod(0o755)
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("TLS directory and its parents must be root-owned, non-writable directories")


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
        for path, expected_gid, mode in ((cert, 0, 0o644), (key, gid, 0o640)):
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != expected_gid or stat.S_IMODE(info.st_mode) != mode:
                raise ValueError("existing TLS identity has unsafe ownership or permissions")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-checkend", "0"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-checkip", "127.0.0.1"], check=True, stdout=subprocess.DEVNULL)
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
    args = parser.parse_args()
    try:
        provision(args.directory, args.group)
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"TLS provisioning refused: {error}\n")


if __name__ == "__main__":
    main()
