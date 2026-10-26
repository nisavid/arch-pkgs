# Open WebUI administrator bootstrap validation

The package and administrator-boundary checks passed for candidate `0.11.4-4`
on 2026-10-26. This is scoped security-fix evidence for [PR #145](https://github.com/nisavid/arch-pkgs/pull/145)
and [IDV-1972](https://linear.app/nisavid/issue/IDV-1972). The candidate remains
deferred and ineligible for publication or production activation. The integrated
provider, restore, rollback, and promotion gates under
[#89](https://github.com/nisavid/arch-pkgs/issues/89) and
[#90](https://github.com/nisavid/arch-pkgs/issues/90) remain open.

## Source and package identity

The build consumed commit `5179ca5a15c1e912a4f42323642e79e2c88de48e`, with
Open WebUI package tree `68a86e389345ff9a8a296c3ee38d4b3ea478b79c`.
The PKGBUILD SHA-256 is
`dc2aa05cf169db7168d77e1fcc43ffe0d593ed1bcea441cf9397da68a552ed1a`.
All 35 sources passed `makepkg --verifysource`; the CI workflow independently
verified the source set and generated `.SRCINFO`.

The retained candidate is `open-webui-0.11.4-4-x86_64.pkg.tar.zst`,
186,426,208 bytes, SHA-256
`ef5c380f0dfd1fb743f0e5a3a4018114219ecb9e1827a59e4c91ddfda11f7c8d`.
Its declared installed size is 620,405,467 bytes. This archive is a disposable
validation candidate, not the historical `0.11.4-2` candidate-set member.

## Build and payload inspection

`makepkg -f --nodeps --cleanbuild` completed inside a Bubblewrap namespace with
network access disabled, read-only host tools, and only disposable build storage
writable. The build used CPython 3.14.6 and independently extracted Node
22.23.4-1, whose package signature verified against the Arch keyring. The pinned
Python and npm closures passed their SHA-256 checks and supplied all dependency
installation inputs offline. The package was regenerated with `makepkg -R -f
--nodeps` to record the inspector's supported generic `/build` start/build path;
no archive metadata was edited manually.

This was not a clean-chroot build. Dependency installation was skipped; the
host's native providers and build tools were used. The exact previously built
RapidOCR 3.9.2-1 archive, SHA-256
`0e70fb599a535f9bb1c0c0b3a2f88abe9993f7632eba8e2c618826c7f01bf99b`,
supplied only allowlisted `rapidocr` and distribution-metadata files in an
isolated provider directory. No candidate `/usr` overlay or host package
installation was used. The result does not establish clean dependency closure,
byte reproducibility, model inference, or production suitability.

The unchanged v2 whole-archive inspector, SHA-256
`c36a5c40fae3fbb4f814060490a0061e22b91927ad0399c86e292c0ab971bc76`,
passed against the retained archive. Its deterministic receipt is
[evidence/open-webui-admin-bootstrap-package-inspection-2026-10-26.json](evidence/open-webui-admin-bootstrap-package-inspection-2026-10-26.json),
SHA-256 `e51f09d1d56431be3c388af1092134a2e6cef73a3fb53c807b2b60930babddcb`.
The receipt binds all 24,305 members, including 5,621 frontend entries and the
63-file release Pyodide payload. It reports no unsafe paths, links, ownership
or mode violations, build residue, or private server-side external-provider
payload. The dynamic provider-boundary verifier also passed.

The packaged launcher matches the source exactly and has mode 0755. The
packaged default environment file has mode 0600. The actual patched backend
files were parsed and inspected; their SHA-256 identities are:

| File under private site-packages | SHA-256 |
| --- | --- |
| `open_webui/models/auths.py` | `089d9f9c9c7b7f48016d24d5524890cdec0ba553451a2771130ef7b0f119bbb0` |
| `open_webui/utils/auth.py` | `0d9b90ae569b6a2b0c7b565943ab82948e973eb48b970aa54947f59416dd303b` |
| `open_webui/main.py` | `dd47ba3326aa9d3161a4e4c15b12b1f7929c8c959c4d3b28daa65a8ad83cb69c` |

## Full package runtime

The [runtime result receipt](evidence/open-webui-admin-bootstrap-runtime-2026-10-26.json)
binds these observations to the retained archive.

The retained archive's payload was mounted at its packaged `/opt/open-webui`
location in a separate filesystem/network namespace. The actual packaged
launcher started the complete application through its normal Typer/Uvicorn
entry point and a Unix socket. Tests used fresh temporary SQLite storage,
read-only synthetic credential files, and disposable real Qdrant and Valkey
TLS peers. No application, ORM, route, or lifespan implementations were replaced.
No production unit, route, credentials, or database was used or changed.

| Scenario | Observed result |
| --- | --- |
| Empty database, no bootstrap set | Startup fails at the administrator invariant; no listener readiness and zero user/auth rows. |
| Inherited `WEBUI_ADMIN_*` values | Launcher clears them; startup refuses with zero user/auth rows. |
| Partial bootstrap set | Launcher exits 78 before application startup. |
| Empty bootstrap password | Launcher exits 78 before application startup. |
| Complete protected bootstrap set | Application becomes healthy; exactly one admin/auth pair is persisted; sign-in returns 200 and unauthenticated signup returns 403. |
| Restart after removing all bootstrap files | Application becomes healthy, existing admin signs in, and authenticated later pending-user creation returns 200 with two user/auth pairs. |
| User/auth tables emptied while application is already ready | Unauthenticated first-user signup reaches the shared guard, returns 500, and persists zero rows. |
| Restart against the resulting empty database | Startup refuses before listener readiness and persists zero rows. |

The external embedding/reranking endpoint was deliberately unavailable. The
RAG gate remained closed; this did not prevent the commissioned application
from becoming healthy. No successful retrieval or live-provider acceptance is
claimed. The tests exercise package payload startup, not systemd activation or
credential encryption/provisioning on a production host.

## Regression and CI evidence

The focused local suite passed 98 tests and skipped two platform-dependent
cases. It includes five real-SQLite cases using the complete pinned Users/Auths
modules, real queries, model mappings, commits, and upstream session-context
functions. They cover empty, pending-only, existing-admin, and initial-admin
flows, including shared and independent sessions and row persistence.

On source head `5179ca5`,
[Repository Consistency](https://github.com/nisavid/arch-pkgs/actions/runs/40393557172)
passed 816 tests with 29 skips and the repository consistency gate. Service TLS
clients and protected identity lifecycle checks passed in the same workflow.
[Open WebUI Package Sources](https://github.com/nisavid/arch-pkgs/actions/runs/40393557246)
and CodeQL also passed. Later documentation-only commits must still pass their
own required CI and review gates before merge.

Security Cloud finding `csf_e05bc8cd00f77a12eb6cb1cf`, occurrence
`occ_99021a076872f150c0fd9200`, remains New: repository-scan resolution writeback
is unsupported. This record establishes the scoped candidate's behavior and
contains no production deployment or Cloud-resolution claim.
