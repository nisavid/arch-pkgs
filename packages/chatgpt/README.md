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

For the first ingest into otherwise-empty checkout-local staging, run the
helper with the retained evidence set, exact record digest, and complete
published repository as the seed:

```zsh
tools/ingest_chatgpt.zsh \
  --artifact /path/to/chatgpt-26.810.52044-1-x86_64.pkg.tar.zst \
  --verification-record /path/to/verification-record.json \
  --record-sha256 b7761927b93f4164cf34c40d5e789d16e8b2b2325a83a9a77565bdcdbd64e923 \
  --source-dir /path/to/chatgpt-linux \
  --seed-repo-dir /srv/pacman/nisavid/x86_64
```

The seed is read while the helper holds the repository-writer lock. Omit
`--seed-repo-dir` on later ingests after checkout-local staging already contains
the complete repository, or to initialize the first repository. A supplied seed
path must already exist as a directory.

The helper first binds the record digest and full accepted tuple to the tracked
baseline, then snapshots the artifact and evidence before parsing them. It
verifies the source, package, manifest, generation-decision, and build-info
tuple. It resolves the package-manifest verifier from the recorded commit
object, so unrelated working-tree files cannot change verification. It then
replaces only the `chatgpt` entry and the recorded legacy `codex-app` and
`codex-desktop` entries in staging, and writes allowlisted public provenance
without local paths.

Verify the staged repository against the tracked baseline before publication.
These checks derive the accepted identity from the repository rather than
repeating a version or digest by hand:

```zsh
set -euo pipefail

baseline=packages/chatgpt/fallback-baseline-2026-08-16.json
repo_dir=repo/x86_64
package_file=$(jq -er '.package.fileName' "$baseline")
package_name=$(jq -er '.package.name' "$baseline")
package_version=$(jq -er '.package.version' "$baseline")
package_path=${repo_dir}/${package_file}
verification_dir=$(mktemp -d)
trap 'rm -rf -- "$verification_dir"' EXIT

[[ "$(sha256sum -- "$package_path" | awk '{print $1}')" == \
  "$(jq -er '.package.sha256' "$baseline")" ]]
[[ "$(bsdtar -tf "${repo_dir}/nisavid.db.tar.zst" | \
  grep -xcF "${package_name}-${package_version}/desc")" == 1 ]]

bsdtar -xOf "$package_path" .PKGINFO >"${verification_dir}/PKGINFO"
[[ "$(sed -n 's/^pkgname = //p' "${verification_dir}/PKGINFO")" == \
  "$package_name" ]]
[[ "$(sed -n 's/^pkgver = //p' "${verification_dir}/PKGINFO")" == \
  "$package_version" ]]
[[ "$(sed -n 's/^arch = //p' "${verification_dir}/PKGINFO")" == \
  "$(jq -er '.package.architecture' "$baseline")" ]]
[[ "$(sed -n 's/^provides = //p' "${verification_dir}/PKGINFO" | sort)" == \
  "$(jq -r '.package.provides[]' "$baseline" | sort)" ]]
[[ "$(sed -n 's/^conflict = //p' "${verification_dir}/PKGINFO" | sort)" == \
  "$(jq -r '.package.conflicts[]' "$baseline" | sort)" ]]
[[ "$(sed -n 's/^replaces = //p' "${verification_dir}/PKGINFO" | sort)" == \
  "$(jq -r '.package.replaces[]' "$baseline" | sort)" ]]

bsdtar -tf "$package_path" | sed 's#^\./##' >"${verification_dir}/archive-list"
for required_path in \
  usr/bin/chatgpt \
  usr/bin/chatgpt-updater \
  usr/lib/systemd/user/chatgpt-updater.service \
  usr/share/applications/chatgpt.desktop \
  usr/share/polkit-1/actions/com.github.nisavid.chatgpt.update.policy \
  opt/chatgpt/start.sh; do
  grep -qxF "$required_path" "${verification_dir}/archive-list"
done

jq -e --slurpfile accepted "$baseline" '
  . as $actual |
  $accepted[0] as $baseline |
  $actual.schemaVersion == 1 and
  $actual.purpose == "retained-fallback-before-official-linux-app-evaluation" and
  ($actual.recordedAt | type == "string" and length > 0) and
  ($actual | keys | sort) == ([
    "generationEvidence", "hostedValidation", "package", "payloadManifest",
    "purpose", "recordedAt", "schemaVersion", "source",
    "verificationRecordSha256"
  ] | sort) and
  $actual.source == $baseline.source and
  $actual.package == $baseline.package and
  ($actual.payloadManifest | {fileName, fileSha256, manifestSha256, entryCount}) ==
    $baseline.payloadManifest and
  $actual.verificationRecordSha256 == $baseline.verification.recordSha256 and
  $actual.generationEvidence.acceptanceVerdict == $baseline.verification.acceptanceVerdict and
  $actual.generationEvidence.blockerCount == $baseline.verification.blockerCount and
  $actual.generationEvidence.inconclusiveReasonCount == $baseline.verification.inconclusiveReasonCount and
  $actual.generationEvidence.optionalWarningCount == $baseline.verification.optionalWarningCount and
  $actual.generationEvidence.decisionFileSha256 == $baseline.verification.generationDecisionSha256 and
  $actual.generationEvidence.buildInfoFileSha256 == $baseline.verification.buildInfoSha256 and
  $actual.hostedValidation.headSha == $baseline.hostedValidation.headSha and
  $actual.hostedValidation.repositoryActionsQuiescent ==
    $baseline.hostedValidation.repositoryActionsQuiescent and
  ($baseline.hostedValidation.runs | all(. as $required |
    $actual.hostedValidation.runs | any(. == $required))) and
  ($baseline.hostedValidation.requiredJobs | all(. as $required |
    $actual.hostedValidation.requiredJobs | any(. == $required))) and
  ([$actual | .. | strings | select(test("^(file://)?/"))] | length == 0)
' "${repo_dir}/chatgpt.provenance.json" >/dev/null
```

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

The package transaction replaces an installed `codex-app` producer and
supersedes the legacy `codex-desktop` virtual identity. Keep
`chatgpt-updater.service` masked through installed and interactive acceptance.
After acceptance, run the following only in the one designated
updater-authority user's session; leave it masked and inactive for every other
user:

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
