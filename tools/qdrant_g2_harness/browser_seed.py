#!/usr/bin/env python3
"""Seed the browser fixture with the admin secret and mint a scoped JWT.

Usage: browser_seed.py <secret-env-file> <jwt-out-file> <seed-out.json>
The admin secret never leaves this process; the JWT is written 0600 to a
private tmpfs path and is never printed.
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx
import jwt

BASE = "http://127.0.0.1:6333"
COLLECTION = "browser-fixture"
SUBJECT = "qdrant-disposable-browser-acceptance"
LIFETIME = 300


def main() -> int:
    secret_file, jwt_out, seed_out = sys.argv[1:4]
    key, _, secret = Path(secret_file).read_text(encoding="ascii").strip().partition("=")
    if key != "QDRANT__SERVICE__API_KEY" or len(secret) < 64:
        raise SystemExit("secret file is malformed")
    deadline = time.time() + 60
    while True:
        try:
            if httpx.get(f"{BASE}/readyz", timeout=2, trust_env=False).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if time.time() > deadline:
            raise SystemExit("qdrant did not become ready")
        time.sleep(0.5)
    admin = {"api-key": secret}
    with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as h:
        created = h.put(
            f"/collections/{COLLECTION}",
            headers=admin,
            json={"vectors": {"size": 4, "distance": "Cosine"}},
        )
        points = [
            {
                "id": i,
                "vector": [((i * 7 + j * 3) % 11) / 10.0 + 0.05 for j in range(4)],
                "payload": {"label": f"point-{i}", "group": i % 2},
            }
            for i in range(1, 7)
        ]
        upserted = h.put(
            f"/collections/{COLLECTION}/points?wait=true",
            headers=admin,
            json={"points": points},
        )
        root = h.get("/").json()
    token = jwt.encode(
        {
            "sub": SUBJECT,
            "exp": int(time.time()) + LIFETIME,
            "access": [{"collection": COLLECTION, "access": "prw"}],
        },
        secret,
        algorithm="HS256",
    )
    fd = os.open(jwt_out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        stream.write(token)
    Path(seed_out).write_text(
        json.dumps(
            {
                "collection_created": created.status_code,
                "points_upserted": upserted.status_code,
                "point_count": len(points),
                "server_version": root.get("version"),
                "credential": {
                    "kind": "JWT",
                    "subject": SUBJECT,
                    "lifetimeSeconds": LIFETIME,
                    "adminSecret": False,
                    "access": [{"collection": COLLECTION, "role": "prw"}],
                },
            },
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
