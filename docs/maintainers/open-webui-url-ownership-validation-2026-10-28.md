# Open WebUI URL collection ownership validation

The source fix candidate is `open-webui` 0.11.4-5, based on repository commit
`52097a9e031a5d13dbe2d78a04e5bf44c301fbd0`. It addresses Security Cloud finding
`csf_9a9c8b6eced9037742131c36`, occurrence
`occ_abc942f66e7831eca67ae0fe`, tracked in
[IDV-1971](https://linear.app/nisavid/issue/IDV-1971).
Verification is **blocked at the package build gate**. No production deployment,
package publication, merge, or Security Cloud resolution is claimed.

## Finding and patch boundary

In the pinned Open WebUI source, `/process/web` and `/process/youtube` share
`process_web`; `/process/url` also dispatches web pages and YouTube URLs there.
Without an explicit collection name, the handler hashed only the URL and skipped
the write-authorization check. The default overwrite path reached
`save_docs_to_vector_db`, then Qdrant's tenant-wide delete, before insertion.
The same URL therefore selected another user's existing tenant.

Patch `0012-bind-url-collections-to-owner.patch` adds fixed-length owner-bound
names, reuses the shared collection authorization for both generated and supplied
targets, persists server-owned `created_by` metadata, and retains the existing
Qdrant hash-based physical collection. The authorization branch reserves both
canonical URL names and aliases normalized by Milvus or Weaviate, even when
legacy unscoped collections are enabled. Noncanonical aliases are denied,
not reinterpreted into another target. The names carry a 128-bit hash of the
complete owner ID and a 104-bit URL hash and remain 63 characters long.

Legacy URL hashes are not migrated or claimed by a new caller: they lack a
trustworthy owner binding. The existing explicit file/knowledge permissions and
administrator access remain. No pristine fixture or historical acceptance
artifact was edited.

## Source and focused validation

The downloaded 0.11.4 sdist matched the package-pinned SHA-256:
`1f1a31668a0dee733953c29d6183d78dd78984e696aa8eb0f2083f5796497be0`.
All source-tree patches (0001–0009, 0011, then 0012) apply with `--fuzz=0`;
0010 targets the installed Redis dependency and is unchanged. The affected
complete Python modules parse after patching. `bash -n` accepts `PKGBUILD`,
and the new patch digest is bound in both the recipe and `.SRCINFO`.

The test `test_original_path_replaces_other_users_data` runs the pre-fix route,
vector-save body, tenant mapping, and tenant-delete body and confirms replacement.
The patched-source cases show separate tenants for two users submitting the same
URL, no foreign overwrite/append/read, no vector operations after denied writes,
stable same-owner IDs and overwrite/append behavior, server metadata precedence,
long owner-ID isolation, malformed-name and backend-alias rejection, unchanged
authorized shared writes and administrator behavior, no-processing/bypass
behavior, and both web and YouTube dispatch paths.

These are focused execution tests with local provider/vector-service fakes;
they do not start the full application or a real Qdrant server. An independent
read-only review identified the alternate-backend alias case, which was confirmed
against source and added to the fix and regression coverage.

Final ordered gates:

| Gate / command | Result |
| --- | --- |
| `git diff --check`; `bash -n packages/open-webui/PKGBUILD` | Passed. |
| All applicable source-tree patches with `patch --batch --fuzz=0`; `python3 -m py_compile` on all three changed upstream modules | Passed against the digest-verified complete sdist. |
| Recipe source-array checksum audit | All 32 local sources matched; pinned downloaded sdist matched separately. The other three remote archives were not downloaded or independently reverified. |
| makepkg `write_srcinfo_content` library generator | Passed; regenerated `.SRCINFO` contains the new patch and checksum. Actual `makepkg --printsrcinfo` remains blocked. |
| `python -m unittest tests.test_open_webui_url_ownership` | All eight new tests passed, including pre-fix reproduction and patched attack/control/alias cases. |
| `python -m unittest tests.test_open_webui_url_ownership tests.test_open_webui_household_rag_gate tests.test_open_webui_qdrant_paging tests.test_open_webui_household_external_credentials tests.test_open_webui_service_tls -q` | 53 tests run: 51 passed, two platform-dependent skips. Initial missing `requests` and `fastapi` dependencies were installed in an isolated test environment; the rerun passed. |
| `python -m unittest tests.test_open_webui_package tests.test_open_webui_household_candidate_set -q` | 41 tests run: 36 passed, three skips, two environment errors. `makepkg --printsrcinfo` returned exit 10; the commissioning helper's Unix socket creation returned EPERM. No assertion failures. |
| `makepkg --verifysource`; `makepkg -f` | Each refused root execution, exit 10; package source verification/build/payload inspection remain blocked. |

The Python runs used an isolated Python 3.12 test environment, not the package's
Python 3.14 runtime. Relevant test dependencies included FastAPI 0.136.3,
SQLAlchemy 2.0.50, and aiosqlite 0.22.1. These checks establish the source
boundary and compatibility controls; they do not establish a successful package
build or deployment.

## Package verification limit and next gate

This session runs on Ubuntu with a root-only, capability-limited execution
identity. A real Ubuntu-packaged makepkg 6.0.2 was extracted into disposable
storage; `makepkg --printsrcinfo`, `makepkg --verifysource`, and `makepkg -f`
all stop at makepkg's root prohibition (exit 10). Bubblewrap cannot establish
a user namespace (`setting up uid map: Operation not permitted`). The root
check was not bypassed. `.SRCINFO` was generated with the unmodified makepkg
`util.sh` and `srcinfo.sh` libraries' `write_srcinfo_content`, rather than
claiming a successful makepkg invocation.

The previous 0.11.4-4 build and runtime receipts do not cover this changed
payload. On an unprivileged Arch build environment, run:

```sh
cd packages/open-webui
makepkg --printsrcinfo > generated.SRCINFO
diff -u .SRCINFO generated.SRCINFO
makepkg --verifysource
makepkg -f
python inspect-open-webui-package.py --help
```

Use the inspector's documented invocation against the resulting archive, then
run the complete packaged application with two disposable authenticated users
and local vector/provider peers to verify the URL-ownership scenarios. Retain
those exact build/runtime receipts before claiming the remediation verified.
The existing integrated acceptance and promotion gates still apply; keep the
candidate deferred and ineligible for production activation.
