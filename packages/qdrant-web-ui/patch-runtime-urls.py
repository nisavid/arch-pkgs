#!/usr/bin/env python3
"""Replace upstream automatic external data paths with inert local assets."""

from __future__ import annotations

import argparse
from pathlib import Path

REPLACEMENTS = (
    (
        "https://qdrant.tech/web-ui-info.json",
        "/dashboard/web-ui-info.json",
    ),
    (
        "https://snapshots.qdrant.io/manifest-v1.16.0.json",
        "/dashboard/datasets.json",
    ),
    ("https://snapshots.qdrant.io/", "disabled:"),
    ("http://snapshots.qdrant.io/", "disabled:"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_directory", type=Path)
    args = parser.parse_args()

    candidates = sorted(args.asset_directory.glob("index-*.js"))
    if len(candidates) != 1:
        parser.error(
            f"expected one dashboard application bundle, found {len(candidates)}"
        )

    bundle = candidates[0]
    text = bundle.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS:
        count = text.count(old)
        if count != 1:
            raise SystemExit(
                f"expected one occurrence of {old!r} in {bundle.name}, found {count}"
            )
        text = text.replace(old, new)

    if "https://qdrant.tech/web-ui-info.json" in text:
        raise SystemExit("external Web UI information URL remains after patching")
    if "snapshots.qdrant.io" in text:
        raise SystemExit("external snapshot URL remains after patching")

    bundle.write_text(text, encoding="utf-8")
    print(f"patched runtime data paths in {bundle.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
