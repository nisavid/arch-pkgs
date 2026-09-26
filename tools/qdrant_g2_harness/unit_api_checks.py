#!/usr/bin/env python3
"""G2 REST/gRPC checks for the exact packaged Qdrant unit.

Runs on the host inside the disposable container's network namespace (the
container itself has network=none), so only the container's loopback is
reachable. Reads the admin/HMAC secret from a private file, never prints it,
and writes a raw result document for the evidence writer.

Usage: unit_api_checks.py <pre-restart|post-restart> <secret-env-file> <out.json>
"""
import json
import sys
import time
from pathlib import Path

import grpc
import httpx
import jwt

sys.path.insert(0, str(Path(__file__).resolve().parent / "grpc_stubs"))
import points_pb2  # noqa: E402
import points_service_pb2_grpc  # noqa: E402
import json_with_int_pb2  # noqa: E402,F401
import qdrant_common_pb2  # noqa: E402

BASE = "http://127.0.0.1:6333"
GRPC = "127.0.0.1:6334"
FIXTURE = "g2-fixture"
EXPECTED_VERSION = "1.19.1"
GRPC_POINT_ID = 900


def load_secret(path: str) -> str:
    line = Path(path).read_text(encoding="ascii").strip()
    key, _, value = line.partition("=")
    if key != "QDRANT__SERVICE__API_KEY" or len(value) < 64:
        raise SystemExit("secret file is malformed")
    return value


def token(secret: str, access: str, lifetime: int = 300) -> str:
    return jwt.encode(
        {
            "sub": "qdrant-disposable-g2-unit",
            "exp": int(time.time()) + lifetime,
            "access": [{"collection": FIXTURE, "access": access}],
        },
        secret,
        algorithm="HS256",
    )


def status(response: httpx.Response) -> int:
    return response.status_code


class Client:
    def __init__(self, secret: str):
        self.http = httpx.Client(base_url=BASE, timeout=30.0, trust_env=False)
        self.admin = {"api-key": secret}

    def bearer(self, jwt_token: str) -> dict:
        return {"authorization": f"Bearer {jwt_token}"}


def vector(seed: int) -> list[float]:
    return [((seed * 7 + i * 3) % 11) / 10.0 + 0.05 for i in range(4)]


def pre_restart(secret: str) -> dict:
    c = Client(secret)
    out: dict = {}
    h = c.http

    root = h.get("/")
    out["public_root"] = {
        "status": status(root),
        "body": root.json(),
        "exact": root.json()
        == {"title": "qdrant - vector search engine", "version": EXPECTED_VERSION},
    }
    out["unauthenticated"] = {
        "collections": status(h.get("/collections")),
        "quotas": status(h.get("/quotas")),
    }
    collections = h.get("/collections", headers=c.admin)
    quotas = h.get("/quotas", headers=c.admin)
    out["admin"] = {
        "collections_status": status(collections),
        "quotas_status": status(quotas),
        "quotas_result": quotas.json().get("result"),
    }

    # Fixture plus 63 more collections reach the configured maximum of 64.
    body = {"vectors": {"size": 4, "distance": "Cosine"}}
    created = []
    for name in [FIXTURE] + [f"limit-{n:02d}" for n in range(2, 65)]:
        response = h.put(f"/collections/{name}", headers=c.admin, json=body)
        created.append((name, status(response)))
    over = h.put("/collections/limit-65", headers=c.admin, json=body)
    listed = h.get("/collections", headers=c.admin).json()["result"]["collections"]
    out["collection_quota"] = {
        "created_ok": sum(1 for _, s in created if s == 200),
        "create_statuses": sorted({s for _, s in created}),
        "listed": len(listed),
        "sixty_fifth_status": status(over),
        "sixty_fifth_error": over.json().get("status", {}).get("error"),
    }

    points = [
        {"id": i, "vector": vector(i), "payload": {"label": f"p{i}", "group": i % 2}}
        for i in range(1, 7)
    ]
    seeded = h.put(
        f"/collections/{FIXTURE}/points?wait=true", headers=c.admin, json={"points": points}
    )
    out["fixture_seed_status"] = status(seeded)

    prw, r, rw = token(secret, "prw"), token(secret, "r"), token(secret, "rw")
    write_body = {"points": [{"id": 101, "vector": vector(101), "payload": {"label": "jwt"}}]}
    read_body = {"ids": [1, 101], "with_payload": True}

    def management(jwt_token: str) -> dict:
        hdr = c.bearer(jwt_token)
        return {
            "collectionCreate": status(
                h.put("/collections/g2-denied", headers=hdr, json=body)
            ),
            "collectionDelete": status(h.delete(f"/collections/{FIXTURE}", headers=hdr)),
            "alias": status(
                h.post(
                    "/collections/aliases",
                    headers=hdr,
                    json={
                        "actions": [
                            {
                                "create_alias": {
                                    "collection_name": FIXTURE,
                                    "alias_name": "g2-denied-alias",
                                }
                            }
                        ]
                    },
                )
            ),
            "snapshot": status(h.post(f"/collections/{FIXTURE}/snapshots", headers=hdr)),
            "quotas": status(h.get("/quotas", headers=hdr)),
            "configuration": status(
                h.patch(
                    f"/collections/{FIXTURE}",
                    headers=hdr,
                    json={"optimizers_config": {"indexing_threshold": 20001}},
                )
            ),
        }

    prw_write = h.put(
        f"/collections/{FIXTURE}/points?wait=true", headers=c.bearer(prw), json=write_body
    )
    prw_read = h.post(f"/collections/{FIXTURE}/points", headers=c.bearer(prw), json=read_body)
    r_read = h.post(f"/collections/{FIXTURE}/points", headers=c.bearer(r), json=read_body)
    r_write = h.put(
        f"/collections/{FIXTURE}/points?wait=true", headers=c.bearer(r), json=write_body
    )
    rw_snapshot = h.post(f"/collections/{FIXTURE}/snapshots", headers=c.bearer(rw))
    rw_snapshot_name = None
    if status(rw_snapshot) == 200:
        rw_snapshot_name = rw_snapshot.json()["result"]["name"]
        h.delete(f"/collections/{FIXTURE}/snapshots/{rw_snapshot_name}", headers=c.admin)
    out["jwt_rest"] = {
        "prw_write": status(prw_write),
        "prw_read": status(prw_read),
        "prw_read_ids": sorted(p["id"] for p in prw_read.json().get("result", [])),
        "r_read": status(r_read),
        "r_write": status(r_write),
        "prw_management": management(prw),
        "r_management": management(r),
        "rw_snapshot_create": status(rw_snapshot),
        "rw_snapshot_removed_by_admin": rw_snapshot_name is not None
        and all(
            s["name"] != rw_snapshot_name
            for s in h.get(f"/collections/{FIXTURE}/snapshots", headers=c.admin).json()[
                "result"
            ]
        ),
    }

    out["grpc"] = grpc_checks(secret, prw, r)

    origin = {"origin": "http://cors-probe.invalid", "access-control-request-method": "GET"}
    unauth_preflight = h.options("/collections", headers=origin)
    auth_preflight = h.options("/collections", headers={**origin, **c.admin})
    out["cors"] = {
        "unauthenticated_preflight_status": status(unauth_preflight),
        "authenticated_preflight_status": status(auth_preflight),
        "allow_origin_absent": "access-control-allow-origin" not in unauth_preflight.headers
        and "access-control-allow-origin" not in auth_preflight.headers,
    }

    dashboard = h.get("/dashboard/")
    cloud = h.get("/dashboard/cloud/data.json")
    out["dashboard"] = {
        "status": status(dashboard),
        "content_security_policy": dashboard.headers.get("content-security-policy"),
        "referrer_policy": dashboard.headers.get("referrer-policy"),
        "content_type_options": dashboard.headers.get("x-content-type-options"),
        "frame_options": dashboard.headers.get("x-frame-options"),
        "cloud_data_status": status(cloud),
        "cloud_data_value": cloud.json() if status(cloud) == 200 else "unavailable",
    }

    query = {"query": vector(1), "limit": 1000}
    out["strict_mode"] = {
        "query_limit_1000": status(
            h.post(f"/collections/{FIXTURE}/points/query", headers=c.admin, json=query)
        ),
        "query_limit_1001": status(
            h.post(
                f"/collections/{FIXTURE}/points/query",
                headers=c.admin,
                json={**query, "limit": 1001},
            )
        ),
        "timeout_120": status(
            h.post(
                f"/collections/{FIXTURE}/points/query?timeout=120",
                headers=c.admin,
                json={**query, "limit": 10},
            )
        ),
        "timeout_121": status(
            h.post(
                f"/collections/{FIXTURE}/points/query?timeout=121",
                headers=c.admin,
                json={**query, "limit": 10},
            )
        ),
    }
    recover = h.put(
        f"/collections/{FIXTURE}/snapshots/recover",
        headers=c.admin,
        json={"location": "http://127.0.0.1:9/g2-url-recovery.snapshot"},
    )
    out["url_snapshot_recovery"] = {
        "status": status(recover),
        "error": recover.json().get("status", {}).get("error")
        if recover.headers.get("content-type", "").startswith("application/json")
        else None,
    }
    return out


def grpc_checks(secret: str, prw: str, r: str) -> dict:
    channel = grpc.insecure_channel(GRPC)
    stub = points_service_pb2_grpc.PointsStub(channel)

    def get(metadata):
        return stub.Get(
            points_pb2.GetPoints(
                collection_name=FIXTURE,
                ids=[qdrant_common_pb2.PointId(num=1), qdrant_common_pb2.PointId(num=GRPC_POINT_ID)],
            ),
            metadata=metadata,
            timeout=30,
        )

    def upsert(metadata):
        return stub.Upsert(
            points_pb2.UpsertPoints(
                collection_name=FIXTURE,
                wait=True,
                points=[
                    points_pb2.PointStruct(
                        id=qdrant_common_pb2.PointId(num=GRPC_POINT_ID),
                        vectors=points_pb2.Vectors(
                            vector=points_pb2.Vector(
                                dense=points_pb2.DenseVector(data=vector(GRPC_POINT_ID))
                            )
                        ),
                    )
                ],
            ),
            metadata=metadata,
            timeout=30,
        )

    def outcome(call, metadata):
        try:
            response = call(metadata)
        except grpc.RpcError as error:
            return {"code": error.code().name}
        if call is get:
            return {"code": "OK", "ids": sorted(p.id.num for p in response.result)}
        return {"code": "OK"}

    result = {
        "unauthenticated_read": outcome(get, ()),
        "prw_write": outcome(upsert, (("authorization", f"Bearer {prw}"),)),
        "prw_read": outcome(get, (("authorization", f"Bearer {prw}"),)),
        "r_read": outcome(get, (("authorization", f"Bearer {r}"),)),
        "r_write": outcome(upsert, (("authorization", f"Bearer {r}"),)),
    }
    channel.close()
    return result


def post_restart(secret: str) -> dict:
    c = Client(secret)
    h = c.http
    listed = h.get("/collections", headers=c.admin).json()["result"]["collections"]
    prw = token(secret, "prw")
    channel = grpc.insecure_channel(GRPC)
    stub = points_service_pb2_grpc.PointsStub(channel)
    got = stub.Get(
        points_pb2.GetPoints(
            collection_name=FIXTURE, ids=[qdrant_common_pb2.PointId(num=GRPC_POINT_ID)]
        ),
        metadata=(("authorization", f"Bearer {prw}"),),
        timeout=30,
    )
    channel.close()
    rest = h.post(
        f"/collections/{FIXTURE}/points",
        headers=c.admin,
        json={"ids": [1, 2, 3, 4, 5, 6, 101], "with_payload": True},
    )
    root = h.get("/")
    return {
        "public_root_version": root.json().get("version"),
        "collections_listed": len(listed),
        "grpc_point_preserved": [p.id.num for p in got.result] == [GRPC_POINT_ID],
        "rest_points_preserved": sorted(p["id"] for p in rest.json()["result"]),
    }


def wait_ready() -> None:
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/readyz", timeout=2, trust_env=False).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise SystemExit("qdrant did not become ready")


def main() -> int:
    mode, secret_file, out_path = sys.argv[1:4]
    secret = load_secret(secret_file)
    wait_ready()
    result = pre_restart(secret) if mode == "pre-restart" else post_restart(secret)
    text = json.dumps(result, indent=1, sort_keys=True)
    if secret in text:
        raise SystemExit("refusing to write a result that contains the secret")
    Path(out_path).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
