# chatgpt

`chatgpt` is the pacman package produced by
[ChatGPT for Linux](https://github.com/nisavid/chatgpt-linux), an unofficial
Linux adaptation of OpenAI's ChatGPT desktop app. This repository ingests the
already verified native package; it does not rebuild or repackage it.

The accepted fallback is `chatgpt 26.810.52044-1` from annotated tag
[`fallback-baseline-2026-08-16`](https://github.com/nisavid/chatgpt-linux/tree/fallback-baseline-2026-08-16).
Its public, path-free provenance tuple is recorded in
[`fallback-baseline-2026-08-16.json`](fallback-baseline-2026-08-16.json).

## Maintenance baseline

- `authoritative_reference`: the exact tagged package output and provenance
  tooling in [`nisavid/chatgpt-linux`](https://github.com/nisavid/chatgpt-linux/tree/dd3d1397f544752ea1170af8393cd59379373f52).
- `advisory_references`: CachyOS
  [`chatgpt-desktop-bin`](https://github.com/CachyOS/cachyos-aur-derived/blob/e6b07823a7842b688e1b3247162a161db2b8d3e3/chatgpt-desktop-bin/PKGBUILD)
  is the later official-app evaluation candidate, not an input to this package.
- `divergence_notes`: this is an exact artifact-ingest lane with no local
  `PKGBUILD`. The retained fallback includes `chatgpt-updater`, replaces and
  conflicts with the former `codex-app` and `codex-desktop` identities, and
  is accepted by immutable digests rather than a package signature or version.
- `update_notes`: require an explicit artifact, verification record, record
  SHA-256, annotated source tag, and source checkout containing the recorded Git
  objects. Recompute the package stream manifest, stage transactionally, and
  verify the repository-served digest before installation. Never select by
  filesystem time or rebuild merely because the version matches.

## Ingest

Run the helper with the retained evidence set and exact record digest:

```zsh
tools/ingest_chatgpt.zsh \
  --artifact /path/to/chatgpt-26.810.52044-1-x86_64.pkg.tar.zst \
  --verification-record /path/to/verification-record.json \
  --record-sha256 b7761927b93f4164cf34c40d5e789d16e8b2b2325a83a9a77565bdcdbd64e923 \
  --source-dir /path/to/chatgpt-linux
```

The helper first binds the record digest and full accepted tuple to the tracked
baseline, then snapshots the artifact and evidence before parsing them. It
verifies the source, package, manifest, generation-decision, and build-info
tuple. It resolves the package-manifest verifier from the recorded commit
object, so unrelated working-tree files cannot change verification. It then
replaces only the `chatgpt` entry and the recorded legacy `codex-app` and
`codex-desktop` entries in staging, and writes allowlisted public provenance
without local paths.

## Install and updater boundary

Close ChatGPT before the package transaction. In every active user's own
session, stop and mask both updater identities before installing; the package
hook otherwise attempts to enable and start the canonical updater:

```zsh
systemctl --user stop codex-app-updater.service chatgpt-updater.service
systemctl --user mask codex-app-updater.service chatgpt-updater.service
systemctl --user is-active codex-app-updater.service chatgpt-updater.service
systemctl --user is-enabled codex-app-updater.service chatgpt-updater.service
```

Both services must report inactive, and the canonical service must report
masked. Publish the complete staging repository through the local-repository
workflow, verify the published package SHA-256, then install through pacman:

```zsh
sudo pacman -Syu chatgpt
```

The package transaction replaces `codex-app`. Keep `chatgpt-updater.service`
masked through installed and interactive acceptance. After acceptance, run the
following only in the one designated updater-authority user's session; leave it
masked and inactive for every other user:

```zsh
systemctl --user unmask chatgpt-updater.service
systemctl --user enable --now chatgpt-updater.service
systemctl --user is-enabled chatgpt-updater.service
systemctl --user is-active chatgpt-updater.service
```

Preserve the shared profile and independently installed global `codex` CLI.

The exact accepted artifact remains retained outside pacman's cache until the
separate fallback-sunsetting decision. The later `chatgpt-desktop-bin`
evaluation must not begin until this fallback has passed installed acceptance.
