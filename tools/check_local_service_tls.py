#!/usr/bin/env python3
"""Report approaching local-service TLS expiry without changing the identity."""

import argparse
from pathlib import Path
import subprocess
import sys


def check_certificate(certificate: Path, warn_days: int = 30) -> tuple[int, str]:
    """Return an actionable failure for invalid, expired, or expiring certificates."""
    if warn_days < 0:
        raise ValueError("warning threshold must be nonnegative")
    command = ["openssl", "x509", "-in", str(certificate), "-noout"]
    expiry = subprocess.run([*command, "-enddate"], capture_output=True, text=True)
    if expiry.returncode:
        return 1, f"TLS ERROR: cannot read certificate {certificate}; inspect the configured identity."
    end_date = expiry.stdout.strip().removeprefix("notAfter=")
    valid = subprocess.run([*command, "-checkend", "0"], capture_output=True)
    if valid.returncode:
        return 1, f"TLS EXPIRED: {certificate} expired at {end_date}; rotate the identity before restarting consumers."
    warning = subprocess.run([*command, "-checkend", str(warn_days * 86400)], capture_output=True)
    if warning.returncode:
        return 1, f"TLS EXPIRY WARNING: {certificate} expires within {warn_days} days, at {end_date}; schedule deliberate rotation now."
    return 0, f"TLS OK: {certificate} expires at {end_date}, beyond the {warn_days}-day warning threshold."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--warn-days", type=int, default=30)
    args = parser.parse_args()
    try:
        code, message = check_certificate(args.certificate, args.warn_days)
    except (OSError, ValueError) as error:
        parser.exit(1, f"TLS ERROR: {error}\n")
    print(message, file=sys.stderr if code else sys.stdout)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
