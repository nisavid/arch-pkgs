#!/usr/bin/env zsh

emulate -L zsh
setopt errexit nounset pipefail extendedglob

script_dir=${0:A:h}
script_name=${0:t}
repo_root=${script_dir:h}
artifact=
verification_record=
record_sha256=
source_dir=${CHATGPT_LINUX_DIR:-${repo_root}/upstream/chatgpt-linux}
repo_dir=${repo_root}/repo/x86_64
repo_name=nisavid
seed_repo_dir=
dry_run=0
accepted_baseline=${repo_root}/packages/chatgpt/fallback-baseline-2026-08-16.json
test_signal_after_backup=${ARCH_PKGS_INGEST_TEST_SIGNAL_AFTER_BACKUP:-0}
test_signal_during_lock=${ARCH_PKGS_INGEST_TEST_SIGNAL_DURING_LOCK_ACQUISITION:-0}
[[ "$test_signal_after_backup" == 0 || "$test_signal_after_backup" == 1 ]] \
  || { print -u2 -- "ARCH_PKGS_INGEST_TEST_SIGNAL_AFTER_BACKUP must be 0 or 1"; exit 2; }
[[ "$test_signal_during_lock" == 0 || "$test_signal_during_lock" == 1 ]] \
  || { print -u2 -- "ARCH_PKGS_INGEST_TEST_SIGNAL_DURING_LOCK_ACQUISITION must be 0 or 1"; exit 2; }

usage() {
  cat <<EOF
Usage: ${script_name} --artifact FILE --verification-record FILE \\
  --record-sha256 SHA256 [--source-dir DIR] [--repo-dir DIR] \\
  [--repo-name NAME] [--seed-repo-dir DIR] [--dry-run]

Verify and stage one immutable chatgpt-linux fallback package. The artifact,
verification record, record digest, and annotated source tag must agree exactly.
This helper never selects by version, clones a checkout, or rebuilds a package.
EOF
}

die() {
  print -ru2 -- "$*"
  exit 2
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

require_reflink_cp() {
  cp --help 2>/dev/null | grep -q -- '--reflink' \
    || die "ingest requires cp with --reflink support"
}

validate_seed_repo_dir() {
  [[ "$seed_repo_dir" != "/" ]] || die "seed repo directory must not be /"
  [[ ! -L "$seed_repo_dir" ]] \
    || die "seed repo directory must not be a symlink: $seed_repo_dir"
  [[ ! -e "$seed_repo_dir" || -d "$seed_repo_dir" ]] \
    || die "seed repo directory target exists and is not a directory: $seed_repo_dir"
}

require_sha256() {
  local value=$1 label=$2
  (( ${#value} == 64 )) && [[ "$value" == [0-9a-f]## ]] \
    || die "$label is not a lowercase SHA-256 digest: $value"
}

require_git_oid() {
  local value=$1 label=$2
  (( ${#value} == 40 || ${#value} == 64 )) && [[ "$value" == [0-9a-f]## ]] \
    || die "$label is not a full lowercase Git object ID: $value"
}

json_string() {
  local query=$1 label=$2 value
  value=$(jq -er "${query} | select(type == \"string\" and length > 0)" \
    "$verification_record" 2>/dev/null) \
    || die "verification record is missing $label"
  print -r -- "$value"
}

sha256_file() {
  sha256sum -- "$1" | awk '{print $1}'
}

normalize_repository_url() {
  local value=$1
  value=${value%/}
  value=${value%.git}
  print -r -- "$value"
}

metadata_values() {
  local metadata_file=$1 key=$2
  sed -n "s/^${key} = //p" "$metadata_file"
}

verify_support_file() {
  local file_name=$1 expected_sha256=$2 label=$3 support_source support_path
  [[ "$file_name" == "${file_name:t}" && "$file_name" != "." && "$file_name" != ".." ]] \
    || die "$label file name must be a safe basename: $file_name"
  require_sha256 "$expected_sha256" "$label SHA-256"
  support_source=${evidence_dir}/${file_name}
  support_path=${support_snapshot_dir}/${file_name}
  [[ -f "$support_source" && ! -L "$support_source" ]] \
    || die "missing $label file: $file_name"
  cp --reflink=auto -- "$support_source" "$support_path"
  [[ "$(sha256_file "$support_path")" == "$expected_sha256" ]] \
    || die "$label file SHA-256 does not match the verification record"
  print -r -- "$support_path"
}

package_name_from_archive() {
  local archive=$1
  bsdtar -xOf "$archive" .PKGINFO 2>/dev/null \
    | sed -n 's/^pkgname = //p' \
    | sed -n '1p'
}

repo_database_package_names() {
  local database=$1 description_entry
  for description_entry in ${(f)"$(bsdtar -tf "$database" | sed -n 's#/desc$#/desc#p')"}; do
    bsdtar -xOf "$database" "$description_entry" 2>/dev/null \
      | awk '/^%NAME%$/ { getline; print; exit }'
  done
}

while (( $# )); do
  case "$1" in
    --artifact)
      (( $# >= 2 )) || die "--artifact requires a value"
      artifact=${2:A}
      shift 2
      ;;
    --verification-record)
      (( $# >= 2 )) || die "--verification-record requires a value"
      verification_record=${2:A}
      shift 2
      ;;
    --record-sha256)
      (( $# >= 2 )) || die "--record-sha256 requires a value"
      record_sha256=$2
      shift 2
      ;;
    --source-dir)
      (( $# >= 2 )) || die "--source-dir requires a value"
      source_dir=${2:A}
      shift 2
      ;;
    --repo-dir)
      (( $# >= 2 )) || die "--repo-dir requires a value"
      repo_dir=${2:A}
      shift 2
      ;;
    --repo-name)
      (( $# >= 2 )) || die "--repo-name requires a value"
      repo_name=$2
      shift 2
      ;;
    --seed-repo-dir)
      (( $# >= 2 )) || die "--seed-repo-dir requires a value"
      seed_repo_dir=${2:a}
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

(( ! test_signal_after_backup && ! test_signal_during_lock )) \
  || [[ "$repo_dir" == /tmp/* ]] \
  || die "ingest interruption injection is restricted to repository directories under /tmp"

for command_name in awk bsdtar cp env git grep install jq mkdir mktemp mv python3 \
  repo-add repo-remove rm rmdir sed sha256sum sort stat zstd; do
  need_command "$command_name"
done
require_reflink_cp

[[ -n "$artifact" ]] || die "--artifact is required"
[[ -n "$verification_record" ]] || die "--verification-record is required"
[[ -n "$record_sha256" ]] || die "--record-sha256 is required"
[[ -f "$accepted_baseline" && ! -L "$accepted_baseline" ]] \
  || die "tracked ChatGPT acceptance baseline is missing: $accepted_baseline"
[[ -f "$artifact" && ! -L "$artifact" ]] || die "artifact is not a regular file: $artifact"
[[ -f "$verification_record" && ! -L "$verification_record" ]] \
  || die "verification record is not a regular file: $verification_record"
[[ -d "$source_dir" ]] || die "source checkout is missing: $source_dir"
git -C "$source_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "source directory is not a Git checkout: $source_dir"
[[ "$repo_name" =~ '^[A-Za-z0-9._-]+$' ]] \
  || die "repo name contains unsupported characters: $repo_name"
[[ "$repo_name" != "." && "$repo_name" != ".." ]] \
  || die "repo name must not be a path segment"
[[ "$repo_dir" != "/" && "${repo_dir:t}" != "." && "${repo_dir:t}" != ".." ]] \
  || die "unsafe repo directory: $repo_dir"
[[ ! -L "$repo_dir" ]] || die "repo directory must not be a symlink: $repo_dir"
[[ ! -e "$repo_dir" || -d "$repo_dir" ]] \
  || die "repo directory target exists and is not a directory: $repo_dir"
[[ -z "$seed_repo_dir" ]] || validate_seed_repo_dir

require_sha256 "$record_sha256" "verification record SHA-256"
accepted_record_sha256=$(jq -er '.verification.recordSha256' "$accepted_baseline") \
  || die "tracked ChatGPT acceptance baseline has no verification record digest"
[[ "$record_sha256" == "$accepted_record_sha256" ]] \
  || die "verification record digest does not match the tracked accepted baseline"

typeset -a temporary_paths
backup_dir=
signal_deferral=0
pending_signal=0
cleanup_temporary_paths() {
  local exit_status=$?
  local temporary_path

  if [[ -n "$backup_dir" && -e "$backup_dir" && ! -e "$repo_dir" ]]; then
    mv -- "$backup_dir" "$repo_dir" >/dev/null 2>&1 || true
  fi
  for temporary_path in "${temporary_paths[@]}"; do
    if [[ -n "$temporary_path" && -e "$temporary_path" ]]; then
      rm -rf -- "$temporary_path"
    fi
  done
  return $exit_status
}
handle_signal() {
  local signal_status=$1

  if (( signal_deferral )); then
    (( pending_signal )) || pending_signal=$signal_status
    return 0
  fi
  exit $signal_status
}
finish_signal_deferral() {
  local signal_status

  signal_deferral=0
  if (( pending_signal )); then
    signal_status=$pending_signal
    pending_signal=0
    exit $signal_status
  fi
}
trap cleanup_temporary_paths EXIT
trap 'handle_signal 129' HUP
trap 'handle_signal 130' INT
trap 'handle_signal 143' TERM

evidence_dir=${verification_record:h}
verification_temp=$(mktemp -d)
temporary_paths+=("$verification_temp")
support_snapshot_dir=${verification_temp}/support
mkdir -- "$support_snapshot_dir"
record_snapshot=${verification_temp}/verification-record.json
artifact_snapshot=${verification_temp}/${artifact:t}
baseline_snapshot=${verification_temp}/accepted-baseline.json
cp --reflink=auto -- "$verification_record" "$record_snapshot"
cp --reflink=auto -- "$artifact" "$artifact_snapshot"
cp -- "$accepted_baseline" "$baseline_snapshot"
verification_record=$record_snapshot
artifact=$artifact_snapshot
accepted_baseline=$baseline_snapshot

[[ "$(sha256_file "$verification_record")" == "$record_sha256" ]] \
  || die "verification record SHA-256 does not match --record-sha256"

jq -e --slurpfile accepted "$accepted_baseline" '
  .schemaVersion == 1 and
  .purpose == "retained-fallback-before-official-linux-app-evaluation" and
  .source == $accepted[0].source and
  .package == $accepted[0].package and
  (.payloadManifest | {fileName, fileSha256, manifestSha256, entryCount}) ==
    $accepted[0].payloadManifest and
  .generationEvidence.acceptanceVerdict == $accepted[0].verification.acceptanceVerdict and
  .generationEvidence.blockerCount == $accepted[0].verification.blockerCount and
  .generationEvidence.inconclusiveReasonCount == $accepted[0].verification.inconclusiveReasonCount and
  .generationEvidence.optionalWarningCount == $accepted[0].verification.optionalWarningCount and
  .generationEvidence.decisionFileSha256 == $accepted[0].verification.generationDecisionSha256 and
  .generationEvidence.buildInfoFileSha256 == $accepted[0].verification.buildInfoSha256
' "$verification_record" >/dev/null \
  || die "verification record does not match the tracked accepted fallback tuple"

typeset -a sanitized_environment=(env)
for environment_entry in "${(@0)$(env -0)}"; do
  environment_key=${environment_entry%%=*}
  if [[ "$environment_key" == BASH_FUNC_*%% ]]; then
    sanitized_environment+=(-u "$environment_key")
  fi
done
for exported_function_key in ${(f)"$(jq -r '.generationEvidence.sanitizedExportedFunctionKeys[]? // empty' "$verification_record")"}; do
  [[ "$exported_function_key" =~ '^BASH_FUNC_[A-Za-z0-9_]+%%$' ]] \
    || die "verification record contains an unsafe exported-function key"
  sanitized_environment+=(-u "$exported_function_key")
done

source_repository=$(json_string '.source.repository' 'source.repository')
source_commit=$(json_string '.source.commit' 'source.commit')
source_tag=$(json_string '.source.tag' 'source.tag')
source_tag_object=$(json_string '.source.tagObject' 'source.tagObject')
source_tag_target=$(json_string '.source.tagTarget' 'source.tagTarget')
package_file_name=$(json_string '.package.fileName' 'package.fileName')
package_name=$(json_string '.package.name' 'package.name')
package_version=$(json_string '.package.version' 'package.version')
package_architecture=$(json_string '.package.architecture' 'package.architecture')
package_sha256=$(json_string '.package.sha256' 'package.sha256')
manifest_file_name=$(json_string '.payloadManifest.fileName' 'payloadManifest.fileName')
manifest_file_sha256=$(json_string '.payloadManifest.fileSha256' 'payloadManifest.fileSha256')
manifest_sha256=$(json_string '.payloadManifest.manifestSha256' 'payloadManifest.manifestSha256')
decision_file_name=$(json_string '.generationEvidence.decisionFile' 'generationEvidence.decisionFile')
decision_file_sha256=$(json_string '.generationEvidence.decisionFileSha256' 'generationEvidence.decisionFileSha256')
build_info_file_name=$(json_string '.generationEvidence.buildInfoFile' 'generationEvidence.buildInfoFile')
build_info_file_sha256=$(json_string '.generationEvidence.buildInfoFileSha256' 'generationEvidence.buildInfoFileSha256')
package_size=$(jq -er '.package.sizeBytes | select(type == "number" and . > 0 and floor == .)' "$verification_record") \
  || die "verification record has an invalid package size"
manifest_size=$(jq -er '.payloadManifest.sizeBytes | select(type == "number" and . > 0 and floor == .)' "$verification_record") \
  || die "verification record has an invalid payload manifest size"
manifest_entry_count=$(jq -er '.payloadManifest.entryCount | select(type == "number" and . > 0 and floor == .)' "$verification_record") \
  || die "verification record has an invalid payload entry count"

for object_label in \
  "${source_commit}:source commit" \
  "${source_tag_object}:source tag object" \
  "${source_tag_target}:source tag target"; do
  value=${object_label%%:*}
  label=${object_label#*:}
  require_git_oid "$value" "$label"
done
for digest_label in \
  "${package_sha256}:package SHA-256" \
  "${manifest_file_sha256}:payload manifest file SHA-256" \
  "${manifest_sha256}:payload manifest SHA-256"; do
  value=${digest_label%%:*}
  label=${digest_label#*:}
  require_sha256 "$value" "$label"
done
[[ "$source_tag_target" == "$source_commit" ]] \
  || die "source tag target does not match the recorded source commit"
[[ "$package_name" == chatgpt ]] || die "expected package name chatgpt, got: $package_name"
[[ "$package_architecture" == x86_64 ]] \
  || die "expected package architecture x86_64, got: $package_architecture"
[[ "$package_file_name" == "${artifact:t}" ]] \
  || die "artifact filename does not match the verification record"
[[ "$package_file_name" == "${package_file_name:t}" ]] \
  || die "recorded package filename must be a basename"
[[ "$(stat -c %s -- "$artifact")" == "$package_size" ]] \
  || die "artifact size does not match the verification record"
[[ "$(sha256_file "$artifact")" == "$package_sha256" ]] \
  || die "artifact SHA-256 does not match the verification record"

source_origin=$(git -C "$source_dir" remote get-url origin 2>/dev/null) \
  || die "source checkout has no origin remote"
[[ "$(normalize_repository_url "$source_repository")" == \
   "https://github.com/nisavid/chatgpt-linux" ]] \
  || die "verification record source is not the canonical chatgpt-linux repository"
[[ "$(normalize_repository_url "$source_origin")" == \
   "$(normalize_repository_url "$source_repository")" ]] \
  || die "source origin does not match the verification record"
git check-ref-format "refs/tags/${source_tag}" >/dev/null 2>&1 \
  || die "verification record contains an invalid source tag"
[[ "$(git -C "$source_dir" cat-file -t "$source_tag_object" 2>/dev/null)" == tag ]] \
  || die "recorded source tag object is not an annotated tag"
[[ "$(git -C "$source_dir" rev-parse "refs/tags/${source_tag}" 2>/dev/null)" == \
   "$source_tag_object" ]] \
  || die "source tag ref does not match the recorded tag object"
[[ "$(git -C "$source_dir" rev-parse "${source_tag}^{commit}" 2>/dev/null)" == \
   "$source_commit" ]] \
  || die "annotated source tag does not peel to the recorded commit"

pkginfo_file=${verification_temp}/PKGINFO
archive_list=${verification_temp}/archive-list
actual_manifest=${verification_temp}/actual-manifest.json
tagged_verifier=${verification_temp}/package-provenance.py
public_provenance=${verification_temp}/chatgpt.provenance.json

bsdtar -xOf "$artifact" .PKGINFO >"$pkginfo_file" \
  || die "could not read .PKGINFO from the artifact"
[[ "$(metadata_values "$pkginfo_file" pkgname)" == "$package_name" ]] \
  || die "artifact package name does not match the verification record"
[[ "$(metadata_values "$pkginfo_file" pkgver)" == "$package_version" ]] \
  || die "artifact package version does not match the verification record"
[[ "$(metadata_values "$pkginfo_file" arch)" == "$package_architecture" ]] \
  || die "artifact architecture does not match the verification record"
expected_legacy_names=$'codex-app\ncodex-desktop'
for metadata_key in provides conflict replaces; do
  [[ "$(metadata_values "$pkginfo_file" "$metadata_key" | sort)" == "$expected_legacy_names" ]] \
    || die "artifact $metadata_key metadata does not match the accepted replacement contract"
done

bsdtar -tf "$artifact" | sed 's#^\./##' >"$archive_list"
for required_path in \
  usr/bin/chatgpt \
  usr/bin/chatgpt-updater \
  usr/lib/systemd/user/chatgpt-updater.service \
  usr/share/applications/chatgpt.desktop \
  opt/chatgpt/start.sh; do
  grep -qxF "$required_path" "$archive_list" \
    || die "artifact is missing required payload: $required_path"
done

manifest_path=$(verify_support_file "$manifest_file_name" "$manifest_file_sha256" "payload manifest")
decision_path=$(verify_support_file "$decision_file_name" "$decision_file_sha256" "generation decision")
build_info_path=$(verify_support_file "$build_info_file_name" "$build_info_file_sha256" "build info")
[[ "$(stat -c %s -- "$manifest_path")" == "$manifest_size" ]] \
  || die "payload manifest size does not match the verification record"
[[ "$(jq -er '.manifestSha256' "$manifest_path")" == "$manifest_sha256" ]] \
  || die "payload manifest digest does not match the verification record"
[[ "$(jq -er '.entries | length' "$manifest_path")" == "$manifest_entry_count" ]] \
  || die "payload manifest entry count does not match the verification record"
[[ "$(jq -er '.source.commit' "$build_info_path")" == "$source_commit" ]] \
  || die "build info does not bind the recorded source commit"

git -C "$source_dir" show "${source_commit}:scripts/lib/package-provenance.py" \
  >"$tagged_verifier" \
  || die "could not resolve the package provenance verifier from the tagged source commit"
zstd -dc -- "$artifact" \
  | python3 "$tagged_verifier" tar-manifest "$actual_manifest"
python3 "$tagged_verifier" compare "$manifest_path" "$actual_manifest"

python3 - "$verification_record" "$record_sha256" >"$public_provenance" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    record = json.load(source)

public = {
    "schemaVersion": 1,
    "purpose": record["purpose"],
    "recordedAt": record["recordedAt"],
    "source": {
        key: record["source"][key]
        for key in ("repository", "commit", "tag", "tagObject", "tagTarget")
    },
    "package": {
        key: record["package"][key]
        for key in (
            "fileName",
            "name",
            "version",
            "architecture",
            "sizeBytes",
            "sha256",
            "updaterIncluded",
            "provides",
            "conflicts",
            "replaces",
        )
    },
    "payloadManifest": {
        key: record["payloadManifest"][key]
        for key in (
            "fileName",
            "sizeBytes",
            "fileSha256",
            "manifestSha256",
            "entryCount",
        )
    },
    "generationEvidence": {
        key: record["generationEvidence"][key]
        for key in (
            "acceptanceVerdict",
            "blockerCount",
            "inconclusiveReasonCount",
            "optionalWarningCount",
            "decisionFileSha256",
            "buildInfoFileSha256",
        )
        if key in record["generationEvidence"]
    },
    "hostedValidation": {
        "headSha": record.get("hostedValidation", {}).get("headSha"),
        "repositoryActionsQuiescent": record.get("hostedValidation", {}).get(
            "repositoryActionsQuiescent"
        ),
        "runs": [
            {
                key: run[key]
                for key in ("name", "id", "conclusion", "url")
                if key in run
            }
            for run in record.get("hostedValidation", {}).get("runs", [])
        ],
        "requiredJobs": [
            {
                key: job[key]
                for key in ("name", "id", "conclusion", "url")
                if key in job
            }
            for job in record.get("hostedValidation", {}).get("requiredJobs", [])
        ],
    },
    "verificationRecordSha256": sys.argv[2],
}
print(json.dumps(public, indent=2, sort_keys=True))
PY

if (( dry_run )); then
  print -- "Verified exact ChatGPT fallback without staging: ${artifact:t}"
  print -- "Package SHA-256: $package_sha256"
  print -- "Source commit: $source_commit"
  print -- "Source tag object: $source_tag_object"
  exit 0
fi

repo_parent=${repo_dir:h}
repo_leaf=${repo_dir:t}
mkdir -p -- "$repo_parent"
lock_dir=${repo_dir}.writer.lock
lock_acquired=0
signal_deferral=1
if mkdir -- "$lock_dir" 2>/dev/null; then
  lock_acquired=1
fi
if (( lock_acquired && test_signal_during_lock )); then
  kill -TERM $$
fi
(( lock_acquired )) && temporary_paths+=("$lock_dir")
finish_signal_deferral
(( lock_acquired )) \
  || die "another repository writer appears to be active: $lock_dir"
[[ -z "$seed_repo_dir" ]] || validate_seed_repo_dir
stage_dir=$(mktemp -d "${repo_parent}/.${repo_leaf}.ingest.XXXXXX")
temporary_paths+=("$stage_dir")

if [[ -d "$repo_dir" ]]; then
  if [[ -n "$seed_repo_dir" ]]; then
    for existing_entry in "$repo_dir"/*(DN); do
      [[ "${existing_entry:t}" == .gitignore ]] \
        || die "staging is not empty; --seed-repo-dir refuses to replace it: $repo_dir"
    done
  fi
  cp -a -- "$repo_dir"/. "$stage_dir"/
fi
if [[ -n "$seed_repo_dir" && -d "$seed_repo_dir" ]]; then
  [[ -f "${seed_repo_dir}/${repo_name}.db.tar.zst" ]] \
    || die "seed repo is missing ${repo_name}.db.tar.zst: $seed_repo_dir"
  cp -a -- "$seed_repo_dir"/. "$stage_dir"/
fi

repo_db=${stage_dir}/${repo_name}.db.tar.zst
typeset -a replaced_package_names=(chatgpt)
replaced_package_names+=(${(f)"$(jq -r '.package.replaces[]' "$verification_record")"})
if [[ -e "$repo_db" ]]; then
  for replaced_name in "${replaced_package_names[@]}"; do
    "${sanitized_environment[@]}" repo-remove "$repo_db" "$replaced_name" >/dev/null 2>&1 || true
  done
  typeset -a remaining_database_names
  remaining_database_names=(${(f)"$(repo_database_package_names "$repo_db")"})
  for replaced_name in "${replaced_package_names[@]}"; do
    (( ! ${remaining_database_names[(Ie)$replaced_name]} )) \
      || die "repository database still contains replaced package: $replaced_name"
  done
fi

for existing_archive in "$stage_dir"/*.pkg.tar.*(N); do
  [[ "$existing_archive" != *.sig ]] || continue
  existing_name=$(package_name_from_archive "$existing_archive" || true)
  [[ -n "$existing_name" ]] || continue
  if (( ${replaced_package_names[(Ie)$existing_name]} )); then
    rm -f -- "$existing_archive" "${existing_archive}.sig"
  fi
done

staged_artifact=${stage_dir}/${package_file_name}
install -m 0644 -- "$artifact" "$staged_artifact"
install -m 0644 -- "$public_provenance" "${stage_dir}/chatgpt.provenance.json"
[[ "$(sha256_file "$staged_artifact")" == "$package_sha256" ]] \
  || die "staged artifact SHA-256 changed during copy"
"${sanitized_environment[@]}" repo-add "$repo_db" "$staged_artifact" >/dev/null

backup_dir=
if [[ -e "$repo_dir" ]]; then
  backup_dir=$(mktemp -d "${repo_parent}/.${repo_leaf}.previous.XXXXXX")
  rmdir -- "$backup_dir"
  mv -- "$repo_dir" "$backup_dir"
  if (( test_signal_after_backup )); then
    kill -TERM $$
  fi
fi

if ! mv -- "$stage_dir" "$repo_dir"; then
  if [[ -n "$backup_dir" && -e "$backup_dir" && ! -e "$repo_dir" ]]; then
    mv -- "$backup_dir" "$repo_dir"
  fi
  die "could not promote verified staging repository"
fi
stage_path_index=${temporary_paths[(Ie)$stage_dir]}
(( stage_path_index )) || die "promoted staging path is not tracked for cleanup"
temporary_paths[$stage_path_index]=()
if [[ -n "$backup_dir" && -e "$backup_dir" ]]; then
  rm -rf -- "$backup_dir"
fi
backup_dir=

print -- "Staged exact ChatGPT fallback: ${repo_dir}/${package_file_name}"
print -- "Package SHA-256: $package_sha256"
print -- "Source commit: $source_commit"
print -- "Source tag object: $source_tag_object"
print -- "Provenance: ${repo_dir}/chatgpt.provenance.json"
