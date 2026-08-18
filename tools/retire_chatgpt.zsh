#!/usr/bin/env zsh

emulate -L zsh
setopt errexit nounset pipefail extendedglob

script_dir=${0:A:h}
script_name=${0:t}
manifest_tool=${script_dir}/repository_manifest.py
owned_directory_tool=${script_dir}/repository_owned_directory.py
source_repo_dir=
input_manifest=
input_manifest_sha256=
repo_dir=
repo_name=nisavid

usage() {
  cat <<EOF
Usage: ${script_name} --source-repo-dir DIR --input-manifest FILE \\
  --input-manifest-sha256 SHA256 --repo-dir DIR [--repo-name NAME]

Construct a new complete pacman repository candidate by removing only the
retired chatgpt, codex-app, and codex-desktop producer identities from an
accepted complete repository. The source repository is never modified.
EOF
}

die() {
  print -ru2 -- "$*"
  exit 2
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

sha256_file() {
  sha256sum -- "$1" | awk '{print $1}'
}

require_sha256() {
  local value=$1 label=$2
  (( ${#value} == 64 )) && [[ "$value" == [0-9a-f]## ]] \
    || die "$label is not a lowercase SHA-256"
}

package_name_from_archive() {
  bsdtar -xOf "$1" .PKGINFO 2>/dev/null \
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

directory_identity() {
  stat -Lc '%d:%i' -- "$1"
}

move_to_unused_path() {
  local source=$1 destination=$2

  [[ ! -e "$destination" && ! -L "$destination" ]] || return 1
  mv --no-clobber --no-target-directory -- "$source" "$destination"
}

claim_owned_directory() {
  local source=$1 destination=$2 expected_identity=$3
  local actual_identity move_status=0 restore_status=0

  claim_state=indeterminate
  claim_status=0
  if [[ ! -d "$source" || -L "$source" ]] \
      || ! actual_identity=$(directory_identity "$source") \
      || [[ "$actual_identity" != "$expected_identity" ]]; then
    claim_state=identity-mismatch
    return 1
  fi
  [[ ! -e "$destination" && ! -L "$destination" ]] || return 1
  move_to_unused_path "$source" "$destination" || move_status=$?
  if [[ ! -e "$source" && ! -L "$source" \
      && -d "$destination" && ! -L "$destination" ]]; then
    if actual_identity=$(directory_identity "$destination") \
        && [[ "$actual_identity" == "$expected_identity" ]]; then
      claim_state=claimed
      return 0
    fi
    move_to_unused_path "$destination" "$source" || restore_status=$?
    claim_state=identity-mismatch
    if (( restore_status )); then
      claim_status=$restore_status
    else
      claim_status=$move_status
    fi
    return 1
  fi
  if [[ -d "$source" && ! -L "$source" \
      && ! -e "$destination" && ! -L "$destination" ]] \
      && actual_identity=$(directory_identity "$source") \
      && [[ "$actual_identity" == "$expected_identity" ]]; then
    claim_state=no-effect
    claim_status=$move_status
    return 1
  fi
  claim_status=$move_status
  return 1
}

write_repository_records() {
  local database=$1 output=$2 description_entry package_description
  local package_name package_file_name package_size package_sha256

  : >"$output"
  for description_entry in ${(f)"$(bsdtar -tf "$database" | sed -n 's#/desc$#/desc#p')"}; do
    package_description=$(bsdtar -xOf "$database" "$description_entry" 2>/dev/null) \
      || die "could not read repository index entry: $description_entry"
    package_name=$(print -r -- "$package_description" \
      | awk '/^%NAME%$/ { getline; print; exit }')
    package_file_name=$(print -r -- "$package_description" \
      | awk '/^%FILENAME%$/ { getline; print; exit }')
    package_size=$(print -r -- "$package_description" \
      | awk '/^%CSIZE%$/ { getline; print; exit }')
    package_sha256=$(print -r -- "$package_description" \
      | awk '/^%SHA256SUM%$/ { getline; print; exit }')
    [[ -n "$package_name" && "$package_name" != *$'\t'* \
      && "$package_name" != *$'\n'* ]] \
      || die "repository index has an invalid package name: $description_entry"
    [[ -n "$package_file_name" && "$package_file_name" == "${package_file_name:t}" \
      && "$package_file_name" != "." && "$package_file_name" != ".." \
      && "$package_file_name" != *$'\t'* && "$package_file_name" != *$'\n'* ]] \
      || die "repository index has an unsafe package filename: $description_entry"
    [[ -n "$package_size" && "$package_size" == <-> ]] \
      || die "repository index has an invalid package size: $package_file_name"
    require_sha256 "$package_sha256" \
      "repository index package SHA-256 for $package_file_name"
    print -r -- "$package_name"$'\t'"$package_file_name"$'\t'"$package_size"$'\t'"$package_sha256" \
      >>"$output"
  done
}

write_index_member_manifest() {
  local database=$1 output=$2 member normalized_member package_directory
  local description package_name member_kind member_sha256 member_metadata
  local member_metadata_sha256 expected_type

  : >"$output"
  for member in ${(f)"$(bsdtar -tf "$database")"}; do
    [[ -n "$member" && "$member" != *$'\t'* && "$member" != *$'\n'* ]] \
      || die "repository index contains an unsafe member name"
    normalized_member=${member#./}
    [[ "$normalized_member" == "$member" ]] \
      || die "repository index contains an unsupported member: $member"
    if [[ "$normalized_member" == */ ]]; then
      package_directory=${normalized_member%/}
      member_kind=directory
      member_sha256=-
      expected_type=d
    elif [[ "$normalized_member" == */desc || "$normalized_member" == */files ]]; then
      package_directory=${normalized_member:h}
      member_kind=${normalized_member:t}
      member_sha256=$(bsdtar -xOf "$database" "$member" 2>/dev/null \
        | sha256sum | awk '{print $1}') \
        || die "could not hash repository index member: $member"
      expected_type=-
    else
      die "repository index contains an unsupported member: $member"
    fi
    [[ -n "$package_directory" && "$package_directory" == "${package_directory:t}" \
      && "$package_directory" != "." && "$package_directory" != ".." \
      && "$package_directory" != *$'\t'* && "$package_directory" != *$'\n'* ]] \
      || die "repository index contains an unsafe package directory: $member"
    description=$(bsdtar -xOf "$database" "${package_directory}/desc" 2>/dev/null) \
      || die "could not read repository description for index member: $member"
    package_name=$(print -r -- "$description" \
      | awk '/^%NAME%$/ { getline; print; exit }')
    [[ -n "$package_name" && "$package_name" != *$'\t'* \
      && "$package_name" != *$'\n'* ]] \
      || die "repository index member has an invalid package name: $member"
    member_metadata=$(env LC_ALL=C TZ=UTC0 tar --zstd --no-recursion \
      --full-time --numeric-owner --quoting-style=escape \
      -tvf "$database" -- "$member" 2>/dev/null) \
      || die "could not read repository index member metadata: $member"
    [[ -n "$member_metadata" && "$member_metadata" != *$'\n'* \
      && "${member_metadata[1]}" == "$expected_type" ]] \
      || die "repository index member has an unexpected type: $member"
    member_metadata_sha256=$(print -rn -- "$member_metadata" \
      | sha256sum | awk '{print $1}')
    print -r -- "$package_name"$'\t'"$member_kind"$'\t'"$normalized_member"$'\t'"$member_sha256"$'\t'"$member_metadata_sha256" \
      >>"$output"
  done
  sort -o "$output" -- "$output"
}

validate_repository_aliases() {
  local repository_dir=$1 repository_name=$2
  local database_alias=${repository_dir}/${repository_name}.db
  local files_alias=${repository_dir}/${repository_name}.files
  local database_target files_target

  [[ -L "$database_alias" ]] \
    || die "canonical database alias is missing: $database_alias"
  database_target=$(readlink -- "$database_alias") \
    || die "could not read canonical database alias: $database_alias"
  [[ "$database_target" == "${repository_name}.db.tar.zst" ]] \
    || die "canonical database alias target does not match: $database_alias"
  [[ -f "${repository_dir}/${database_target}" \
    && ! -L "${repository_dir}/${database_target}" ]] \
    || die "canonical database alias does not name the repository database"

  [[ -L "$files_alias" ]] \
    || die "canonical files alias is missing: $files_alias"
  files_target=$(readlink -- "$files_alias") \
    || die "could not read canonical files alias: $files_alias"
  [[ "$files_target" == "${repository_name}.files.tar.zst" ]] \
    || die "canonical files alias target does not match: $files_alias"
  [[ -f "${repository_dir}/${files_target}" \
    && ! -L "${repository_dir}/${files_target}" ]] \
    || die "canonical files alias does not name the repository files index"
}

validate_repository_shape() {
  local repository_dir=$1 database=$2 files_database=$3 record_prefix=$4
  local allow_empty=${5:-0}
  local database_records=${record_prefix}.db-records
  local files_records=${record_prefix}.files-records
  local sorted_database_records=${record_prefix}.db-records.sorted
  local sorted_files_records=${record_prefix}.files-records.sorted
  local database_members=${record_prefix}.db-members
  local files_members=${record_prefix}.files-members
  local package_name package_file_name expected_size expected_sha256 package_path
  local actual_size archive archive_name indexed_file_name signature package_count
  local non_signature_archive_count=0
  local -a package_signatures

  write_repository_records "$database" "$database_records"
  write_repository_records "$files_database" "$files_records"
  sort -- "$database_records" >"$sorted_database_records"
  sort -- "$files_records" >"$sorted_files_records"
  cmp -s -- "$sorted_database_records" "$sorted_files_records" \
    || die "repository database and files indexes disagree"
  write_index_member_manifest "$database" "$database_members"
  write_index_member_manifest "$files_database" "$files_members"
  python3 - "$sorted_database_records" "$database_members" "$files_members" <<'PY' || exit 2
import sys


def read_members(path):
    members = []
    with open(path, encoding="utf-8") as source:
        for line in source:
            name, kind, _member_path, _content_digest, _metadata_digest = (
                line.rstrip("\n").split("\t")
            )
            members.append((name, kind))
    if len(members) != len(set(members)):
        raise SystemExit("repository index contains duplicate member records")
    return set(members)


with open(sys.argv[1], encoding="utf-8") as source:
    package_names = [line.split("\t", 1)[0] for line in source if line.strip()]
expected_database = {
    (name, kind) for name in package_names for kind in ("directory", "desc")
}
expected_files = expected_database | {(name, "files") for name in package_names}
if read_members(sys.argv[2]) != expected_database:
    raise SystemExit("database index member set does not match package records")
if read_members(sys.argv[3]) != expected_files:
    raise SystemExit("files index member set does not match package records")
PY
  package_count=$(wc -l <"$sorted_database_records")
  if (( package_count == 0 )); then
    (( allow_empty )) || die "source repository indexes are empty"
    for archive in "$repository_dir"/*.pkg.tar.*(N); do
      [[ "$archive" == *.sig ]] || (( ++non_signature_archive_count ))
    done
    (( non_signature_archive_count == 0 )) \
      || die "empty candidate index retains package archives"
    package_signatures=("$repository_dir"/*.pkg.tar.*.sig(N))
    (( ${#package_signatures} == 0 )) \
      || die "empty candidate index retains package signatures"
    return 0
  fi
  [[ "$(cut -f1 "$sorted_database_records" | sort -u | wc -l)" == "$package_count" ]] \
    || die "repository index contains duplicate package names"
  [[ "$(cut -f2 "$sorted_database_records" | sort -u | wc -l)" == "$package_count" ]] \
    || die "repository index contains duplicate package filenames"

  while IFS=$'\t' read -r package_name package_file_name expected_size expected_sha256; do
    package_path=${repository_dir}/${package_file_name}
    [[ -f "$package_path" && ! -L "$package_path" ]] \
      || die "indexed package archive is missing: $package_file_name"
    actual_size=$(stat -c '%s' -- "$package_path")
    [[ "$actual_size" == "$expected_size" ]] \
      || die "indexed package archive size does not match: $package_file_name"
    [[ "$(sha256_file "$package_path")" == "$expected_sha256" ]] \
      || die "indexed package archive SHA-256 does not match: $package_file_name"
    [[ "$(package_name_from_archive "$package_path")" == "$package_name" ]] \
      || die "indexed package archive identity does not match: $package_file_name"
  done <"$sorted_database_records"

  for archive in "$repository_dir"/*.pkg.tar.*(N); do
    [[ "$archive" != *.sig ]] || continue
    archive_name=${archive:t}
    indexed_file_name=$(awk -F '\t' -v filename="$archive_name" \
      '$2 == filename { print $2; exit }' "$sorted_database_records")
    [[ "$indexed_file_name" == "$archive_name" ]] \
      || die "repository contains an unindexed package archive: $archive_name"
  done
  for signature in "$repository_dir"/*.pkg.tar.*.sig(N); do
    package_path=${signature%.sig}
    [[ -f "$signature" && ! -L "$signature" && -f "$package_path" \
      && ! -L "$package_path" ]] \
      || die "repository contains a detached or unsafe package signature: ${signature:t}"
  done
}

while (( $# )); do
  case "$1" in
    --source-repo-dir)
      (( $# >= 2 )) || die "--source-repo-dir requires a value"
      source_repo_dir=${2:a}
      shift 2
      ;;
    --input-manifest)
      (( $# >= 2 )) || die "--input-manifest requires a value"
      input_manifest=${2:a}
      shift 2
      ;;
    --input-manifest-sha256)
      (( $# >= 2 )) || die "--input-manifest-sha256 requires a value"
      input_manifest_sha256=$2
      shift 2
      ;;
    --repo-dir)
      (( $# >= 2 )) || die "--repo-dir requires a value"
      repo_dir=${2:a}
      shift 2
      ;;
    --repo-name)
      (( $# >= 2 )) || die "--repo-name requires a value"
      repo_name=$2
      shift 2
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

[[ -n "$source_repo_dir" ]] || die "--source-repo-dir is required"
[[ -n "$input_manifest" ]] || die "--input-manifest is required"
[[ -n "$input_manifest_sha256" ]] || die "--input-manifest-sha256 is required"
[[ -n "$repo_dir" ]] || die "--repo-dir is required"
[[ "$repo_name" =~ '^[A-Za-z0-9._-]+$' ]] \
  || die "repo name contains unsupported characters: $repo_name"
[[ "$repo_name" != "." && "$repo_name" != ".." ]] \
  || die "repo name must not be a path segment"
(( ${#input_manifest_sha256} == 64 )) \
  && [[ "$input_manifest_sha256" == [0-9a-f]## ]] \
  || die "input manifest digest is not a lowercase SHA-256"
[[ -d "$source_repo_dir" && ! -L "$source_repo_dir" ]] \
  || die "source repository must be a real directory: $source_repo_dir"
[[ -f "$input_manifest" && ! -L "$input_manifest" ]] \
  || die "input manifest must be a regular non-symlink file: $input_manifest"
[[ "${source_repo_dir:A}" == "${source_repo_dir:a}" ]] \
  || die "source repository path must not contain symlink components: $source_repo_dir"
[[ "${input_manifest:A}" == "${input_manifest:a}" ]] \
  || die "input manifest path must not contain symlink components: $input_manifest"
source_repo_dir=${source_repo_dir:A}
input_manifest=${input_manifest:A}
[[ "$source_repo_dir" != "$repo_dir" ]] \
  || die "source and candidate repository directories must differ"
[[ "$repo_dir" != "/" && "${repo_dir:t}" != "." && "${repo_dir:t}" != ".." ]] \
  || die "unsafe candidate repository directory: $repo_dir"
[[ ! -e "$repo_dir" && ! -L "$repo_dir" ]] \
  || die "candidate repository path must not already exist: $repo_dir"

for command_name in awk bsdtar cmp cp cut date env mkdir mktemp mv python3 \
  readlink repo-remove rm sed sha256sum sort stat tar wc zstd; do
  need_command "$command_name"
done
[[ -f "$manifest_tool" && ! -L "$manifest_tool" && -x "$manifest_tool" ]] \
  || die "repository manifest tool is not executable: $manifest_tool"
[[ -f "$owned_directory_tool" && ! -L "$owned_directory_tool" ]] \
  || die "repository owned-directory helper is unavailable: $owned_directory_tool"

source_db=${source_repo_dir}/${repo_name}.db.tar.zst
source_files=${source_repo_dir}/${repo_name}.files.tar.zst
[[ -f "$source_db" && ! -L "$source_db" ]] \
  || die "source repository database is missing: $source_db"
[[ -f "$source_files" && ! -L "$source_files" ]] \
  || die "source repository files index is missing: $source_files"
validate_repository_aliases "$source_repo_dir" "$repo_name"
for index_signature in \
  "${source_repo_dir}/${repo_name}.db"*.sig(N) \
  "${source_repo_dir}/${repo_name}.files"*.sig(N); do
  die "signed repository indexes cannot be rewritten without a signer workflow: ${index_signature:t}"
done

repo_parent=${repo_dir:h}
repo_leaf=${repo_dir:t}
[[ -d "$repo_parent" ]] \
  || die "candidate repository parent must already exist: $repo_parent"
[[ ! -L "$repo_parent" && "${repo_parent:A}" == "${repo_parent:a}" ]] \
  || die "candidate repository parent must not contain symlinks: $repo_parent"
repo_parent=${repo_parent:A}
repo_dir=${repo_parent}/${repo_leaf}
[[ "${repo_dir}/" != "${source_repo_dir}/"* \
    && "${source_repo_dir}/" != "${repo_dir}/"* ]] \
  || die "source and candidate repository directories must not overlap"
writer_lock=${repo_dir}.writer.lock
writer_lock_owned=0
writer_lock_identity=
cleanup_safe=1
signal_deferral=0
pending_signal=0
candidate_identity=
candidate_promotion_owned=0
candidate_finalized=0
candidate_rollback_attempted=0
failed_dir=
typeset -a temporary_paths temporary_path_identities
cleanup() {
  local exit_status=$? temporary_path temporary_identity actual_identity
  local temporary_index claim_path claimed_index delete_status=0
  local -a claimed_paths claimed_identities
  if (( candidate_promotion_owned && ! candidate_finalized \
      && ! candidate_rollback_attempted )); then
    [[ -n "$failed_dir" ]] \
      || failed_dir=${repo_parent}/.${repo_leaf}.retire-failed.$(date -u +%Y%m%dT%H%M%SZ).$$
    candidate_rollback_attempted=1
    if claim_owned_directory "$repo_dir" "$failed_dir" "$candidate_identity"; then
      candidate_promotion_owned=0
      print -ru2 -- "interrupted retirement candidate retained at: $failed_dir"
    else
      cleanup_safe=0
      print -ru2 -- "retirement candidate rollback could not be identified (${claim_state}, status ${claim_status:-0}); candidate: $repo_dir; failed destination: $failed_dir"
    fi
  fi
  if (( cleanup_safe )); then
    if (( writer_lock_owned )); then
      if [[ ! -d "$writer_lock" || -L "$writer_lock" ]] \
          || ! actual_identity=$(directory_identity "$writer_lock") \
          || [[ "$actual_identity" != "$writer_lock_identity" ]]; then
        cleanup_safe=0
        print -ru2 -- "repository writer lock identity changed: $writer_lock"
      fi
    fi
  fi
  if (( cleanup_safe )); then
    for (( temporary_index = ${#temporary_paths}; temporary_index >= 1; --temporary_index )); do
      temporary_path=${temporary_paths[$temporary_index]}
      temporary_identity=${temporary_path_identities[$temporary_index]}
      [[ -n "$temporary_path" ]] || continue
      if [[ ! -e "$temporary_path" && ! -L "$temporary_path" ]]; then
        cleanup_safe=0
        print -ru2 -- "tracked temporary path is missing: $temporary_path"
        break
      fi
      claim_path=${temporary_path}.cleanup.$$.${temporary_index}
      if claim_owned_directory "$temporary_path" "$claim_path" "$temporary_identity"; then
        claimed_paths+=("$claim_path")
        claimed_identities+=("$temporary_identity")
      else
        cleanup_safe=0
        print -ru2 -- "temporary path identity changed: $temporary_path"
        print -ru2 -- "temporary path claim state: ${claim_state}; source: $temporary_path; claim: $claim_path"
        break
      fi
    done
  fi
  if (( cleanup_safe )); then
    for (( claimed_index = 1; claimed_index <= ${#claimed_paths}; ++claimed_index )); do
      claim_path=${claimed_paths[$claimed_index]}
      temporary_identity=${claimed_identities[$claimed_index]}
      if [[ ! -d "$claim_path" || -L "$claim_path" ]] \
          || ! actual_identity=$(directory_identity "$claim_path") \
          || [[ "$actual_identity" != "$temporary_identity" ]]; then
        cleanup_safe=0
        print -ru2 -- "claimed temporary path identity changed: $claim_path"
      fi
    done
  fi
  if (( cleanup_safe )); then
    for (( claimed_index = 1; claimed_index <= ${#claimed_paths}; ++claimed_index )); do
      claim_path=${claimed_paths[$claimed_index]}
      temporary_identity=${claimed_identities[$claimed_index]}
      python3 "$owned_directory_tool" delete-tree "$claim_path" \
        "$temporary_identity" >/dev/null 2>&1 || delete_status=$?
      if (( delete_status )) || [[ -e "$claim_path" || -L "$claim_path" ]]; then
        cleanup_safe=0
        print -ru2 -- "could not remove claimed temporary path: $claim_path"
        break
      fi
    done
  fi
  if (( cleanup_safe && writer_lock_owned )); then
    if [[ -d "$writer_lock" && ! -L "$writer_lock" ]] \
        && actual_identity=$(directory_identity "$writer_lock") \
        && [[ "$actual_identity" == "$writer_lock_identity" ]]; then
      if python3 "$owned_directory_tool" remove-empty "$writer_lock" \
          "$writer_lock_identity" >/dev/null 2>&1; then
        writer_lock_owned=0
      else
        cleanup_safe=0
        print -ru2 -- "could not remove repository writer lock: $writer_lock"
      fi
    else
      cleanup_safe=0
      print -ru2 -- "repository writer lock identity changed: $writer_lock"
    fi
  fi
  if (( ! cleanup_safe )); then
    for claim_path in "${claimed_paths[@]}"; do
      print -ru2 -- "claimed retirement path retained at: $claim_path"
    done
    print -ru2 -- "retirement state is indeterminate; preserving repository lock and transaction paths for recovery"
  fi
  return $exit_status
}
trap cleanup EXIT
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
trap 'handle_signal 129' HUP
trap 'handle_signal 130' INT
trap 'handle_signal 143' TERM

writer_lock_acquired=0
signal_deferral=1
if mkdir -- "$writer_lock" 2>/dev/null; then
  writer_lock_acquired=1
  writer_lock_owned=1
  writer_lock_identity=$(directory_identity "$writer_lock") \
    || die "could not identify the repository writer lock: $writer_lock"
fi
finish_signal_deferral
(( writer_lock_acquired )) \
  || die "another repository writer appears to be active: $writer_lock"

work_dir=$(mktemp -d "${repo_parent}/.${repo_leaf}.retire-work.XXXXXX")
temporary_paths+=("$work_dir")
temporary_path_identities+=("$(directory_identity "$work_dir")")
stage_dir=$(mktemp -d "${repo_parent}/.${repo_leaf}.retire-stage.XXXXXX")
temporary_paths+=("$stage_dir")
temporary_path_identities+=("$(directory_identity "$stage_dir")")
manifest_snapshot=${work_dir}/input-manifest.json
source_before=${work_dir}/source-before.json
source_after=${work_dir}/source-after.json
source_final=${work_dir}/source-final.json
stage_before=${work_dir}/stage-before.json
stage_after=${work_dir}/stage-after.json
stage_final=${work_dir}/stage-final.json
promoted_manifest=${work_dir}/promoted.json
removed_entries=${work_dir}/removed-entries

cp -- "$input_manifest" "$manifest_snapshot"
[[ "$(sha256_file "$manifest_snapshot")" == "$input_manifest_sha256" ]] \
  || die "input manifest SHA-256 does not match"
python3 "$manifest_tool" "$source_repo_dir" >"$source_before"
cmp -s -- "$manifest_snapshot" "$source_before" \
  || die "source repository does not match the accepted input manifest"
validate_repository_shape "$source_repo_dir" "$source_db" "$source_files" \
  "${work_dir}/source"

cp -a -- "$source_repo_dir"/. "$stage_dir"/
python3 "$manifest_tool" "$stage_dir" >"$stage_before"
cmp -s -- "$manifest_snapshot" "$stage_before" \
  || die "candidate copy does not match the accepted input manifest"
python3 "$manifest_tool" "$source_repo_dir" >"$source_after"
cmp -s -- "$manifest_snapshot" "$source_after" \
  || die "source repository changed while constructing the candidate"

stage_db=${stage_dir}/${repo_name}.db.tar.zst
stage_files=${stage_dir}/${repo_name}.files.tar.zst
typeset -a retired_names=(chatgpt codex-app codex-desktop)
typeset -a source_names
source_names=(${(f)"$(repo_database_package_names "$stage_db")"})
(( ${source_names[(Ie)chatgpt]} )) \
  || die "source repository does not contain the accepted chatgpt package"
stage_db_members_before=${work_dir}/stage-db-members-before
stage_files_members_before=${work_dir}/stage-files-members-before
stage_db_members_after=${work_dir}/stage-db-members-after
stage_files_members_after=${work_dir}/stage-files-members-after
write_index_member_manifest "$stage_db" "$stage_db_members_before"
write_index_member_manifest "$stage_files" "$stage_files_members_before"

: >"$removed_entries"
for archive in "$stage_dir"/*.pkg.tar.*(N); do
  [[ "$archive" != *.sig ]] || continue
  package_name=$(package_name_from_archive "$archive" || true)
  if (( ${retired_names[(Ie)$package_name]} )); then
    print -r -- "${archive:t}" >>"$removed_entries"
    [[ ! -e "${archive}.sig" ]] \
      || print -r -- "${archive:t}.sig" >>"$removed_entries"
  fi
done
[[ ! -e "${stage_dir}/chatgpt.provenance.json" ]] \
  || print -r -- "chatgpt.provenance.json" >>"$removed_entries"
print -r -- "${stage_db:t}.old" >>"$removed_entries"
print -r -- "${stage_files:t}.old" >>"$removed_entries"
for stale_index in "${stage_db}.old" "${stage_files}.old"; do
  [[ ! -e "$stale_index" && ! -L "$stale_index" ]] \
    || [[ -f "$stale_index" && ! -L "$stale_index" ]] \
    || die "stale repository index backup is unsafe: ${stale_index:t}"
done

for retired_name in "${retired_names[@]}"; do
  if (( ${source_names[(Ie)$retired_name]} )); then
    repo-remove "$stage_db" "$retired_name" >/dev/null 2>&1 \
      || die "repo-remove failed for retired package: $retired_name"
  fi
done
for archive in "$stage_dir"/*.pkg.tar.*(N); do
  [[ "$archive" != *.sig ]] || continue
  package_name=$(package_name_from_archive "$archive" || true)
  if (( ${retired_names[(Ie)$package_name]} )); then
    rm -f -- "$archive" "${archive}.sig"
  fi
done
rm -f -- "${stage_dir}/chatgpt.provenance.json"
for stale_index in "${stage_db}.old" "${stage_files}.old"; do
  [[ ! -e "$stale_index" && ! -L "$stale_index" ]] \
    || [[ -f "$stale_index" && ! -L "$stale_index" ]] \
    || die "stale repository index backup is unsafe: ${stale_index:t}"
  rm -f -- "$stale_index"
done
validate_repository_aliases "$stage_dir" "$repo_name"

validate_repository_shape "$stage_dir" "$stage_db" "$stage_files" \
  "${work_dir}/candidate" 1

typeset -a remaining_names
remaining_names=(${(f)"$(repo_database_package_names "$stage_db")"})
for retired_name in "${retired_names[@]}"; do
  (( ! ${remaining_names[(Ie)$retired_name]} )) \
    || die "candidate repository still contains retired package: $retired_name"
done
[[ -f "$stage_files" && ! -L "$stage_files" ]] \
  || die "candidate repository files index is missing after retirement"
write_index_member_manifest "$stage_db" "$stage_db_members_after"
write_index_member_manifest "$stage_files" "$stage_files_members_after"
python3 - "$stage_db_members_before" "$stage_db_members_after" \
  "$stage_files_members_before" "$stage_files_members_after" \
  "${retired_names[@]}" <<'PY' || exit 2
import sys


def read_manifest(path):
    records = {}
    with open(path, encoding="utf-8") as source:
        for line in source:
            name, kind, member_path, content_digest, metadata_digest = (
                line.rstrip("\n").split("\t")
            )
            key = (name, kind)
            if key in records:
                raise SystemExit(
                    f"repository index contains a duplicate record: {name}/{kind}"
                )
            records[key] = (member_path, content_digest, metadata_digest)
    return records


retired = set(sys.argv[5:])
for before_path, after_path in ((sys.argv[1], sys.argv[2]), (sys.argv[3], sys.argv[4])):
    before = {
        key: digest
        for key, digest in read_manifest(before_path).items()
        if key[0] not in retired
    }
    after = read_manifest(after_path)
    changed = sorted(key for key in before.keys() & after.keys() if before[key] != after[key])
    if changed:
        name, kind = changed[0]
        raise SystemExit(f"unrelated repository index record changed: {name}/{kind}")
    if before != after:
        missing = sorted(f"{name}/{kind}" for name, kind in before.keys() - after.keys())
        unexpected = sorted(f"{name}/{kind}" for name, kind in after.keys() - before.keys())
        raise SystemExit(
            "candidate repository index record set does not match exact retirement: "
            f"missing={missing!r} unexpected={unexpected!r}"
        )
PY

python3 "$manifest_tool" "$stage_dir" >"$stage_after"
python3 - "$manifest_snapshot" "$stage_after" "$removed_entries" "$repo_name" <<'PY' || exit 2
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    before = json.load(source)
with open(sys.argv[2], encoding="utf-8") as source:
    after = json.load(source)
with open(sys.argv[3], encoding="utf-8") as source:
    removed = {line.rstrip("\n") for line in source if line.rstrip("\n")}
repo_name = sys.argv[4]
mutable = {
    f"{repo_name}.db",
    f"{repo_name}.db.tar.zst",
    f"{repo_name}.files",
    f"{repo_name}.files.tar.zst",
}
before_entries = {entry["name"]: entry for entry in before["entries"]}
after_entries = {entry["name"]: entry for entry in after["entries"]}
expected_names = set(before_entries) - removed
if set(after_entries) != expected_names:
    missing = sorted(expected_names - set(after_entries))
    unexpected = sorted(set(after_entries) - expected_names)
    raise SystemExit(
        "candidate repository entry set does not match exact retirement: "
        f"missing={missing!r} unexpected={unexpected!r}"
    )
for name in sorted(expected_names - mutable):
    if before_entries[name] != after_entries[name]:
        raise SystemExit(f"unrelated repository entry changed: {name}")
PY

python3 "$manifest_tool" "$source_repo_dir" >"$source_final"
cmp -s -- "$manifest_snapshot" "$source_final" \
  || die "source repository changed before candidate promotion"
validate_repository_aliases "$stage_dir" "$repo_name"
python3 "$manifest_tool" "$stage_dir" >"$stage_final"
cmp -s -- "$stage_after" "$stage_final" \
  || die "verified retirement candidate changed before promotion"

candidate_identity=$(directory_identity "$stage_dir") \
  || die "could not identify the verified retirement candidate"
promotion_status=0
promotion_state=indeterminate
signal_deferral=1
move_to_unused_path "$stage_dir" "$repo_dir" || promotion_status=$?
if [[ ! -e "$stage_dir" && ! -L "$stage_dir" \
    && -d "$repo_dir" && ! -L "$repo_dir" ]]; then
  promoted_identity=
  if promoted_identity=$(directory_identity "$repo_dir") \
      && [[ "$promoted_identity" == "$candidate_identity" ]]; then
    promotion_state=promoted
  fi
elif [[ ! -e "$repo_dir" && ! -L "$repo_dir" \
    && -d "$stage_dir" && ! -L "$stage_dir" ]]; then
  retained_identity=
  if retained_identity=$(directory_identity "$stage_dir") \
      && [[ "$retained_identity" == "$candidate_identity" ]]; then
    promotion_state=no_effect
  fi
fi

if [[ "$promotion_state" == no_effect ]]; then
  (( promotion_status )) || promotion_status=1
  finish_signal_deferral
  die "could not promote the verified retirement candidate (status ${promotion_status})"
fi
if [[ "$promotion_state" != promoted ]]; then
  cleanup_safe=0
  print -ru2 -- "recovery manifests preserved at: $work_dir"
  finish_signal_deferral
  die "could not identify the retirement candidate after promotion (status ${promotion_status})"
fi
candidate_promotion_owned=1
stage_index=${temporary_paths[(Ie)$stage_dir]}
(( stage_index )) || die "promoted candidate path is not tracked for cleanup"
temporary_paths[$stage_index]=()
temporary_path_identities[$stage_index]=()

python3 "$manifest_tool" "$repo_dir" >"$promoted_manifest" \
  || post_promotion_verified=0
post_promotion_verified=${post_promotion_verified:-1}
if (( post_promotion_verified )) && ! cmp -s -- "$stage_after" "$promoted_manifest"; then
  post_promotion_verified=0
fi
if (( ! post_promotion_verified )); then
  failed_dir=${repo_parent}/.${repo_leaf}.retire-failed.$(date -u +%Y%m%dT%H%M%SZ).$$
  candidate_rollback_attempted=1
  if claim_owned_directory "$repo_dir" "$failed_dir" "$candidate_identity"; then
    candidate_promotion_owned=0
    finish_signal_deferral
    die "retirement candidate failed post-promotion verification; failed copy retained at $failed_dir"
  fi
  cleanup_safe=0
  print -ru2 -- "recovery manifests preserved at: $work_dir"
  finish_signal_deferral
  die "retirement candidate failed post-promotion verification and could not be identified (${claim_state}, status ${claim_status:-0}); candidate: $repo_dir; failed destination: $failed_dir"
fi

validate_repository_aliases "$repo_dir" "$repo_name"
finish_signal_deferral
candidate_finalized=1

print -- "Constructed retired ChatGPT repository candidate: $repo_dir"
