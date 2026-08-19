import hashlib
import tarfile
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUNDLE = (
    REPO_ROOT
    / "tools"
    / "fixtures"
    / "open-webui-household"
    / "open-webui-0.11.0-pristine-patch-preimages.tar.gz"
)
SOURCE_BUNDLE_SHA256 = (
    "9f68e34b2c809eb4b4d0cd3f00aa8a22689ff05a8ac37f48e3a04f99a88cecc9"
)
EXPECTED_SOURCE_FILES = frozenset(
    {
        "backend/open_webui/__init__.py",
        "backend/open_webui/main.py",
        "backend/open_webui/models/config.py",
        "backend/open_webui/retrieval/models/external.py",
        "backend/open_webui/retrieval/utils.py",
        "backend/open_webui/routers/retrieval.py",
        "backend/open_webui/tools/builtin.py",
        "backend/open_webui/utils/auth.py",
        "backend/open_webui/utils/middleware.py",
        "src/lib/apis/retrieval/index.ts",
        "src/lib/components/admin/Settings/Documents.svelte",
    }
)


def materialize_exact_open_webui_source() -> tuple[tempfile.TemporaryDirectory, Path]:
    bundle = SOURCE_BUNDLE.read_bytes()
    digest = hashlib.sha256(bundle).hexdigest()
    if digest != SOURCE_BUNDLE_SHA256:
        raise RuntimeError(f"Open WebUI source fixture digest mismatch: {digest}")

    temporary = tempfile.TemporaryDirectory()
    source_root = Path(temporary.name)
    try:
        with tarfile.open(SOURCE_BUNDLE, mode="r:gz") as archive:
            members = archive.getmembers()
            files = frozenset(member.name for member in members if member.isfile())
            if files != EXPECTED_SOURCE_FILES:
                raise RuntimeError("Open WebUI source fixture member set mismatch")
            if any(not (member.isfile() or member.isdir()) for member in members):
                raise RuntimeError(
                    "Open WebUI source fixture contains an unsafe member"
                )
            archive.extractall(source_root, filter="data")

        if any(not (source_root / relative).is_file() for relative in files):
            raise RuntimeError("Open WebUI source fixture extraction is incomplete")
    except Exception:
        temporary.cleanup()
        raise
    return temporary, source_root
