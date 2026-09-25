# Open WebUI household acceptance

This is the runbook for
[Acceptance-deploy the Open WebUI household candidate set](https://github.com/nisavid/arch-pkgs/issues/89).
It deploys the exact candidate bytes from
[Build the Open WebUI household candidate set from main](https://github.com/nisavid/arch-pkgs/issues/88)
as user-level services under a disposable root, wires them to the
live-validated Lemonade provider, and runs **one** integrated trial set with
one restore drill and one rollback drill.

The kit is `tools/accept_open_webui_household.py` (evidence schema
`open-webui-household-acceptance/v2`) plus the shared scenario module
`tools/open_webui_household_scenarios.py`. The kit PR alone means *source
updated*. The candidate set is *acceptance deployed* only after the trial's
evidence merges.

## Trial shape

The approved scope of
[Execute the accepted Arch package refresh](https://github.com/nisavid/arch-pkgs/issues/46)
fixes the shape:

- Exactly one integrated trial set: one restore drill and one rollback drill.
  No loops, no repeated runs, no heavy uploads, no sharing scenarios, and no
  vector-generation machinery. The one multi-chunk upload is the generated
  paging corpus of about 0.7 MB (owner decision); see
  [Qdrant paging](#qdrant-paging).
- The numeric limits recorded on
  [Set Open WebUI acceptance limits and create its execution tickets](https://github.com/nisavid/arch-pkgs/issues/70)
  are ceilings for this first trial only. The values the trial records become
  the baseline for
  [Deploy the accepted Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/59).
- The only resource gates are **no OOM kill** and **no unplanned restart**.
  Every other resource value is recorded, not gated.
- Open WebUI's model connections carry no stored secret in this refresh
  (owner decision). The ticket's earlier connection items are superseded;
  the stored-secret check below replaces them.
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
   The trial takes them as `--lemonade-receipt <id>` (repeat the flag for each
   id), and the evidence cites them; record-mode `trial` exits 75 without
   them, before the trial starts. This repository writes nothing to the
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
   | `open-webui-0.11.0-7-x86_64.pkg.tar.zst` | **pending** | **pending** |
   | `python-rapidocr-3.9.2-1-any.pkg.tar.zst` | 27198440 | `0e70fb599a535f9bb1c0c0b3a2f88abe9993f7632eba8e2c618826c7f01bf99b` |

   Open WebUI 0.11.0-7 is the trial candidate. It carries the 0.11.0-6
   `open-webui-tailnet.service` sidecar for the tailnet-only production route
   and adds patch 0008, which pages Open WebUI's Qdrant scroll reads at no
   more than 1000 points per page. Qdrant's strict-mode `max_query_limit`
   stays at 1000 (owner decision), and an Open WebUI build without 0008 fails
   the first handbook upload against it. The 0.11.0-7 size and SHA-256 stay
   **pending** until the candidate is built, merged, and tree-equal;
   `python-rapidocr` is unchanged.

   The candidate store also keeps superseded archives, some under the same
   names (an earlier `open-webui-0.11.0-5` build differs in size and digest),
   so the kit picks the store file whose size and SHA-256 match the manifest
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
6. **Host tools.** `bwrap`, `socat`, `bsdtar`, `unshare`, `systemd-creds`,
   `systemd-run`, `systemctl`, `journalctl`, `ss`, the host `valkey-server`,
   and the host `python-ctranslate2-gfx1151` speech provider (4.7.2 on the
   host today). Preflight refuses when any is missing. A user manager with
   lingering enabled.
7. **A household window.** The trial runs in an announced window that does not
   overlap a Lemonade redeploy. A Lemonade restart during the trial voids the
   run; the lead decides whether one rerun is allowed. The kit detects a
   restart only when Lemonade's `/api/v1/health` reports a start time or
   uptime, and the host's Lemonade reports neither today. The evidence then
   records `restarted: null` and the condition
   `lemonade restart: not detectable from /api/v1/health; the operator's service start times are the record`,
   and `trial` prints a reminder. So the command sequence always reads the
   Lemonade service's state just before `trial` and just after it. Both
   reads must show `LoadState=loaded` and `ActiveState=active`, and the same
   non-empty `ActiveEnterTimestamp`; the operator copies all six lines into
   the description of the PR that carries the evidence.
8. **No concurrent builds.** The trial runs its units under a capped user
   `builds.slice` (see `--slice`), which package builds share. Hold every
   build on the host for the whole trial: a build that fills the shared cap
   could OOM-kill a trial service and fail the no-OOM resources gate
   spuriously.

## Parameters

Every subcommand takes this parameter set; `trial` also takes
`--lemonade-receipt`. Nothing host-specific is committed; the evidence records
each value used.

| Option | Default | Meaning |
| --- | --- | --- |
| `--root DIR` | `/srv/build/arch-pkgs-owui-acceptance` | Disposable acceptance root. It holds a `.owui-acceptance` marker, and teardown deletes only a marked root. |
| `--manifest FILE` | none; required | The candidate manifest of record from the build ticket (name, size, SHA-256, source commit). `trial` refuses with exit 75, before the trial starts, when it is missing or differs from the manifest `stage` used. |
| `--candidate-store DIR` | the operator's arch-pkgs candidate store under the XDG state directory | Where `preflight` and `stage` look for a manifest archive that is not yet under `<root>/inputs/`; the file whose size and SHA-256 match the record is used. |
| `--lemonade-receipt ID` | none; required for a record-mode `trial` | One Lemonade M4 receipt id; repeat it for each id. |
| `--lemond-url URL` | `http://127.0.0.1:13305` | Lemonade base URL. Only `GET /api/v1/health`, `GET /api/v1/models`, and inference requests are sent. In record mode it must be the provider origin of the packaged `open-webui.env` (`RAG_OPENAI_API_BASE_URL` and `RAG_EXTERNAL_RERANKER_URL`); otherwise preflight and every re-entry exit 75. |
| `--chat-model ID` | `user.Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL` (owner-pinned) | The resident chat model used for ordinary chat and the cited answer. Readiness accepts this canonical id or its bare form without the leading `user.`. |
| `--embedding-model ID` | the packaged env's `RAG_EMBEDDING_MODEL` | zembed id that must be served and loaded. |
| `--reranking-model ID` | the packaged env's `RAG_RERANKING_MODEL` | zerank id that must be served and loaded. |
| `--whisper-model NAME` | `base` | Pinned Whisper size, `base` or `tiny`; the revision and every file SHA-256 are recorded. |
| `--provider stub\|lemond` | `lemond` | `stub` serves the rehearsal from `stub_provider.py`; `lemond` is the trial. |
| `--rehearsal` | off | Required with `--provider stub`; marks every output `mode=rehearsal`. |
| `--slice NAME` | `owui-acc.slice` | The user slice every kit unit runs under: a plain systemd slice unit name ending in `.slice`. `stage` records it in `kit.json`, and every later subcommand reads it from there; a later `--slice` that differs from the staged one is refused. systemd nests slices by dashes, so `builds-owui_acc.slice` is a child of `builds.slice`. The slice must be a dedicated child the kit owns alone: `down` and `teardown` stop the whole slice, so a top-level slice with no dash-separated leaf of its own, such as `builds.slice` itself, is refused as a usage error. |

A served model id that differs from the expected one exits 75 and escalates.
The one equivalence is a leading `user.`: a canonical `user.` id and its bare
name name the same model, because Lemonade's listings may show either.
Otherwise the kit never remaps ids; a mismatch means a new candidate or a
lead-approved override.

## Command sequence

Placeholders: `<root>` is the acceptance root (see the prerequisites),
`<manifest>` the candidate manifest of record, `<receipt-id>` a Lemonade M4
receipt id, and `<lemonade-unit>` the Lemonade system service unit
(`lemond.service` from the `lemonade-server` package).
The production placeholders (`<household-origin>`, `<kit-checkout>`, and the
rest) are defined in the
[production handoff](open-webui-household-production-install.md).

Run from a checkout of this repository at the kit commit. Each step is
idempotent up to its own outputs, and each refuses when its precondition does
not hold. `up` may run again before `trial` (after a `down` or a refusal); it
keeps the first start's record.

```bash
kit=tools/accept_open_webui_household.py
args=(--root <root> --manifest <manifest> --slice builds-owui_acc.slice)

python3 "$kit" preflight "${args[@]}"
python3 "$kit" stage     "${args[@]}"
python3 "$kit" up        "${args[@]}"
systemctl show -p LoadState -p ActiveState -p ActiveEnterTimestamp --timestamp=unix <lemonade-unit>
python3 "$kit" trial     "${args[@]}" --lemonade-receipt <receipt-id>
systemctl show -p LoadState -p ActiveState -p ActiveEnterTimestamp --timestamp=unix <lemonade-unit>
python3 "$kit" down      "${args[@]}"
python3 "$kit" teardown  "${args[@]}" --keep-anchor
```

`preflight` is read-only; `stage` extracts, renders, mints, and initializes;
`up` starts the kit slice with the route closed; the two read-only
`systemctl show` lines record Lemonade's state and start time around the
trial; `trial`
runs the one trial set and writes the evidence; `down` stops the slice. After a 0400-file
credential fallback, `teardown` also needs `--keep-plaintext-credentials`.
The command blocks carry no trailing comments, because zsh without
`interactivecomments` would pass them to the kit as arguments.

The trial and the rehearsal both pass `--slice builds-owui_acc.slice`, so the
kit units inherit the host's build memory cap from a capped user
`builds.slice`. So do the transient `systemd-run` units the kit starts for the
credential probe, commissioning, and the resmoke: each one passes the staged
slice. The kit units are long-running user services, so a
`systemd-run --scope` wrapper around the kit command would not cap them.
Never pass `builds.slice` itself: stopping the kit slice would then stop every
other build in it.

The kit sets no `OOMScoreAdjust=` on its units, and they keep the default
`oom_score_adj`. Do not wrap kit commands in `choom`: a host whose build
tooling raises compilers' `oom_score_adj` relies on the default for
long-running services, so a full cap kills a compiler before a trial service.

If `stage` printed that `systemd-creds --user` is unavailable, the root uses
the 0400-file credential fallback, and the record-mode teardown adds
`--keep-plaintext-credentials` to `--keep-anchor` (see `teardown` below).

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
  evidence out, and removes the marked root. In record mode it refuses with
  exit 75, before stopping anything, while
  `<root>/evidence/raw/trial-evidence.json` exists without a public copy:
  move that file out of the root first, because it is then the only copy of
  the trial's values. `--keep-anchor` keeps the
  marker, `kit.json`, `inputs/`, `backups/` (with `backups/anchor/`), and the
  session-epoch `ledger/` (a few hundred MB), so the acceptance re-smoke can
  revive the environment before the production install. `up` on a kept root
  re-extracts the trees, restores the credential store, re-renders `etc/`,
  and restores the state tuple. After a rehearsal, teardown ignores
  `--keep-anchor` and `--keep-plaintext-credentials`.
- On a root that uses the 0400-file fallback, `--keep-anchor` refuses unless
  `--keep-plaintext-credentials` is also given; that flag without
  `--keep-anchor` is a usage error. With both, teardown keeps the anchor's
  credential files as 0400 files in a 0700 directory owned by the operator,
  and `up` restores them in the same fallback mode. The lead ruled that on a
  host where `systemd-creds --user` cannot decrypt, the fallback is a trial
  condition, not a failure. They are test-only secrets for the disposable
  acceptance services, and
  [Release retained rollback anchors and clean target-local state](https://github.com/nisavid/arch-pkgs/issues/62)
  deletes them with the rest of the kept root.

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
| `open-webui.acceptance.connections.no-stored-secret` (A-S5) | Open WebUI's model connections carry no stored secret: the unit loads only Open WebUI's five secret credentials plus the session-epoch credential, and the API-key fields in the env, overlay, SQLite config, and admin exports are empty. | exact |
| `open-webui.resmoke.zembed-canary` (A-R3) | 2,560 dims, `\|norm − 1\| ≤ 0.001`, margin ≥ 0.20, prefixes read from the running process's settings; one indexed chunk's stored vector has cosine ≥ 0.999 with the direct content-prefixed vector. | fixed; failure exits 3 and escalates |
| `open-webui.resmoke.zerank-qualification` (A-R4) | Retrieval health 200 after start; a direct rerank gives finite scores with the relevant document first. | pass/fail |
| `open-webui.acceptance.route.caddy-uds` (A-S1) | HTTPS 200 through Caddy to the socket; authenticated WebSocket 101; no Open WebUI TCP listener and no non-loopback listener on the Caddy port. Rechecked after both drills. | exact |
| `open-webui.resmoke.cited-answer` (A-S6) | "The brass key opens the seed cabinet." with exactly one source, named as the uploaded fixture handbook (`winter-garden-handbook.md`), because Open WebUI names a file source by its upload name, and a finite rerank score. The uploaded handbook is deleted afterwards, and a failed delete fails the scenario. Timings recorded. | pass/fail |
| `open-webui.acceptance.failclosed.reranker-down` (A-F1) | With the relay stopped: chat 200; retrieval, file-attached chat, and health 503 with the fixed detail and no citation. | exact |
| `open-webui.acceptance.failclosed.recovery` (A-F2) | Relay back, latch still 503, RAG config re-saved, then health 200 and a cited answer. | exact |
| `open-webui.resmoke.stt` (A-S7) | `jfk.flac` through local faster-whisper on the CPU (int8): language `en`, both expected phrases, at least 20 ordered words; no `WhisperModel initialization failed` in the journal. | pass/fail |
| `open-webui.acceptance.privacy` (A-P1..P3, A-E2) | A-P1 recorded; peer samples only within the allowed set; the five telemetry values; Haystack absent from the acceptance environment. | pass/fail (A-P1 record) |
| `open-webui.acceptance.drill.restore` (A-D1, A-D3) | One restore, clock from epoch reservation to ready plus the cited fact. | ceiling 40 s |
| `open-webui.acceptance.drill.rollback` (A-D2, A-D3) | Archives match the anchor manifest; state restore timed; total window recorded; never `:8080`: the host's own `open-webui.service` state is unchanged across the drill and no acceptance process listens on `:8080`. | ceiling 40 s state; window recorded |
| `open-webui.acceptance.qdrant.paging` | The generated paging corpus indexes with packaged hybrid search on: its file tenant and a knowledge base built from it each hold exactly 1,100 points, a knowledge-scoped chat returns non-empty sources that include the sentence planted in section 1,050, and a BM25-only query finds the knowledge tenant's first point past one scroll page. The step detail records both measured point counts. The knowledge base and file are deleted afterwards, and a failed delete fails the step; an upload whose processing fails or times out is deleted before the step fails. See [Qdrant paging](#qdrant-paging). | counts exact; timings recorded |
| `open-webui.acceptance.resources` (A-RES1..3) | `memory.events` `oom_kill` 0 for every unit and for the kit slice, whose count is hierarchical and so still covers a unit whose cgroup is gone; an active unit whose count cannot be read fails the gate as unobserved; and `NRestarts` 0 in every snapshot for every unit (systemd resets it on each planned start, and a snapshot precedes each one); peak memory, CPU, Qdrant sizes, snapshot and backup sizes, and the cache inventory recorded. | gates: no OOM, no unplanned restart |
| `open-webui.acceptance.evidence` (A-E1, A-E3) | Public-safe evidence with `trial_set_count=1`, the restore and rollback drills counted from the steps that actually ran (a critical failure that stops the trial first records 0 and fails this step), and no generation fields. | pass/fail |

Between the stored-secret check and the zembed canary, the trial also
records one setup step, `open-webui.acceptance.handbook-indexed`: the fixture handbook
upload that the cited answer and both drills reuse. It is not a separate
requirement.

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
- **The anchor check.** The restore drill checks every anchor member
  against `anchor.json` right after it writes the anchor, before its marker
  change; the rollback drill checks it before it stops or removes anything;
  and `up` checks it before it revives a kept root. The check covers the data
  and credential tree digests (and refuses any symlink in either tree), the
  RDB SHA-256, and each Qdrant snapshot's size and SHA-256. A mismatch fails
  the drill with the live state as the backup left it, and the restore drill
  restarts the services it stopped. The check runs outside the drill
  clocks.
- **The rollback drill (A-D2)** stops the slice, removes `tree/` and all state,
  re-extracts from `inputs/` after a digest check against the anchor manifest,
  reserves the epoch, and restores the tuple into fresh Qdrant 1.19.
- **The A-D3 checks** run before Caddy restarts after each drill: SQLite
  `quick_check` at Alembic head, backup digests, Valkey RDB and a sentinel
  key, collection shape and point counts, the credential tuple's
  fingerprints, the epoch above the recorded bound, a pre-backup session
  rejected with 401, and a fresh login succeeding.

### Qdrant paging

The packaged Qdrant strict mode caps every query and scroll at
`max_query_limit` 1000, and that cap stays (owner decision). Open WebUI 0.11
reads a whole tenant with one scroll whose limit is 999999999, which the cap
rejects; patch 0008 in 0.11.0-7 reads it in pages of at most 1000 points.
Only a tenant with more than 1000 points proves the paging. At or below the
cap, one page returns everything, so a read that stops after one page passes
too. Neither failure is loud: hybrid search logs a failed collection read and
returns no sources, and a one-page read silently drops the rest of the tenant
from its BM25 corpus.

`open-webui.acceptance.qdrant.paging` runs after the rollback drill, so the
drills' anchor, snapshots, and timings never carry its points. It:

1. reads the retrieval config, requires `ENABLE_RAG_HYBRID_SEARCH` to be true
   as packaged, and records the chunking and ranking settings;
2. uploads `household-paging-corpus.md`, which `paging_corpus()` in the kit
   generates on each run: 1,100 Markdown sections of about 650 to 700
   characters (about 0.7 MB), with
   `The copper lantern hangs above the north greenhouse door.` planted in
   section 1,050, and no filler word shared with that sentence or its
   question; the evidence records the corpus size and SHA-256. If processing
   fails or times out, the step deletes the file and fails;
3. counts the file's tenant in `open-webui-rag-v1_files`, which must hold
   exactly 1,100 points, one per section;
4. creates a knowledge base and adds the file. Open WebUI copies the file's
   chunks into the knowledge tenant through one scroll read, so the knowledge
   tenant must also hold exactly 1,100 points; a one-page read copies exactly
   1000;
5. runs a knowledge-scoped chat, whose sources must be non-empty and include
   the planted sentence;
6. reads the knowledge tenant's first point after one 1000-point scroll page,
   with two read-only scrolls, and takes that section's four-digit page
   number, a whitespace token that no other section holds;
7. queries `/api/v1/retrieval/query/collection` for that token with
   `hybrid_bm25_weight` 1, so Open WebUI ranks with BM25 alone, and with `k`
   and `k_reranker` both 3, so the reranker only reorders BM25's results.
   The results must include that section;
8. deletes the knowledge base and the file.

Both counts are exact, read-only Qdrant counts made with the kit's admin
key. Open WebUI stores points without waiting for Qdrant to apply them, so
two equal reads can both be partial: the step polls each count until it
reaches 1,100, and a count still short after 300 s fails the step. The step
detail records both counts, and the evidence records the BM25 query and its
result.

The corpus assumes Open WebUI 0.11's chunking defaults, which the packaged env
does not override: the character splitter, `CHUNK_SIZE` 1000, `CHUNK_OVERLAP`
100, Markdown header splitting on, and `CHUNK_MIN_SIZE_TARGET` 0. Each
section fits in one chunk and no two fit together, so the corpus indexes
as one chunk per section, 1,100 points, with or without header splitting. A
setting that merges or splits sections changes the count and fails the step.

The counts, not the planted sentence's position, prove that the knowledge
copy read every page. Qdrant scrolls in point-id order, and Open WebUI gives
each chunk a random UUID, so section 1,050 is not reliably on a later page.
The chat proves that hybrid retrieval over a tenant past the cap returns
sources, because a failed collection read returns none. It cannot prove that
BM25 read past the first page: Open WebUI 0.11 has no native hybrid search
for Qdrant, so it fuses BM25 with a dense search that queries Qdrant
directly, and the dense branch can return the planted sentence on its own.
The sources do not say which branch found a chunk. The BM25-only query
closes that gap. Its corpus is a separate full read of the knowledge tenant,
and the first point past one scroll page is exactly the point that a read
stopping after one page drops, so BM25 finds it only when that read reaches
the second page.

Runtime and memory: Open WebUI embeds one chunk per request, one request at a
time (`RAG_EMBEDDING_BATCH_SIZE=1`), and it embeds the corpus twice, once for
the file and once for the knowledge base: 2,200 embedding requests. The
expected runtime is about a minute against the stub and a few minutes against
zembed. The hard bounds are 1,200 s for indexing, 1,200 s per request, and
300 s for a count to reach 1,100. The points add about 22 MB of 2,560-dimension
vectors to Qdrant until the step deletes them, and the corpus stays under
1 MB in the kit. The end-of-trial resource snapshot includes this load.

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
  an empty `OPENAI_API_KEYS`). From 0.11.0-5 on, the Open WebUI package carries
  that seed for the default Lemonade origin, so the record overlay carries none
  of these keys and the rehearsal overlay carries only `OPENAI_API_BASE_URLS`
  for the stub. An older package without the seed gets all three.

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
  and the enforcement of `IPAddressDeny`/`IPAddressAllow`, recorded as not
  enforced; the user manager's IP-firewall warning is quoted when the Open
  WebUI unit's current journal holds it, but systemd logs it only once per
  manager lifetime, so it is often absent;
- the rewritten items: working directory, `HOME`, the cache and temporary
  directories, and the credential sources;
- the overlay keys above;
- the session-epoch ledger run under `unshare -r`, the socket path under
  `$XDG_RUNTIME_DIR/owui-acc/`, and Caddy with `tls internal`;
- the credential route: `systemd-creds --user` when it works, otherwise
  0400 files through `LoadCredential=`, recorded as a weaker restore proof.
  The evidence also lists the fallback under `conditions` as
  `credentials: 0400-file fallback; systemd-creds --user unavailable`: a
  trial condition, not a failure;
- the Open WebUI launch mode: the packaged wrapper inside `bwrap` with only
  `/opt/open-webui` shadowed, or, if the rehearsal shows the sampler cannot
  read the namespaced process, the candidate site-packages on `PYTHONPATH`
  with `FRONTEND_BUILD_DIR` in the overlay.

Acceptance Caddy binds loopback only, disables the redirect server and admin
endpoint, uses `tls internal` without installing trust, and keeps all its
storage under `<root>/state/caddy`. Acceptance Valkey runs RDB only
(`appendonly no`), and the drills back up and restore the RDB.

The production handoff does not repeat these rows one by one. Its agent
post-verification proves that the packaged unit is unmodified and that only the two documented
drop-ins apply, so every packaged property that A-ID2 records as dropped or
not enforced here is in force in production.

The 0.11.0-6 `open-webui-tailnet.service` sidecar is not part of the
acceptance environment: the acceptance route is loopback Caddy, and the
sidecar's loopback deny is proven on the host by the owner-run P5.2 check in
the production handoff.

## Rehearsal (kit debugging only)

The stub rehearsal exists only to catch kit bugs before the one real trial. It
is not a trial and never counts toward the trial set.

The rehearsal uses its own root, such as
`/srv/build/arch-pkgs-owui-acceptance-rehearsal`, never the trial's: `stage`
pins the mode, and a rehearsal teardown removes the whole root, including
`inputs/`. Copy the approved inputs into it; do not move them.

```bash
kit=tools/accept_open_webui_household.py
args=(--root <rehearsal-root> --manifest <manifest> --provider stub --rehearsal --slice builds-owui_acc.slice)
python3 "$kit" preflight "${args[@]}"
python3 "$kit" stage     "${args[@]}"
python3 "$kit" up        "${args[@]}"
python3 "$kit" down      "${args[@]}"
python3 "$kit" up        "${args[@]}"
python3 "$kit" trial     "${args[@]}"
python3 "$kit" down      "${args[@]}"
python3 "$kit" teardown  "${args[@]}"
```

The `down` and second `up` before `trial` exercise the repeated-up path the
real trial may need; the second `up` keeps `first-start.json`.

- It runs against `tools/fixtures/open-webui-household-acceptance/stub_provider.py`,
  a deterministic stand-in provider. The sampler allowlist excludes the
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
  every trial value, the A-ID2 table, the trial `conditions` (such as the
  0400-file credential fallback), and the disposition.
- The kit's public-safety check runs on it before it is written. Ports appear
  only as `loopback:<port>` tokens, loopback ranges as `loopback/<prefix>`, and
  a non-default Lemonade origin as `<lemond>`; the root path, hostnames, and
  addresses never appear.
- The full document is always written first to
  `<root>/evidence/raw/trial-evidence.json` (mode 0600). If the public-safety
  check fails, only the public copy is withheld, and the kit prints the
  private path with the reason, so the one trial's values survive. Teardown
  refuses until that file is moved out of the root.
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
origin as the dedicated non-admin smoke account that the owner creates in the
production runbook's
[P5.4](open-webui-household-production-install.md#p54-the-smoke-account).
Its credentials take one of two paths, picked by a probe that encrypts a
value with `systemd-creds --user` and loads it the way the re-smoke does:

```bash
p=$(mktemp -d)
printf probe | systemd-creds --user encrypt --name=probe - "$p/probe.cred" 2>/dev/null
if systemd-run --user --pipe --wait --collect --quiet \
     -p LoadCredentialEncrypted=probe:"$p/probe.cred" \
     sh -c 'cat "$CREDENTIALS_DIRECTORY/probe"' 2>/dev/null | grep -qx probe; then
  echo encrypted
else
  echo 0400-files
fi
rm -r "$p"
```

On a host where user decryption works (`encrypted`), store the credentials
once, typed without echo:

```bash
install -d -m 0700 "$HOME/.config/credstore.encrypted"
systemd-ask-password -n "resmoke email" \
  | systemd-creds --user encrypt --name=resmoke-email - \
      "$HOME/.config/credstore.encrypted/open-webui-resmoke.email"
systemd-ask-password -n "resmoke password" \
  | systemd-creds --user encrypt --name=resmoke-password - \
      "$HOME/.config/credstore.encrypted/open-webui-resmoke.password"
cred=(
  -p LoadCredentialEncrypted=resmoke-email:"$HOME/.config/credstore.encrypted/open-webui-resmoke.email"
  -p LoadCredentialEncrypted=resmoke-password:"$HOME/.config/credstore.encrypted/open-webui-resmoke.password"
)
```

On a host where `systemd-creds --user` cannot decrypt (`0400-files`), for
example where TPM2 unsealing fails, store them as 0400 files in a 0700
directory the operator owns, and load them with `LoadCredential=`:

```bash
install -d -m 0700 "$HOME/.config/credstore"
systemd-ask-password -n "resmoke email" \
  | install -m 0400 /dev/stdin "$HOME/.config/credstore/open-webui-resmoke.email"
systemd-ask-password -n "resmoke password" \
  | install -m 0400 /dev/stdin "$HOME/.config/credstore/open-webui-resmoke.password"
cred=(
  -p LoadCredential=resmoke-email:"$HOME/.config/credstore/open-webui-resmoke.email"
  -p LoadCredential=resmoke-password:"$HOME/.config/credstore/open-webui-resmoke.password"
)
```

Then run, from a checkout at the evidence commit (the commit that adds the
trial evidence and its `PRODUCTION_EXPECTATIONS` entry), in the shell that set
`cred`:

```bash
systemd-run --user --pipe --wait --collect "${cred[@]}" \
  /usr/bin/python3 <kit-checkout>/tools/open_webui_household_scenarios.py resmoke \
    --target production --origin <household-origin> \
    --lemond-url <lemond-url> \
    --audio <retained>/jfk.flac --scenario all --receipt <out>.json
```

`<lemond-url>` is the Lemonade base URL, `<retained>` the directory that
holds the retained `jfk.flac`, and `<out>` the receipt path; give all paths
absolutely, because the transient user service runs in `$HOME`, not in the
current directory. The tailnet origin's certificate is publicly trusted, so
production needs no `--cacert`. `--embedding-model`, `--reranking-model`, and
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
  precondition failure (a missing `--root` or `--origin`, or an unreachable
  Lemonade or Open WebUI, exits 75 with a receipt) and a malformed response (a
  FAIL row). A rehearsal writes none, and a receipt that fails the
  public-safety check is not written: the run exits 1 instead.

## Ported constants

Each constant below carries its source. Both source pull requests have
merged, and the kit's copies equal the values on `main`.

| Constant | Source |
| --- | --- |
| `tiny` Whisper repository, revision, and `model.bin` SHA-256; `jfk.flac` SHA-256 | `docs/maintainers/evidence/speech-providers-4.8.2-1.2.1/g0-g2.json`, from [feat(ctranslate2): update to 4.8.2 with speech G0-G2 evidence](https://github.com/nisavid/arch-pkgs/pull/92) |
| `base` Whisper revision and file SHA-256 values; the other `tiny` file digests | The Hugging Face API, read-only, on 2026-09-23: the revision and `model.bin` LFS SHA-256 from `https://huggingface.co/api/models/Systran/faster-whisper-base?blobs=true`, and the other digests from the files at that revision |
| Collection body, payload indexes, and the HS256 `prw`/`r` JWT mint | `tools/qdrant_production_cutover.zsh`, from [feat(qdrant): add production cutover route and rebind accepted candidates](https://github.com/nisavid/arch-pkgs/pull/93) |

## Cleanup

`teardown` removes everything the kit created under the marked root and the
runtime units under `$XDG_RUNTIME_DIR/systemd/user`. It never touches the
host's system services, the host's current Open WebUI, Qdrant, Valkey, or
Lemonade. With `--keep-anchor`, only the marker, `kit.json`, `inputs/`,
`backups/`, and `ledger/` remain. If credentials used the 0400-file fallback,
`--keep-anchor` refuses rather than leave plaintext secrets behind, unless
`--keep-plaintext-credentials` keeps the test-only 0400 files in the anchor
for the retention cleanup to delete.
