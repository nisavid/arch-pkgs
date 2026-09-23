# Open WebUI household acceptance

This is the runbook for
[Acceptance-deploy the Open WebUI household candidate set](https://github.com/nisavid/arch-pkgs/issues/89).
It deploys the exact candidate bytes from
[Build the Open WebUI household candidate set from main](https://github.com/nisavid/arch-pkgs/issues/88)
as user-level services under a disposable root, wires them to the
live-validated Lemonade provider, and runs **one** integrated trial set with
one restore drill and one rollback drill.

The kit is `tools/accept_open_webui_household.py` (evidence schema
`open-webui-household-acceptance/v1`) plus the shared scenario module
`tools/open_webui_household_scenarios.py`. The kit PR alone means *source
updated*. The candidate set is *acceptance deployed* only after the trial's
evidence merges.

## Trial shape

The approved scope of
[Execute the accepted Arch package refresh](https://github.com/nisavid/arch-pkgs/issues/46)
fixes the shape:

- Exactly one integrated trial set: one restore drill and one rollback drill.
  No loops, no repeated runs, no heavy uploads, no sharing scenarios, and no
  vector-generation machinery.
- The numeric limits recorded on
  [Set Open WebUI acceptance limits and create its execution tickets](https://github.com/nisavid/arch-pkgs/issues/70)
  are ceilings for this first trial only. The values the trial records become
  the baseline for
  [Deploy the accepted Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/59).
- The only resource gates are **no OOM kill** and **no unplanned restart**.
  Every other resource value is recorded, not gated.
- Open WebUI's Lemonade connection uses no credential in this refresh (owner
  decision). The ticket's earlier Lemonade-connection items are superseded;
  the no-credential check below replaces them.
- The trial runs on the host's real ML provider set (owner decision). The
  evidence records each provider's pacman identity as a knowingly-foreign
  provider of record, and no provider is overlaid; see
  [Evidence handling](#evidence-handling).

## Prerequisites

Do not start the trial until all of these hold. The kit code and the stub
rehearsal may run earlier.

1. **The Lemonade M4 signal.** The lemonade ticket "Confirm the candidate is
   installed and live-validated on the host"
   (https://github.com/nisavid/lemonade/issues/156) is closed, and the lead has
   recorded its receipt ids in the arch-strix-halo-pkgs `current-state.md`.
   The trial evidence cites those ids. This repository writes nothing to the
   lemonade repository.
2. **The candidate of record.** The pull request that stages the candidate has
   merged, and
   [Build the Open WebUI household candidate set from main](https://github.com/nisavid/arch-pkgs/issues/88)
   has recorded its manifest, either by adopting the pre-merge bytes through
   its tree-id equality check or by rebuilding. The kit reads that manifest
   (`--manifest`); it never reads a directory listing. Because only one trial
   set is allowed, running it on non-record bytes would waste it.
   The candidate of record for the Open WebUI pair, which the manifest must
   carry, is:

   | Archive | Size (bytes) | SHA-256 |
   | --- | --- | --- |
   | `open-webui-0.11.0-5-x86_64.pkg.tar.zst` | 240005573 | `bd273be8c33287f7ac3c44592c91005034da8ada886fbd8a480f3dbf7a7e2fc8` |
   | `python-rapidocr-3.9.2-1-any.pkg.tar.zst` | 27198440 | `0e70fb599a535f9bb1c0c0b3a2f88abe9993f7632eba8e2c618826c7f01bf99b` |

   The candidate store also keeps superseded archives under the same names
   (an earlier `open-webui-0.11.0-5` build differs in size and digest), so
   the kit picks the store file whose size and SHA-256 match the manifest
   record, never the first name match.
3. **The build root.** A user-owned directory on a filesystem below 80% use.
   The preferred root is `/srv/build/arch-pkgs-owui-acceptance`. Any other
   filesystem needs lead or owner approval. Preflight refuses `/home`, the shared `/tmp` volume, any root at
   80% use or more, and any root whose projected footprint (about 6 GB
   apparent at peak) does not fit. Qdrant's packaged 85% disk quota is never
   lowered; a quota trip stops the trial with no override.
4. **Approved inputs.** With the user's explicit download permission, placed
   under `<root>/inputs/` and checked by digest:
   - `caddy`, `python-omegaconf`, and `python-antlr4`: the kit prefers the
     host-installed package and records its pacman identity (version,
     architecture, build date, install reason). Only for a package the host
     lacks does it extract an archive from `<root>/inputs/`, after checking
     it against the sync database `%SHA256SUM%`;
   - the Whisper model snapshot `Systran/faster-whisper-base` at revision
     `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`, as the flat directory
     `<root>/inputs/faster-whisper-base/` holding exactly these files:

     | File | SHA-256 |
     | --- | --- |
     | `config.json` | `56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a` |
     | `model.bin` | `d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9` |
     | `tokenizer.json` | `fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab` |
     | `vocabulary.txt` | `34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913` |

     `stage` checks every digest before it places anything, and places only
     these four files. `tiny` stays available only when `--whisper-model tiny`
     is named; its pins are in `tools/open_webui_household_scenarios.py`;
   - the audio clip `jfk.flac` from faster-whisper 1.2.1, SHA-256
     `63a4b1e4c1dc655ac70961ffbf518acd249df237e5a0152faae9a4a836949715`.
5. **Resident models.** The zembed, zerank, and designated chat models are
   already loaded in Lemonade. The kit never loads, unloads, pins, pulls,
   restarts, or reconfigures Lemonade. If a model is not loaded, preflight
   and every re-entry after a restart, restore, or rollback exit 75 with
   `NEEDS LEAD` instead of triggering a load.
6. **Host tools.** `bwrap`, `socat`, `bsdtar`, `sqlite3`, `unshare`,
   `systemd-creds`, the host `valkey-server`, and the host
   `python-ctranslate2-gfx1151` 4.7.2 speech provider. A user manager with
   lingering enabled.
7. **A household window.** The trial runs in an announced window that does not
   overlap a Lemonade redeploy. A Lemonade restart during the trial voids the
   run; the lead decides whether one rerun is allowed.
8. **No concurrent builds.** The trial runs its units under a capped user
   `builds.slice` (see `--slice`), which package builds share. Hold every
   build on the host for the whole trial: a build that fills the shared cap
   could OOM-kill a trial service and fail the no-OOM resources gate
   spuriously.

## Parameters

Every subcommand takes the same parameter set. Nothing host-specific is
committed; the evidence records each value used.

| Option | Default | Meaning |
| --- | --- | --- |
| `--root DIR` | `/srv/build/arch-pkgs-owui-acceptance` | Disposable acceptance root. It holds a `.owui-acceptance` marker, and teardown deletes only a marked root. |
| `--manifest FILE` | none; required | The candidate manifest of record from the build ticket (name, size, SHA-256, source commit). |
| `--lemond-url URL` | `http://127.0.0.1:13305` | Lemonade base URL. Only `GET /api/v1/health`, `GET /api/v1/models`, and inference requests are sent. In record mode it must be the provider origin of the packaged `open-webui.env` (`RAG_OPENAI_API_BASE_URL` and `RAG_EXTERNAL_RERANKER_URL`); otherwise preflight and every re-entry exit 75. |
| `--chat-model ID` | `user.Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL` (owner-pinned) | The resident chat model used for ordinary chat and the cited answer. Readiness accepts this canonical id or its bare form without the leading `user.`. |
| `--embedding-model ID` | the packaged env's `RAG_EMBEDDING_MODEL` | zembed id that must be served and loaded. |
| `--reranking-model ID` | the packaged env's `RAG_RERANKING_MODEL` | zerank id that must be served and loaded. |
| `--whisper-model NAME` | `base` | Pinned Whisper size, `base` or `tiny`; the revision and every file SHA-256 are recorded. |
| `--provider stub\|lemond` | `lemond` | `stub` serves the rehearsal from `stub_provider.py`; `lemond` is the trial. |
| `--rehearsal` | off | Required with `--provider stub`; marks every output `mode=rehearsal`. |
| `--slice NAME` | `owui-acc.slice` | The user slice every kit unit runs under: a plain systemd slice unit name ending in `.slice`. `stage` records it in `kit.json`, and every later subcommand reads it from there; a later `--slice` that differs from the staged one is refused. systemd nests slices by dashes, so `builds-owui_acc.slice` is a child of `builds.slice`. |

A served model id that differs from the expected one exits 75 and escalates.
The one equivalence is a leading `user.`: a canonical `user.` id and its bare
name name the same model, because Lemonade's listings may show either.
Otherwise the kit never remaps ids; a mismatch means a new candidate or a
lead-approved override.

## Command sequence

Run from a checkout of this repository at the kit commit. Each step is
idempotent up to its own outputs, and each refuses when its precondition does
not hold.

```bash
kit=tools/accept_open_webui_household.py
args=(--root <root> --manifest <manifest> --slice builds-owui_acc.slice)

python3 "$kit" preflight "${args[@]}"   # read-only
python3 "$kit" stage     "${args[@]}"   # extract, render, mint, initialize
python3 "$kit" up        "${args[@]}"   # start the kit slice, route closed
python3 "$kit" trial     "${args[@]}"   # the one trial set, then evidence
python3 "$kit" down      "${args[@]}"   # stop the slice
python3 "$kit" teardown  "${args[@]}" --keep-anchor
```

The trial and the rehearsal both pass `--slice builds-owui_acc.slice`, so the
kit units inherit the host's build memory cap from a capped user
`builds.slice`. The kit units are long-running user services, so a
`systemd-run --scope` wrapper around the kit command would not cap them.

- `preflight` checks the manifest pins against the input archives, disk
  headroom, free ports, the served and loaded model ids, and the host tools.
  Its only Lemonade contact is `GET /api/v1/health` and `GET /api/v1/models`.
- `stage` validates the archives (exact set, size, SHA-256, no symlinks),
  extracts them read-only under `<root>/tree/`, renders the derived user units
  and the acceptance overlay from the packaged files, mints synthetic
  credentials, initializes the session-epoch ledger, and places the whisper
  model in Hugging Face cache layout.
- `up` starts Qdrant, Valkey, the reranker relay, Open WebUI, and the peer
  sampler under the kit slice. Caddy stays stopped until commissioning, so
  the route is closed.
- `trial` runs the scenarios below once, in order, and writes the evidence
  JSON.
- `teardown` stops the slice, removes the runtime units, copies the public
  evidence out, and removes the marked root. `--keep-anchor` keeps the
  marker, `kit.json`, `inputs/`, `backups/` (with `backups/anchor/`), and the
  session-epoch `ledger/` (a few hundred MB), so the acceptance re-smoke can
  revive the environment before the production install. `up` on a kept root
  re-extracts the trees, restores the credential store, re-renders `etc/`,
  and restores the state tuple. After a rehearsal, teardown ignores
  `--keep-anchor`.

Exit codes for every subcommand: `0` pass, `1` failure, `2` usage error (an
unknown flag or an invalid flag combination), `3` escalate (zembed canary),
`75` precondition not met (the message names the owner or lead action).

## Scenario map

The trial runs these in order. "Ceiling" limits apply to this first trial
only.

| Id | Requirement | Limit |
| --- | --- | --- |
| `open-webui.acceptance.identity.archives` (A-ID1) | All deployed archives match the manifest by name, size, and SHA-256, before extraction and again at rollback. The generic `ctranslate2` and `python-ctranslate2` 4.8.2 archives are listed as "bound, not deployed"; the host `python-ctranslate2-gfx1151` provides and conflicts. | exact |
| `open-webui.acceptance.identity.unit-properties` (A-ID2) | Every packaged unit property the user manager cannot apply, generated (see below). | record |
| `open-webui.acceptance.ready.first-start` (A-R2) | First fresh start reaches Alembic head `f0bd01a18a3d` with no migration error; UDS `/ready` 200 before commissioning. | head exact; duration recorded |
| `open-webui.acceptance.auth.one-admin` (A-S2) | The packaged `open-webui-commission-admin` succeeds; signup off and exactly one admin, rechecked after both drills. | exact |
| `open-webui.acceptance.ready.restart` (A-R1) | Restart to UDS `/ready` 200 plus authenticated retrieval health 200. | ceiling 25 s |
| `open-webui.acceptance.qdrant.g4` (A-S3, A-S4) | Fresh 1.19 state; five `open-webui-rag-v1` collections, 2,560-dim cosine, payload indexes `tenant_id`, `metadata.hash`, `metadata.file_id`; the runtime holds only the `prw` JWT; the negative probe (an `r` JWT upsert and a `prw` collection create or delete return 403). | exact |
| `open-webui.acceptance.lemonade.no-credential` (A-S5) | Open WebUI holds no credential for its Lemonade connection: five secret credentials plus the session-epoch credential; empty API-key fields in the env, overlay, SQLite config, and admin exports. | exact |
| `open-webui.resmoke.zembed-canary` (A-R3) | 2,560 dims, `\|norm − 1\| ≤ 0.001`, margin ≥ 0.20, prefixes read from the running process's settings; one indexed chunk's stored vector has cosine ≥ 0.999 with the direct content-prefixed vector. | fixed; failure exits 3 and escalates |
| `open-webui.resmoke.zerank-qualification` (A-R4) | Retrieval health 200 after start; a direct rerank gives finite scores with the relevant document first. | pass/fail |
| `open-webui.acceptance.route.caddy-uds` (A-S1) | HTTPS 200 through Caddy to the socket; authenticated WebSocket 101; no Open WebUI TCP listener and no non-loopback listener on the Caddy port. Rechecked after both drills. | exact |
| `open-webui.resmoke.cited-answer` (A-S6) | "The brass key opens the seed cabinet." with exactly one source, named as the fixture's canonical citation, and a finite rerank score. Timings recorded. | pass/fail |
| `open-webui.acceptance.failclosed.reranker-down` (A-F1) | With the relay stopped: chat 200; retrieval, file-attached chat, and health 503 with the fixed detail and no citation. | exact |
| `open-webui.acceptance.failclosed.recovery` (A-F2) | Relay back, latch still 503, RAG config re-saved, then health 200 and a cited answer. | exact |
| `open-webui.resmoke.stt` (A-S7) | `jfk.flac` through local faster-whisper on the CPU (int8): language `en`, both expected phrases, at least 20 ordered words; no `WhisperModel initialization failed` in the journal. | pass/fail |
| `open-webui.acceptance.privacy` (A-P1..P3, A-E2) | A-P1 recorded; peer samples only within the allowed set; the five telemetry values; Haystack absent from the acceptance environment. | pass/fail (A-P1 record) |
| `open-webui.acceptance.drill.restore` (A-D1, A-D3) | One restore, clock from epoch reservation to ready plus the cited fact. | ceiling 40 s |
| `open-webui.acceptance.drill.rollback` (A-D2, A-D3) | Archives match the anchor manifest; state restore timed; total window recorded; never `:8080`: the host's own `open-webui.service` state is unchanged across the drill and no acceptance process listens on `:8080`. | ceiling 40 s state; window recorded |
| `open-webui.acceptance.resources` (A-RES1..3) | `memory.events` `oom_kill` 0, and `NRestarts` 0 in every snapshot for every unit (systemd resets it on each planned start, and a snapshot precedes each one); peak memory, CPU, Qdrant sizes, snapshot and backup sizes, and the cache inventory recorded. | gates: no OOM, no unplanned restart |
| `open-webui.acceptance.evidence` (A-E1, A-E3) | Public-safe evidence with `trial_set_count=1`, one restore, one rollback, and no generation fields. | pass/fail |

Notes on specific checks:

- **Haystack (A-E2)** is scoped to the acceptance environment: no hayhooks or
  Haystack unit among the `owui-acc-*` units, no Haystack module loaded by the Open
  WebUI process, and `hayhooks.service` neither active nor enabled on the
  host. A host package that is installed but disabled is not a failure; its
  removal is optional and belongs to
  [Release retained rollback anchors and clean target-local state](https://github.com/nisavid/arch-pkgs/issues/62).
- **Allowed peers (A-P2)** are the Lemonade origin from `--lemond-url`, the
  reranker relay, acceptance Qdrant, acceptance Valkey, and the service's own
  Unix socket. Any other peer, including a connection attempt to an Ollama or
  hosted OpenAI endpoint, fails the check. The reranker relay and the peer
  sampler exist only to evidence A-F1 and A-P2; they are not new gates.
- **The restore drill (A-D1)** makes a marker change to every tuple member
  after the anchor: it deletes the uploaded file, rewrites the Valkey
  sentinel, and adds a harmless extra credential. It records that the live
  sentinel and credential store differ from the anchor, reserves the next
  session epoch (the clock starts), wipes and restores the whole tuple, and
  stops the clock when the service is ready and returns the cited fact. A
  restore that misses its ceiling is recorded as the drill's failure; the
  rollback drill still runs.
- **The rollback drill (A-D2)** stops the slice, removes `tree/` and all state,
  re-extracts from `inputs/` after a digest check against the anchor manifest,
  reserves the epoch, and restores the tuple into fresh Qdrant 1.19.
- **The A-D3 checks** run before Caddy restarts after each drill: SQLite
  `quick_check` at Alembic head, backup digests, Valkey RDB and a sentinel
  key, collection shape and point counts, the credential tuple's
  fingerprints, the epoch above the recorded bound, a pre-backup session
  rejected with 401, and a fresh login succeeding.

## Deviations and the A-ID2 table

The packaged env bytes stay exact. The derived user unit loads the packaged
`open-webui.env` first and then one overlay, `<root>/etc/acceptance.env`; the
later file wins. The overlay is the only deviation surface, and a test pins
its key set to:

- the `/var/lib/open-webui` state-path keys, rewritten under
  `<root>/state/open-webui`;
- `QDRANT_URI` pointing at acceptance Qdrant on port 16333, because the
  host's current Qdrant holds the packaged port;
- `RAG_EXTERNAL_RERANKER_URL` pointing at the reranker relay on port 13306,
  which forwards bytes unchanged to the provider and lets the trial stop the
  reranker without touching Lemonade;
- any connection-seed key whose packaged value differs from the kit's seed
  (`ENABLE_OLLAMA_API=false`, `OPENAI_API_BASE_URLS=<lemond-url>/api/v1`, and
  an empty `OPENAI_API_KEYS`). Open WebUI 0.11.0-5 packages that seed for the
  default Lemonade origin, so the record overlay carries none of these keys and
  the rehearsal overlay carries only `OPENAI_API_BASE_URLS` for the stub. An
  older package without the seed gets all three.

The local Whisper settings are not overlay keys. The derived unit sets
`WHISPER_MODEL=<whisper-model>` and `HF_HUB_OFFLINE=1` as `Environment=`
lines, recorded as A-ID2 rows, and the production drop-in carries the same
two values.

The seed keys are persistent-config seeds in Open WebUI 0.11: they apply on
first start, and afterwards the database value wins. A rehearsal root holds
stub URLs in its database, so it is never reused or kept as an anchor.

The kit renders each derived unit from the extracted packaged unit. It keeps
`EnvironmentFile`, the credential directives (sources rewritten under
`<root>/credstore`), `Restart`, `RestartSec`, `UMask`, `NoNewPrivileges`, and
`IPAddressDeny`/`IPAddressAllow` (configured, not enforced). For every unit it
sets `HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME`, `TORCH_HOME`, `HF_HOME`,
`TMPDIR`, and the working directory under `<root>`, and sets
`PYTHONDONTWRITEBYTECODE=1`, so no cache, bytecode, or temporary file reaches
`/home` or the shared `/tmp`.

A-ID2 is generated, not hand-written. The kit compares the packaged unit, the
derived unit, and `systemctl --user show`, and writes one row per item with
its packaged value, its acceptance value, and the reason. The table covers:

- the dropped items: `User`, `Group`, `SupplementaryGroups`,
  `ExecStartPre=+`, `StateDirectory`, `RuntimeDirectory`, the
  `Protect*`/`Private*`/`Restrict*`/`SystemCall*` block, `ReadWritePaths`,
  and the enforcement of `IPAddressDeny`/`IPAddressAllow` (with the journal
  warning quoted);
- the rewritten items: working directory, `HOME`, the cache and temporary
  directories, and the credential sources;
- the overlay keys above;
- the session-epoch ledger run under `unshare -r`, the socket path under
  `$XDG_RUNTIME_DIR/owui-acc/`, and Caddy with `tls internal`;
- the credential route: `systemd-creds --user` when it works, otherwise
  0400 files through `LoadCredential=`, recorded as a weaker restore proof;
- the Open WebUI launch mode: the packaged wrapper inside `bwrap` with only
  `/opt/open-webui` shadowed, or, if the rehearsal shows the sampler cannot
  read the namespaced process, the candidate site-packages on `PYTHONPATH`
  with `FRONTEND_BUILD_DIR` in the overlay.

Acceptance Caddy binds loopback only, disables the redirect server and admin
endpoint, uses `tls internal` without installing trust, and keeps all its
storage under `<root>/state/caddy`. Acceptance Valkey runs RDB only
(`appendonly no`), and the drills back up and restore the RDB.

The installed check in the production handoff covers every A-ID2 row.

## Rehearsal (kit debugging only)

The stub rehearsal exists only to catch kit bugs before the one real trial. It
is not a trial and never counts toward the trial set.

```bash
args=(--root <root> --manifest <manifest> --provider stub --rehearsal --slice builds-owui_acc.slice)
python3 "$kit" preflight "${args[@]}"
python3 "$kit" stage     "${args[@]}"
python3 "$kit" up        "${args[@]}"
python3 "$kit" trial     "${args[@]}"
python3 "$kit" down      "${args[@]}"
python3 "$kit" teardown  "${args[@]}"
```

- It runs against `tools/fixtures/open-webui-household-acceptance/stub_provider.py`,
  a credential-free deterministic provider. The sampler allowlist excludes the
  Lemonade origin, so any Lemonade contact fails the rehearsal.
- It may exercise each drill code path once, because the real trial runs only
  once.
- It writes no evidence file and publishes no timings, measurements, or
  comparisons. Its record in the PR description is a bring-up pass or fail
  only.
- Fix Open WebUI 0.11 API-shape mismatches found here before the trial.

The rehearsal cannot prove the zembed semantic margin, real zerank scores, the
real model's verbatim answer, or provider timings. Only the trial does.

## Evidence handling

- The public record is
  `docs/maintainers/evidence/open-webui-household-acceptance-<YYYY-MM-DD>.json`.
  It lands as a follow-up commit on the kit PR, or as a stacked PR if the kit
  has already merged. The ticket closes only when that evidence merges.
- It binds the archive identities, the supporting packages (host pacman
  identity or verified archive), the host provider identities, the
  knowingly-foreign providers of record, the Whisper model and audio pins, the Lemonade version, the
  pre- and post-trial model snapshots, the M4 receipt ids, the canary texts,
  every trial value, the A-ID2 table, and the disposition.
- The kit's public-safety check runs on it before it is written. Ports appear
  only as `loopback:<port>` tokens, loopback ranges as `loopback/<prefix>`, and
  a non-default Lemonade origin as `<lemond>`; the root path, hostnames, and
  addresses never appear.
- The full document is always written first to
  `<root>/evidence/raw/trial-evidence.json` (mode 0600). If the public-safety
  check fails, only the public copy is withheld, and the kit prints the
  private path with the reason, so the one trial's values survive.
- It records `production_expectation`, the frozen production-settings entry
  for the deployed `open-webui` archive, and the trial prints it. The
  evidence commit adds that entry to `PRODUCTION_EXPECTATIONS` in
  `tools/open_webui_household_scenarios.py`; a test ties every entry to
  committed acceptance evidence.
- Every `/proc/<pid>/environ` read is filtered in memory to a fixed key
  allowlist (the five telemetry keys, the embedding prefixes and model, and
  the reranking model). Raw environ is never written anywhere.
- Credential fingerprints stay in private evidence; the public record states
  only `tuple_match: true`.
- Raw journals and sampler output stay under `<root>/evidence/raw/`, are never
  committed, and are removed at teardown.

## Re-smoke (S6)

The four `open-webui.resmoke.*` scenarios are the same functions the trial
runs. arch-strix-halo-pkgs uses them after each later Lemonade redeploy (M6)
and at the generation C activation (W6). The lead records the receipts;
this repository makes no cross-repository writes.

### Frozen ids

The ids are frozen in `tools/open_webui_household_scenarios.py`, and a test
checks them. A behavior change gets a new id and a schema bump, never a
rewritten id. They run in this order:

1. `open-webui.resmoke.zembed-canary`
2. `open-webui.resmoke.zerank-qualification`
3. `open-webui.resmoke.cited-answer`
4. `open-webui.resmoke.stt`

The scenario module uses only the Python standard library, so it runs with
`/usr/bin/python3` and nothing else. Exit codes: `0` all pass, `1` a failure,
`3` escalate (zembed canary), `75` precondition not met.

### Prerequisites

- After the Lemonade redeploy, the arch-strix-halo-pkgs scenarios for the
  service-consumer pins, zembed embeddings, and zerank selected-logit scoring
  have passed on the redeployed provider.
- The expected embedding prefixes and model ids are frozen in the module,
  keyed by the promoted `open-webui` version and bound to its archive
  SHA-256. Entries come only from the acceptance evidence commit; until it
  lands the map is empty and production S6 exits 75. The module checks
  `pacman -Q open-webui` and, when the archive is still cached, its SHA-256;
  the receipt claims the digest only when that check ran, and otherwise
  records the binding as `pacman-version-only`.
- `jfk.flac` is kept outside `/tmp`, and the module verifies its SHA-256
  before use.
- S6 never shares a window with the production cutover.

### Production target

After the production install, S6 runs unprivileged through the household HTTPS
origin with a dedicated non-admin smoke account, if the lead and owner approve
one. Store its credentials once, typed without echo:

```bash
install -d -m 0700 "$HOME/.config/credstore.encrypted"
systemd-ask-password -n "resmoke email" \
  | systemd-creds --user encrypt --name=resmoke-email - \
      "$HOME/.config/credstore.encrypted/open-webui-resmoke.email"
systemd-ask-password -n "resmoke password" \
  | systemd-creds --user encrypt --name=resmoke-password - \
      "$HOME/.config/credstore.encrypted/open-webui-resmoke.password"
```

Then run, from a checkout at the evidence commit (the commit that adds the
trial evidence and its `PRODUCTION_EXPECTATIONS` entry):

```bash
systemd-run --user --pipe --wait --collect \
  -p LoadCredentialEncrypted=resmoke-email:"$HOME/.config/credstore.encrypted/open-webui-resmoke.email" \
  -p LoadCredentialEncrypted=resmoke-password:"$HOME/.config/credstore.encrypted/open-webui-resmoke.password" \
  /usr/bin/python3 <kit-checkout>/tools/open_webui_household_scenarios.py resmoke \
    --target production --origin https://<household-origin> \
    --lemond-url <lemond-url> \
    --audio <retained>/jfk.flac --scenario all --receipt <out>.json
```

Add `--cacert <household-ca>` when the origin's certificate is not in the
system trust store. `--embedding-model`, `--reranking-model`, and
`--whisper-model` default to the frozen values and are passed only to confirm
them. `--chat-model` defaults to the owner-pinned id.

In production each scenario checks:

- zembed: direct embeddings from Lemonade against the canary thresholds;
- zerank: authenticated retrieval health 200, plus a direct rerank with finite
  scores and the relevant document first;
- cited-answer: uploads the fixture handbook into the smoke account's own
  files, runs a file-scoped chat, asserts the sentence, one source, and a
  finite score, then deletes the file;
- stt: one transcription through Open WebUI.

### Acceptance target

Before the production install, or if it is deferred, revive the kept anchor:

```bash
python3 tools/accept_open_webui_household.py up --root <root> --manifest <manifest>
python3 tools/accept_open_webui_household.py resmoke --root <root> --manifest <manifest>
python3 tools/accept_open_webui_household.py down --root <root> --manifest <manifest>
```

The runner's `resmoke` calls the same module against the acceptance Caddy
origin and writes the receipt under `<root>/evidence/`. It runs in record mode
only: a rehearsal root refuses `resmoke` with exit 75, and the module writes
no receipt in rehearsal mode.

### Rules

- **Latch.** If zerank-qualification sees 503 (the gate latched on a fault
  during the redeploy), the run exits 75 with
  `NEEDS OWNER: sudo systemctl restart open-webui.service`. The owner replies
  `HAND-BACK: open-webui restarted`, and S6 runs once more. The smoke account
  is not an admin, so an admin re-save is not used.
- **W6 speech provider.** W6 rebuilds `python-ctranslate2-gfx1151`, and a
  running Open WebUI keeps the old library mapped. The stt scenario exits 75
  with the same restart request unless the service's `ActiveEnterTimestamp`
  is later than the provider's install date.
- **Model ids.** A missing or different served id exits 75 and escalates. The
  module never remaps, except that a canonical `user.` id and its bare name
  are the same model. Open WebUI's chat requests use whichever form Open WebUI
  lists.
- **Receipt.** Schema `open-webui-household-resmoke/v1`, one
  `<id> PASS|FAIL <detail>` line per scenario on stdout, and a JSON receipt
  with the scenario ids and results, the Lemonade version and start time, the
  `open-webui` archive SHA-256 (only when verified) and its binding, the
  model ids, the chat model id, timings, and the exit code. It never contains
  a secret. Every run past argument parsing writes one, including a
  precondition failure (an unreachable Lemonade or Open WebUI exits 75 with a
  receipt) and a malformed response (a FAIL row).

## Ported constants

Each constant below carries its source. For those copied from open pull
requests, a one-line consistency check compares the kit's copies with the
merged values once those pull requests merge.

| Constant | Source |
| --- | --- |
| `tiny` Whisper repository, revision, and `model.bin` SHA-256; `jfk.flac` SHA-256 | [feat(ctranslate2): update to 4.8.2 with speech G0-G2 evidence](https://github.com/nisavid/arch-pkgs/pull/92), commit `e12fdd9` |
| `base` Whisper revision and file SHA-256 values; the other `tiny` file digests | The Hugging Face API, read-only, on 2026-09-23: the revision and `model.bin` LFS SHA-256 from `https://huggingface.co/api/models/Systran/faster-whisper-base?blobs=true`, and the other digests from the files at that revision |
| Collection body, payload indexes, and the HS256 `prw`/`r` JWT mint | [feat(qdrant): add production cutover route and rebind accepted candidates](https://github.com/nisavid/arch-pkgs/pull/93), commit `b99f9bd` |

## Cleanup

`teardown` removes everything the kit created under the marked root and the
runtime units under `$XDG_RUNTIME_DIR/systemd/user`. It never touches the
host's system services, the host's current Open WebUI, Qdrant, Valkey, or
Lemonade. With `--keep-anchor`, only the marker, `kit.json`, `inputs/`,
`backups/`, and `ledger/` remain; if credentials used the 0400-file fallback,
`--keep-anchor` refuses rather than leave plaintext secrets behind.
