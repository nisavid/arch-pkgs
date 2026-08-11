# Package Acceptance Environments

Retrieved: 2026-08-11

## Question

What is the strongest acceptance gate required by each package or compatibility
lane, which gates can run on the current Arch host or CI, and which require
installation, services, browser execution, expensive builds, privileged access,
paid infrastructure, or NVIDIA hardware?

## Provenance And Scope

This note evaluates the repository at immutable source commit
`ca744c74ea8bca30c6ac3166b7e1006821c51dba` for the Wayfinder ticket
[Determine acceptance environments for each package lane](https://github.com/nisavid/arch-pkgs/issues/20).
It combines package-local contracts at that commit with primary upstream and
platform documentation retrieved on 2026-08-11. It does not select target
versions or decide whether a package should be updated, deferred, or retired.

The package directories group into seven acceptance lanes:

- artifact ingestion: `codex-app`;
- Haystack service stack: `haystack-ai`, `hayhooks`, and
  `python-haystack-experimental`;
- Open WebUI and system ML stack: `open-webui`, `ctranslate2`,
  `python-faster-whisper`, `python-rapidocr-onnxruntime`, and
  `python-sentence-transformers`;
- Qdrant: `qdrant`;
- browser source build: `thorium-browser-updated`;
- NVIDIA TUI: `utilyze`;
- lightweight Python dependencies: `python-backoff`,
  `python-docstring-parser`, `python-fastapi-openai-compat`,
  `python-lazy-imports`, and `python-posthog`.

Every package directory is named above. The lightweight packages also inherit
the integration gate of whichever higher-level lane consumes them.

No package build, installation, service mutation, browser login, or cloud
resource was performed for this research.

## Gate Model

The strongest gate for a lane includes every lower level:

| Gate | Meaning |
| --- | --- |
| G0 — source | Regenerate `.SRCINFO`, verify source identity and checksums with `makepkg --verifysource`, and review patch application. |
| G1 — package | Build from a clean Arch environment with checks enabled, inspect metadata and payload, and review `namcap` findings. |
| G2 — installed runtime | Install the package set into a disposable Arch target and exercise imports, binaries, ownership, permissions, and upgrade/install hooks. |
| G3 — service or integration | Start the packaged service or composed dependency stack and exercise its externally visible API, persistence, restart, and upgrade behavior. |
| G4 — interactive or hardware | Exercise browser/TUI/account/hardware behavior that cannot be established by a build or API smoke alone. |

`makepkg` downloads and verifies sources, builds into a temporary root, and
creates a pacman package; a `check()` function is the package's test hook.
Arch's clean-chroot guidance exists specifically to catch undeclared
dependencies and unwanted host linkage, and `namcap` audits both `PKGBUILD`
files and package archives. Those are the common G0/G1 floor, not substitutes
for the higher gates below. Sources:
[makepkg(8)](https://man.archlinux.org/man/makepkg.8.en),
[PKGBUILD(5)](https://man.archlinux.org/man/PKGBUILD.5.en),
[building in a clean chroot](https://wiki.archlinux.org/title/DeveloperWiki:Building_in_a_clean_chroot),
and [namcap(1)](https://man.archlinux.org/man/namcap.1).

The G0/G1 wording applies to `PKGBUILD`-backed lanes. The current `codex-app`
lane has no local `PKGBUILD`; its equivalent lower gates are upstream artifact
trust and inspection of the resulting pacman payload, as described below.

## Environment Summary

The current development host is an x86-64 Arch-family system with `makepkg`,
pacman, the current Python toolchain, Rust, Clang, Ninja, Node.js, `systemd`, and
an active KDE Wayland desktop. It has ample CPU and memory for ordinary package
work, but:

- it has no visible NVIDIA device or `nvidia-smi`, so it cannot accept
  `utilyze`;
- its currently free local storage is below the 75–100 GB browser-build floor,
  so it cannot perform a fresh Thorium/Alacrium acceptance build without first
  making room or attaching a suitable build volume;
- installing packages, creating clean chroots, changing setuid/capability
  state, and starting system services are privileged mutations and need
  task-specific authorization even though the host can perform them;
- the agent sandbox is not itself an adequate substitute for the active host
  desktop or service manager.

The repository's only current GitHub Actions workflow builds and publishes the
Arch CUDA container. It does not build or install any package. A standard
public-repository `ubuntu-latest` runner has 4 vCPUs, 16 GB RAM, and 14 GB SSD,
which is useful for static checks and selected lightweight work but is far below
the Chromium disk requirement. GitHub documents larger Ubuntu runners beginning
at 150 GB SSD and workflow logs/artifacts as retention-limited rather than
durable records. Sources:
[GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[larger runners](https://docs.github.com/en/actions/reference/runners/larger-runners),
and [artifact retention](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#configuring-the-retention-period-for-github-actions-artifacts-and-logs-in-your-repository).

"CI-capable" below means a new Arch container/VM job could cover that portion.
It does not mean the repository already runs it.

## Classification

| Lane | Strongest gate | Current Arch host | Existing CI | Extra environment |
| --- | --- | --- | --- | --- |
| Lightweight Python dependencies | G2 plus the consuming lane's regression | Yes; installation or a clean chroot needs privilege | None; G0–G2 are feasible in a new Arch job | No service, browser, GPU, or paid API |
| Haystack and Hayhooks | G3 local service and no-provider pipeline/API run | Yes, with package/service authorization | None; imports and a direct-process API smoke are feasible | `systemd` for the packaged unit; no paid model provider required |
| Open WebUI and system ML | G4 installed service, browser flow, and real CPU ML functions across the system-provider boundary | Yes, with package/service authorization and model downloads | None; build/import/headless subsets are feasible | Browser and local service; no NVIDIA or paid provider required |
| Qdrant | G3 installed service, CRUD/query, restart, and disposable upgrade/snapshot recovery | Yes, with package/service authorization | None; build/API subsets are feasible | Persistent local storage; no browser, GPU, or paid service required |
| Codex app ingestion | G4 trusted artifact plus installed Linux desktop launch and human sign-in smoke | Yes, with package authorization and a user-controlled account session | None in this repo; the source repo owns macOS trust and Linux package gates | macOS trust evidence, Linux desktop, human account; no automated credential handling |
| Thorium/Alacrium browser | G4 full source build, package install, sandboxed desktop launch, and web smoke | Not with current free disk; otherwise capable | Standard CI is unsuitable | At least 100 GB free is the safe floor, browser session, privileged install; optionally a larger/self-hosted builder |
| Utilyze | G4 packaged TUI on live Ampere-or-newer NVIDIA hardware under representative workloads | No NVIDIA hardware | Current image CI is off-GPU only | Paid short-lived GPU is the selected path; root or `CAP_SYS_ADMIN`, privileged GPU container/chroot, interactive TUI |

## Lane Contracts

### Lightweight Python dependencies — G2 plus consumer regression

Build the five packages in a clean Arch environment, install them together with
their declared dependency closure, and check their public imports and installed
distribution versions. Run upstream unit tests when the selected release source
ships them; none of these local `PKGBUILD` files currently defines `check()`.

An import-only pass is insufficient as final acceptance:

- `python-backoff` and `python-posthog` must also pass the chosen Haystack
  runtime smoke;
- `python-docstring-parser` and `python-fastapi-openai-compat` must also pass the
  Hayhooks endpoint smoke;
- `python-lazy-imports` must also pass the chosen Haystack pipeline smoke.

The PostHog client must not make an acceptance run depend on a live analytics
account. Run the consumer smoke with outbound telemetry disabled and, where
practical, with egress blocked so unexpected network behavior is visible.
Haystack documents anonymous telemetry and an opt-out; the local package policy
therefore needs a deliberate test setting rather than an accidental live send.
Source: [Haystack telemetry statement](https://github.com/deepset-ai/haystack#telemetry).

Cost is low. Build trees and temporary Python caches are disposable; retain the
package hashes, `.BUILDINFO`, test output, and the exact consumer version matrix.

### Haystack and Hayhooks — G3

Accept `python-haystack-ai`, `python-haystack-experimental`, and `hayhooks` as an
exact version set, not as three isolated imports. Upstream says the newest
experimental release is tested only against the newest Haystack release, while
Hayhooks' current metadata and test environments explicitly exercise Haystack 2
and 3 separately. Sources:
[haystack-experimental compatibility](https://github.com/deepset-ai/haystack-experimental#installation)
and [Hayhooks test environments](https://github.com/deepset-ai/hayhooks/blob/main/pyproject.toml).

The strongest package gate is:

1. install the complete pacman-built set into a disposable Arch target;
2. run a provider-free in-memory Haystack pipeline so serialization, component
   wiring, and execution are real rather than import-only;
3. start the packaged `hayhooks.service` with the repository's loopback default;
4. confirm its status endpoint, deploy a minimal wrapper that needs no LLM or
   external API, invoke the generated REST endpoint, restart the service, and
   invoke it again.

Hayhooks' official quick start defines `hayhooks run`, pipeline deployment, and
the generated REST and OpenAI-compatible endpoints. Source:
[Hayhooks quick start](https://github.com/deepset-ai/hayhooks#quick-start).

Run with Haystack telemetry disabled and no provider credentials. This makes
the gate free and repeatable. The packaged service needs `systemd` and privileged
installation, but the pipeline and direct-process HTTP portions can be added to
CI independently.

Use a disposable pipelines directory rather than live
`/var/lib/hayhooks/pipelines`. If an upgrade is expected to preserve deployed
wrappers, test a synthetic representative directory copied into the disposable
target, then stop the service and remove only that fixture. Retain service logs,
HTTP requests/responses, installed versions, and the fixture digest.

### Open WebUI and system ML — G4

This lane crosses a deliberately unusual boundary: Open WebUI keeps its
non-ML Python tree private under `/opt/open-webui` but removes ML/native wheels
and imports them from pacman packages. The local package also patches upstream
for system Python 3.14, while Open WebUI's current quick-start documentation
states that Python 3.11 is the most-tested path and 3.13 is not supported. That
makes a real installed runtime gate mandatory; wheel construction alone cannot
validate the local divergence. Source:
[Open WebUI quick start](https://docs.openwebui.com/getting-started/quick-start/).

The strongest gate is:

1. clean-build and install Open WebUI with the chosen `ctranslate2` split
   package, Faster Whisper, RapidOCR, Sentence Transformers, and the intended
   system providers for PyTorch, Transformers, ONNX Runtime, NumPy, OpenCV, and
   the other externalized roots;
2. inspect the archive and installed tree to prove those roots were not
   accidentally rebundled under `/opt/open-webui`;
3. exercise the CTranslate2/OpenBLAS CPU path, a tiny Faster Whisper CPU
   transcription fixture, an OCR image through the packaged ONNX Runtime
   provider, and a small Sentence Transformers embedding model;
4. start `open-webui.service`, verify loopback binding and telemetry defaults,
   then use a browser to create a disposable local user and complete a chat
   against a loopback mock or local OpenAI-compatible provider;
5. repeat startup and a representative read after upgrading a disposable copy
   of prior state.

The ML smokes require network downloads unless test models are pinned and
cached, but they require neither NVIDIA nor a paid inference API. Faster Whisper
supports CPU execution, Sentence Transformers documents a small embedding
example, and RapidOCR documents an ONNX Runtime CPU check. Sources:
[CTranslate2 OpenBLAS build option](https://github.com/OpenNMT/CTranslate2/blob/master/docs/installation.md#build-options),
[Faster Whisper requirements](https://github.com/SYSTRAN/faster-whisper#requirements),
[Sentence Transformers example](https://github.com/UKPLab/sentence-transformers#getting-started),
and [RapidOCR installation check](https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/install/).

Open WebUI automatically migrates its database on startup and explicitly warns
that manual repair can corrupt it. Stop the service, make and verify a backup,
and test migration only on a disposable copy of the entire application data
tree, not on the live database. Its data includes accounts, chats, settings,
uploads, and generated content. Sources:
[updating and backups](https://docs.openwebui.com/getting-started/updating/)
and [database migration](https://docs.openwebui.com/troubleshooting/manual-database-migration/).

This lane needs privileged install/service control and interactive browser
evidence. Retain redacted service logs, package hashes, imported module/version
inventory, model identifiers and hashes, API fixture output, migration backup
integrity output, and one or two screenshots that contain no account secrets or
personal chats. Remove only disposable accounts, models, caches, and state
copies after capture.

### Qdrant — G3

Build and install the Rust package, start the packaged loopback service, and
exercise both advertised transports: HTTP readiness and collection CRUD/search,
plus a gRPC connection. Restart the unit and prove the inserted synthetic data
remains readable. Qdrant's local quick start defines ports 6333 and 6334 and a
create/upsert/search flow; no cloud account is needed. Sources:
[local quick start](https://qdrant.tech/documentation/quick-start/)
and [installation requirements](https://qdrant.tech/documentation/installation/).

An update gate must use disposable persistent state. Create a small collection
with payloads under the old package, stop it cleanly, snapshot it, upgrade the
copy, start the target package, and validate queries and another restart. Also
prove a snapshot can be restored into a separate empty target when the selected
version relationship supports it.

The current upstream documentation is not internally uniform about snapshot
version range: the snapshot reference says restore within the same minor
version, while the migration overview says the target may be the same or one
minor newer. Do not generalize either statement across an eventual target.
Bind the acceptance procedure to that target's release notes and test the exact
old-to-new pair. Sources:
[snapshot reference](https://qdrant.tech/documentation/operations/snapshots/)
and [migration and recovery](https://qdrant.tech/documentation/migration-recovery-options/).

No browser, GPU, or paid service is required. The source build and recovery
test are moderate CPU/disk work. Snapshot restore can temporarily require about
twice the collection's disk usage, so use a deliberately small synthetic
fixture and measure headroom first. Retain package/build hashes, API transcripts,
service logs, snapshot hash, old/new version pair, and post-restore query output;
then delete only the test collection, snapshot, and disposable storage copy.

### Codex app ingestion — G4 with a split trust/runtime gate

`codex-app` is an ingested artifact, not a package rebuilt by a local
`PKGBUILD`. Acceptance therefore has two owners:

1. **Source-artifact trust:** the `codex-app-linux` source repository must have
   built the pacman artifact from a fresh, reviewed official OpenAI DMG; run its
   tests and release gate; inspect pacman metadata and payload; and retain the
   source commit, DMG digest, app version, package digest, and release evidence.
   Its strongest trust procedure verifies the official app inside the DMG with
   Apple tooling on macOS before the Linux release gate. Source:
   [package and runtime maintenance](https://github.com/nisavid/codex-app-linux/blob/main/docs/maintainers/package-runtime-maintenance.md#validation-selection).
2. **Repository/runtime acceptance:** ingest that exact artifact, publish it to
   the disposable/local pacman repository, install it on the Arch desktop,
   inspect `/opt/codex-app`, launch `codex-app`, confirm the generated webview
   and updater service are healthy, and complete a human-controlled sign-in and
   one representative workspace interaction.

Official OpenAI documentation requires opening the desktop app and signing in
with a ChatGPT account, and currently publishes desktop downloads for Windows
or macOS. Linux behavior and packaging are therefore owned by the community
adaptation, not established by the official download alone. Sources:
[official ChatGPT desktop app quickstart](https://learn.chatgpt.com/docs/app)
and [Codex App for Linux](https://github.com/nisavid/codex-app-linux#quick-start).

The current Arch host can run the Linux desktop half after privileged package
installation. The macOS artifact-authenticity half belongs in the source repo's
manual macOS workflow or an equivalent trusted macOS host. Sign-in is HITL:
never place session material, API keys, or account credentials in CI or the
research repository. Server-side rollout or account-entitlement features are
not baseline package failures unless the chosen refresh explicitly makes one a
contract.

Use a side-by-side development identity or disposable XDG directories for
launch smokes. Never clear the user's real Codex state or updater cache as
teardown. Retain only redacted launcher/updater status, source and package
digests, the source-repo workflow link, package listings, and a screenshot that
contains no task content or account data.

### Thorium/Alacrium browser — G4

Metadata checks do not accept this package. The strongest gate is a fresh full
source build, archive inspection, privileged installation, sandboxed browser
launch, and a desktop web smoke through the installed wrapper. Record the
reported browser version and executable path, load a local HTTP fixture, check
desktop entry/icon behavior, and verify the installed Chromium sandbox has the
intended ownership and mode.

Current Alacrium documentation requires at least 75 GB free and recommends 16
GB or more RAM; current Chromium guidance calls for at least 100 GB free and
more than 16 GB RAM. The conservative package gate therefore reserves at least
100 GB plus archive/evidence headroom. Sources:
[Alacrium build requirements](https://github.com/brauliobo/alacrium/blob/main/docs/BUILDING.md#system-requirements)
and [Chromium Linux build requirements](https://chromium.googlesource.com/chromium/src/+/main/docs/linux/build_instructions.md#system-requirements).

The current host has sufficient compute but not sufficient free disk. Standard
GitHub CI is also unsuitable. Clear space deliberately, attach a large local
volume, or use a larger/self-hosted runner; rented compute is optional rather
than inherent to acceptance. Fetch/setup can itself take from tens of minutes
to hours depending on the connection, and compilation is the most expensive
lane, so retain logs and the final archive before teardown.

Upstream now uses Alacrium package, binary, and profile identities. The eventual
disposition ticket must decide the identity before the runtime fixture is
written. Do not open a refreshed binary against a real Thorium or Alacrium
profile: use a temporary `--user-data-dir`, and test profile compatibility only
against a disposable copy after the target identity and migration intent are
known. Retain source tag/commit, Chromium archive checksum, build log, package
hash/listing, sandbox-mode check, version output, and a small browser capture.
Remove only the directly owned build tree and temporary profile after those
artifacts are secured.

### Utilyze — G4 on paid NVIDIA hardware

The local `check()` covers selected config, metrics, telemetry, and TUI code,
but cannot accept the package runtime. Upstream requires Linux amd64, an NVIDIA
Ampere-or-newer GPU, CUDA 11 or newer, and `sudo`, `CAP_SYS_ADMIN`, or a
privileged container. Source:
[utilyze requirements](https://github.com/systalyze/utilyze#requirements).

The strongest gate must:

1. build and inspect the package, including all Arch patches and the no-self-
   update/privacy behavior;
2. run the repository's Arch CUDA image validation in required-GPU mode;
3. install the package into an Arch userland attached to a live
   Ampere-or-newer NVIDIA GPU;
4. start `utlz` with authorized profiling access and exercise idle, steady, and
   changing GPU workloads;
5. interact with navigation, exit, degraded states, live updates, and telemetry
   consent, including persistence for the effective root and non-root config
   locations;
6. point any consent-enabled reporting test at an owned local capture endpoint
   rather than sending acceptance telemetry to production.

NVIDIA documents that GPU performance-counter access is restricted to admin
users on current drivers and that GPU containers need the NVIDIA Container
Toolkit. Sources:
[NVIDIA profiler permissions](https://docs.nvidia.com/cuda/profiler-users-guide/index.html#restrictions)
and [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/).

The current host and current CI cannot run this gate. The selected repository
fixture is a short-lived TensorDock RTX 4090 VM with root SSH and a privileged
Arch container/chroot, with RunPod as a container fallback. This is the only
lane where paid infrastructure is mandatory under the current plan. Keep the
active window under two hours, use on-demand capacity for the first interactive
pass, and recheck live price/inventory before provisioning. TensorDock currently
advertises on-demand 4090 capacity from $0.37/hour and bills stopped instances
at a lower storage-only rate; RunPod likewise continues charging for persistent
storage on stopped pods. Sources:
[TensorDock RTX 4090](https://www.tensordock.com/gpu-4090.html)
and [RunPod pod pricing](https://docs.runpod.io/pods/pricing).

Before destroying the rig, retain the package digest, image digest, GPU model,
driver/CUDA versions, profiling policy, exact workload commands, terminal/TUI
captures, local telemetry-capture output, logs, elapsed time, and billed cost.
Then copy evidence out, delete the VM/pod and every persistent volume or
snapshot, and verify in the provider console that no compute or storage billing
remains. Do not treat "stopped" as teardown.

## Cross-Lane Execution Rules

### Privilege boundary

Keep source verification and most builds unprivileged. Obtain task-specific
authorization for clean-chroot creation, pacman installation, local-repository
publication, service control, Chromium sandbox ownership/mode, Linux
capabilities, driver policy, and cloud provisioning. Record every system change
and its reversal before applying it.

### State and migration

- Never test an upgrade against the only copy of live Open WebUI, Qdrant,
  Hayhooks, browser, Codex, or utilyze state.
- Stop writers, create a verified backup or synthetic fixture, and test a
  disposable copy.
- Treat database/profile migrations as potentially one-way. A successful
  startup is not recovery evidence; read representative data after upgrade and
  prove the backup or snapshot is usable.
- Do not commit user profiles, databases, tokens, provider identifiers, or
  machine-specific paths.

### Evidence retention

For every accepted lane, retain a concise durable record containing:

- repository commit, upstream tag/commit, source hashes, `.SRCINFO`, package
  filename/hash, and `.BUILDINFO`;
- exact commands, environment class, test versions, and pass/fail summary;
- redacted logs and API responses, plus minimal screenshots or terminal
  captures for interactive gates;
- migration fixture and backup/snapshot hashes, old/new versions, and restore
  result;
- cloud resource type, elapsed time, cost, and explicit deletion confirmation
  when paid infrastructure is used.

GitHub logs and workflow artifacts normally expire, so a workflow URL alone is
not a durable acceptance record. Commit the compact summary and hashes or link
to another deliberately retained artifact store; keep large package archives,
models, browser source trees, and private state out of Git.

## Implications For The Refresh Map

- Cheap G0/G1 checks can be standardized across lanes, but they cannot collapse
  the service, state, browser, account, or hardware decisions into one generic
  package-build ticket.
- Open WebUI, Qdrant, Codex app, Thorium/Alacrium, and utilyze each need an
  explicit acceptance fixture and evidence/teardown plan in their disposition
  ticket.
- Haystack/Hayhooks and the lightweight Python packages should be decided as
  tested compatibility sets, not a list of independently current versions.
- Only utilyze inherently needs paid infrastructure and NVIDIA hardware. Codex
  needs a human account session and macOS trust evidence; Thorium may need paid
  build capacity only if local storage is not made available.
- Existing CI establishes none of the package gates. A future stabilization
  change can add static, `.SRCINFO`, and lightweight Arch build coverage, while
  the strongest G3/G4 gates remain explicit host or external-environment work.
