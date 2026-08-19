#!/usr/bin/python
import argparse
import importlib.metadata
import re
import sys
from pathlib import Path, PurePosixPath


EXTERNALIZED_DISTRIBUTIONS = (
    "accelerate",
    "av",
    "ctranslate2",
    "faster-whisper",
    "numpy",
    "onnxruntime",
    "opencv-python",
    "opencv-python-headless",
    "pandas",
    "pillow",
    "pyarrow",
    "pyclipper",
    "rapidocr",
    "scikit-learn",
    "scipy",
    "sentence-transformers",
    "sentencepiece",
    "shapely",
    "tokenizers",
    "torch",
    "transformers",
)

FALLBACK_ROOTS = {
    "opencv-python": {"cv2"},
    "opencv-python-headless": {"cv2"},
}


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def provider_payload() -> tuple[set[str], set[str]]:
    roots: set[str] = set()
    scripts: set[str] = set()
    for name in EXTERNALIZED_DISTRIBUTIONS:
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            fallback = FALLBACK_ROOTS.get(name)
            if fallback is None:
                raise RuntimeError(f"system provider metadata is unavailable: {name}") from None
            roots.update(fallback)
            continue
        inventory = tuple(distribution.files or ())
        if not inventory:
            fallback = FALLBACK_ROOTS.get(name)
            if fallback is None:
                raise RuntimeError(
                    f"system provider file inventory is unavailable: {name}"
                )
            roots.update(fallback)
        for item in inventory:
            path = PurePosixPath(str(item))
            if not path.parts or path.parts[0] in {"..", "."}:
                continue
            roots.add(path.parts[0])
        for entry_point in distribution.entry_points:
            if entry_point.group == "console_scripts":
                scripts.add(entry_point.name)
    return roots, scripts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site_packages", type=Path)
    arguments = parser.parse_args()
    site = arguments.site_packages.resolve()
    if not site.is_dir():
        parser.error(f"not a site-packages directory: {site}")

    forbidden_names = {canonical(name) for name in EXTERNALIZED_DISTRIBUTIONS}
    violations: set[Path] = set()
    for distribution in importlib.metadata.distributions(path=[str(site)]):
        name = distribution.metadata.get("Name", "")
        if canonical(name) in forbidden_names:
            violations.add(Path(distribution._path))

    roots, scripts = provider_payload()
    for root in roots:
        candidate = site / root
        if candidate.exists() or candidate.is_symlink():
            violations.add(candidate)
    for script in scripts:
        candidate = site / "bin" / script
        if candidate.exists() or candidate.is_symlink():
            violations.add(candidate)

    if violations:
        for violation in sorted(violations):
            print(f"externalized provider payload under private root: {violation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
