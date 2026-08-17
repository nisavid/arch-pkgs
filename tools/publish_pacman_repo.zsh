#!/usr/bin/env zsh

emulate -L zsh
setopt errexit nounset pipefail

script_dir=${0:A:h}
script_name=${0:t}
repo_root=${script_dir:h}
repo_dir=${repo_root}/repo/x86_64
repo_name=nisavid
publish_dir=
publish_dir_set=0
dry_run=0
test_mode=${ARCH_PKGS_PUBLISH_TEST_MODE:-0}
publish_retention=${ARCH_PKGS_PUBLISH_RETENTION:-2}
[[ "$test_mode" == 0 || "$test_mode" == 1 ]] \
  || { print -u2 -- "ARCH_PKGS_PUBLISH_TEST_MODE must be 0 or 1"; exit 2; }
[[ "$publish_retention" =~ '^[1-9][0-9]*$' ]] \
  || { print -u2 -- "ARCH_PKGS_PUBLISH_RETENTION must be a positive integer"; exit 2; }

usage() {
  local default_publish_dir=${publish_dir:-/srv/pacman/${repo_name}/x86_64}
  cat <<EOF
Usage: ${script_name} [--dry-run] [--repo-dir DIR] [--repo-name NAME] [--publish-dir DIR]

Publish the checkout-local pacman repo to the pacman-visible system path.

Defaults:
  repo-dir:     ${repo_dir}
  repo-name:    ${repo_name}
  publish-dir: ${default_publish_dir}
  retained previous repositories: ${publish_retention}
EOF
}

die() {
  print -u2 -- "$*"
  exit 2
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

write_repo_manifest() {
  local directory=$1 output=$2
  python3 - "$directory" >"$output" <<'PY'
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
entries = []
for path in sorted(root.iterdir(), key=lambda item: os.fsencode(item.name)):
    # Pacman repository publication is intentionally flat; never recurse.
    metadata = path.lstat()
    common = {
        "gid": metadata.st_gid,
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "name": path.name,
        "uid": metadata.st_uid,
    }
    if path.is_symlink():
        target = os.readlink(path)
        if "/" in target or target in ("", ".", ".."):
            raise SystemExit(f"unsafe repository symlink: {path.name} -> {target}")
        if not (root / target).is_file():
            raise SystemExit(f"repository symlink target is missing: {path.name} -> {target}")
        entries.append({**common, "target": target, "type": "symlink"})
    elif path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        entries.append(
            {
                **common,
                "sha256": digest.hexdigest(),
                "size": metadata.st_size,
                "type": "file",
            }
        )
    else:
        raise SystemExit(f"unsupported repository entry: {path.name}")

print(json.dumps({"entries": entries, "schemaVersion": 2}, indent=2, sort_keys=True))
PY
}

directory_identity() {
  stat -Lc '%d:%i' -- "$1"
}

validate_repo_name() {
  [[ "$repo_name" =~ '^[A-Za-z0-9._-]+$' ]] || die "repo name contains unsupported characters: $repo_name"
  [[ "$repo_name" != "." && "$repo_name" != ".." ]] || die "repo name must not be a path segment: $repo_name"
}

validate_publish_dir() {
  local component path rel trusted_root

  [[ -n "$publish_dir" ]] || die "publish dir must not be empty"
  [[ "$publish_dir" != "/" ]] || die "publish dir must not be /"
  [[ ! -e "$publish_dir" || -d "$publish_dir" ]] \
    || die "publish dir exists and is not a directory: $publish_dir"
  if (( test_mode )); then
    [[ "$publish_dir" == /tmp/* ]] \
      || die "test-mode publish dir must be under /tmp: $publish_dir"
  else
    [[ "$publish_dir" == /srv/pacman/* ]] \
      || die "publish dir must be under /srv/pacman: $publish_dir"
  fi
  [[ "$publish_dir" != "$repo_dir" ]] || die "publish dir must differ from repo dir: $publish_dir"

  if (( test_mode )); then
    rel=${publish_dir#/tmp/}
    trusted_root=/tmp
  else
    rel=${publish_dir#/srv/pacman/}
    trusted_root=/srv/pacman
  fi
  path=$trusted_root
  [[ -d "$trusted_root" && ! -L "$trusted_root" ]] \
    || die "publish trusted root must be a real directory: $trusted_root"
  for component in ${(s:/:)rel}; do
    path=${path}/${component}
    [[ ! -L "$path" ]] \
      || die "publish dir must not contain symlink components under ${trusted_root}: $path"
  done
}

privileged() {
  if (( test_mode )); then
    "$@"
  else
    sudo "$@"
  fi
}

move_to_unused_path() {
  local source=$1 destination=$2

  [[ ! -e "$destination" && ! -L "$destination" ]] || return 1
  privileged mv --no-clobber --no-target-directory -- "$source" "$destination"
}

require_atomic_mv() {
  local version
  version=$(mv --version 2>/dev/null | sed -n '1s/.* //p') \
    || die "publication requires GNU coreutils mv 9.5 or newer"
  python3 - "$version" <<'PY' \
    || die "publication requires GNU coreutils mv 9.5 or newer"
import re
import sys

match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", sys.argv[1])
if match is None or tuple(map(int, match.groups())) < (9, 5):
    raise SystemExit(1)
PY
  mv --help 2>/dev/null | grep -q -- '--exchange' \
    || die "publication mv does not support --exchange"
}

while (( $# )); do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
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
    --publish-dir)
      (( $# >= 2 )) || die "--publish-dir requires a value"
      publish_dir=${2:a}
      publish_dir_set=1
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

repo_dir=${repo_dir:A}
validate_repo_name

if (( ! publish_dir_set )); then
  publish_dir=/srv/pacman/${repo_name}/x86_64
fi
publish_dir=${publish_dir:a}

if (( ! dry_run )); then
  (( test_mode )) || need_command sudo
  need_command rsync
  need_command python3
  need_command cmp
  need_command sha256sum
  need_command awk
  need_command date
  need_command grep
  need_command mv
  need_command stat
  require_atomic_mv
fi

[[ -d "$repo_dir" ]] || die "repo dir does not exist: $repo_dir"
repo_db=${repo_dir}/${repo_name}.db.tar.zst
[[ -f "$repo_db" ]] || die "missing repo database: $repo_db"

validate_publish_dir

if (( dry_run )); then
  print -r -- "DRY-RUN: repo dir: $repo_dir"
  print -r -- "DRY-RUN: repo name: $repo_name"
  print -r -- "DRY-RUN: repo db: $repo_db"
  print -r -- "DRY-RUN: publish dir: $publish_dir"
  print -r -- "DRY-RUN: would compute and retain a SHA-256 manifest for staging"
  print -r -- "DRY-RUN: would copy staging into a candidate directory beside ${(q)publish_dir}"
  print -r -- "DRY-RUN: would serialize publication with a destination-scoped lock"
  print -r -- "DRY-RUN: would verify the candidate manifest before promotion"
  print -r -- "DRY-RUN: would atomically exchange the candidate with the current destination"
  print -r -- "DRY-RUN: would promote the verified candidate and compare its manifest again"
  exit 0
fi

manifest_dir=$(mktemp -d)
writer_lock=
writer_lock_owned=0
signal_deferral=0
pending_signal=0
publication_state=original
previous_identity=
candidate_identity=
destination_lock_owned=0
cleanup_manifest_dir() {
  local exit_status=$?
  if (( writer_lock_owned )) && [[ -n "$writer_lock" && -d "$writer_lock" ]]; then
    rmdir -- "$writer_lock" >/dev/null 2>&1 || true
  fi
  if [[ -d "$manifest_dir" ]]; then
    rm -rf -- "$manifest_dir"
  fi
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
reconcile_publication_state() {
  local current_candidate_identity current_publish_identity

  publication_state=indeterminate
  current_publish_identity=$(directory_identity "$publish_dir") || return 1
  current_candidate_identity=$(directory_identity "$candidate_dir") || return 1
  if [[ "$current_publish_identity" == "$candidate_identity" \
      && "$current_candidate_identity" == "$previous_identity" ]]; then
    publication_state=swapped
    return 0
  fi
  if [[ "$current_publish_identity" == "$previous_identity" \
      && "$current_candidate_identity" == "$candidate_identity" ]]; then
    publication_state=original
    return 0
  fi
  return 1
}
trap cleanup_manifest_dir EXIT
trap 'handle_signal 129' HUP
trap 'handle_signal 130' INT
trap 'handle_signal 143' TERM

writer_lock=${repo_dir}.writer.lock
writer_lock_acquired=0
signal_deferral=1
if mkdir -- "$writer_lock" 2>/dev/null; then
  writer_lock_acquired=1
fi
if (( writer_lock_acquired && test_mode )) \
    && [[ ${ARCH_PKGS_PUBLISH_TEST_SIGNAL_DURING_WRITER_LOCK_ACQUISITION:-0} == 1 ]]; then
  kill -TERM $$
fi
(( writer_lock_acquired )) && writer_lock_owned=1
finish_signal_deferral
(( writer_lock_acquired )) \
  || die "another repository writer appears to be active: $writer_lock"

staging_manifest=${manifest_dir}/staging.json
candidate_manifest=${manifest_dir}/candidate.json
published_manifest=${manifest_dir}/published.json
write_repo_manifest "$repo_dir" "$staging_manifest"
staging_manifest_sha256=$(sha256sum -- "$staging_manifest" | awk '{print $1}')

publish_parent=${publish_dir:h}
publish_leaf=${publish_dir:t}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
candidate_dir=${publish_parent}/.${publish_leaf}.candidate.${timestamp}.$$
previous_dir=${publish_parent}/${publish_leaf}.previous.${timestamp}.$$
failed_dir=${publish_parent}/.${publish_leaf}.failed.${timestamp}.$$
lock_dir=${publish_parent}/.${publish_leaf}.publish.lock
probe_a=${publish_parent}/.${publish_leaf}.exchange-probe-a.$$
probe_b=${publish_parent}/.${publish_leaf}.exchange-probe-b.$$
had_previous=0
publication_created=0
first_publication_indeterminate=0

cleanup_publication() {
  local exit_status=$?
  local cleanup_safe=1
  local rollback_copy_identity
  local first_rollback_ok=1

  if (( had_previous )) && [[ "$publication_state" == indeterminate ]]; then
    reconcile_publication_state >/dev/null 2>&1 || true
  fi
  if (( had_previous )) && [[ "$publication_state" == swapped ]] \
      && [[ -e "$candidate_dir" && -e "$publish_dir" ]]; then
    publication_state=indeterminate
    if privileged mv --exchange --no-copy --no-target-directory -- "$candidate_dir" "$publish_dir" \
        >/dev/null 2>&1; then
      reconcile_publication_state >/dev/null 2>&1 || true
    fi
  fi
  if (( had_previous )) && [[ "$publication_state" == verified_unretained ]]; then
    cleanup_safe=0
    print -u2 -- "verified publication is live but previous-repository retention is incomplete; preserving repository locks and transaction paths for recovery"
  elif (( had_previous )) && [[ "$publication_state" != original ]]; then
    cleanup_safe=0
    print -u2 -- "publication state is indeterminate; preserving repository locks and transaction paths for recovery"
  fi
  if (( publication_created && ! had_previous && ! first_publication_indeterminate )) \
      && [[ -e "$publish_dir" ]]; then
    if (( test_mode )) \
        && [[ ${ARCH_PKGS_PUBLISH_TEST_FAIL_FIRST_ROLLBACK:-0} == 1 ]]; then
      first_rollback_ok=0
    else
      move_to_unused_path "$publish_dir" "$failed_dir" >/dev/null 2>&1 || true
      first_rollback_ok=0
      if [[ ! -e "$publish_dir" && -d "$failed_dir" ]]; then
        rollback_copy_identity=
        if rollback_copy_identity=$(directory_identity "$failed_dir") \
            && [[ "$rollback_copy_identity" == "$candidate_identity" ]]; then
          first_rollback_ok=1
        fi
      fi
    fi
    if (( first_rollback_ok )); then
      publication_created=0
      first_publication_indeterminate=0
    else
      cleanup_safe=0
      print -u2 -- "first publication could not be rolled back; preserving repository locks for recovery"
    fi
  fi
  if (( first_publication_indeterminate )); then
    cleanup_safe=0
    print -u2 -- "first-publication recovery state is indeterminate; preserving repository locks and transaction paths for recovery"
  fi
  privileged rmdir -- "$probe_a" "$probe_b" >/dev/null 2>&1 || true
  if (( cleanup_safe && destination_lock_owned )); then
    privileged rmdir -- "$lock_dir" >/dev/null 2>&1 || true
  fi
  if (( cleanup_safe )); then
    if (( writer_lock_owned )) && [[ -d "$writer_lock" ]]; then
      rmdir -- "$writer_lock" >/dev/null 2>&1 || true
    fi
  fi
  if (( cleanup_safe )) && [[ -d "$manifest_dir" ]]; then
    rm -rf -- "$manifest_dir"
  elif [[ -d "$manifest_dir" ]]; then
    print -u2 -- "recovery manifests preserved at: $manifest_dir"
  fi
  return $exit_status
}
trap cleanup_publication EXIT

privileged install -d -- "$publish_parent"
destination_lock_acquired=0
signal_deferral=1
if privileged mkdir -- "$lock_dir" 2>/dev/null; then
  destination_lock_acquired=1
fi
if (( destination_lock_acquired && test_mode )) \
    && [[ ${ARCH_PKGS_PUBLISH_TEST_SIGNAL_AFTER_DESTINATION_LOCK:-0} == 1 ]]; then
  kill -TERM $$
fi
(( destination_lock_acquired )) && destination_lock_owned=1
finish_signal_deferral
(( destination_lock_acquired )) \
  || die "another publication appears to be active: $lock_dir"

typeset -a retained_previous
retained_previous=(${publish_parent}/${publish_leaf}.previous.*(N/))
if [[ -e "$publish_dir" ]] && (( ${#retained_previous} >= publish_retention )); then
  die "retained previous-repository limit reached (${publish_retention}); preserve or remove an accepted old copy before publishing"
fi

privileged mkdir -- "$probe_a" "$probe_b"
if ! privileged mv --exchange --no-copy --no-target-directory -- "$probe_a" "$probe_b"; then
  die "target filesystem does not support atomic repository exchange"
fi
privileged rmdir -- "$probe_a" "$probe_b"

privileged install -d -m 0755 -- "$candidate_dir"
privileged rsync -a --delete -- "${repo_dir}/" "${candidate_dir}/"
write_repo_manifest "$candidate_dir" "$candidate_manifest"
cmp -s -- "$staging_manifest" "$candidate_manifest" \
  || die "candidate repository does not match verified staging; candidate retained at $candidate_dir"

if [[ -e "$publish_dir" ]]; then
  had_previous=1
  previous_identity=$(directory_identity "$publish_dir")
  candidate_identity=$(directory_identity "$candidate_dir")
  exchange_status=0
  identity_status=0
  publication_state=indeterminate
  signal_deferral=1
  privileged mv --exchange --no-copy --no-target-directory -- "$candidate_dir" "$publish_dir" \
    || exchange_status=$?
  if (( test_mode )) \
      && [[ ${ARCH_PKGS_PUBLISH_TEST_SIGNAL_DURING_PROMOTION:-0} == 1 ]]; then
    kill -TERM $$
  fi
  if (( test_mode )) \
      && [[ ${ARCH_PKGS_PUBLISH_TEST_FAIL_IDENTITY_AFTER_PROMOTION:-0} == 1 ]]; then
    identity_status=1
  elif ! reconcile_publication_state; then
    identity_status=1
  fi
  finish_signal_deferral
  (( ! identity_status )) \
    || die "could not identify the published repository after atomic exchange"
  [[ "$publication_state" == swapped ]] \
    || die "could not atomically exchange candidate and published repositories (status ${exchange_status})"
else
  candidate_identity=$(directory_identity "$candidate_dir")
  promotion_status=0
  promotion_complete=0
  promotion_no_effect=0
  publication_created=1
  first_publication_indeterminate=1
  move_to_unused_path "$candidate_dir" "$publish_dir" \
    || promotion_status=$?
  if [[ ! -e "$candidate_dir" && -d "$publish_dir" ]]; then
    current_publish_identity=
    if current_publish_identity=$(directory_identity "$publish_dir") \
        && [[ "$current_publish_identity" == "$candidate_identity" ]]; then
      promotion_complete=1
      first_publication_indeterminate=0
    fi
  elif [[ ! -e "$publish_dir" && -d "$candidate_dir" ]]; then
    current_candidate_identity=
    if current_candidate_identity=$(directory_identity "$candidate_dir") \
        && [[ "$current_candidate_identity" == "$candidate_identity" ]]; then
      promotion_no_effect=1
      publication_created=0
      first_publication_indeterminate=0
    fi
  fi
  (( promotion_complete || promotion_status )) || promotion_status=1
  if (( promotion_no_effect )); then
    publication_created=0
    die "could not promote candidate repository (status ${promotion_status})"
  fi
  (( promotion_complete )) \
    || die "could not identify the repository after first publication promotion (status ${promotion_status})"
fi

if (( test_mode )) && [[ ${ARCH_PKGS_PUBLISH_TEST_SIGNAL_AFTER_PROMOTION:-0} == 1 ]]; then
  kill -TERM $$
fi

signal_deferral=1
post_promotion_verified=1
write_repo_manifest "$publish_dir" "$published_manifest" \
  || post_promotion_verified=0
if (( post_promotion_verified )) \
    && ! cmp -s -- "$staging_manifest" "$published_manifest"; then
  post_promotion_verified=0
fi

if (( ! post_promotion_verified )); then
  finish_signal_deferral
  if (( had_previous )); then
    restore_status=0
    identity_status=0
    publication_state=indeterminate
    signal_deferral=1
    privileged mv --exchange --no-copy --no-target-directory -- "$candidate_dir" "$publish_dir" \
      || restore_status=$?
    if (( test_mode )) \
        && [[ ${ARCH_PKGS_PUBLISH_TEST_SIGNAL_DURING_RESTORATION:-0} == 1 ]]; then
      kill -TERM $$
    fi
    if (( test_mode )) \
        && [[ ${ARCH_PKGS_PUBLISH_TEST_FAIL_IDENTITY_AFTER_RESTORATION:-0} == 1 ]]; then
      identity_status=1
    elif ! reconcile_publication_state; then
      identity_status=1
    fi
    finish_signal_deferral
    (( ! identity_status )) \
      || die "published verification failed and the restored repository could not be identified"
    [[ "$publication_state" == original ]] \
      || die "published verification failed and the previous repository could not be restored (status ${restore_status})"
    restored_failed_copy_status=0
    restored_failed_copy_retained=0
    move_to_unused_path "$candidate_dir" "$failed_dir" \
      || restored_failed_copy_status=$?
    if [[ ! -e "$candidate_dir" && -d "$failed_dir" ]]; then
      restored_failed_copy_identity=
      if restored_failed_copy_identity=$(directory_identity "$failed_dir") \
          && [[ "$restored_failed_copy_identity" == "$candidate_identity" ]]; then
        restored_failed_copy_retained=1
      fi
    fi
    (( restored_failed_copy_retained || restored_failed_copy_status )) \
      || restored_failed_copy_status=1
    (( restored_failed_copy_retained )) \
      || die "previous repository was restored but failed candidate retention could not be identified (status ${restored_failed_copy_status}); candidate: $candidate_dir; failed destination: $failed_dir"
    die "published repository failed post-promotion verification; previous repository restored; failed copy retained at $failed_dir"
  fi
  failed_copy_status=0
  first_publication_indeterminate=1
  move_to_unused_path "$publish_dir" "$failed_dir" \
    || failed_copy_status=$?
  if [[ ! -e "$publish_dir" && -d "$failed_dir" ]]; then
    failed_copy_identity=
    if failed_copy_identity=$(directory_identity "$failed_dir") \
        && [[ "$failed_copy_identity" == "$candidate_identity" ]]; then
      publication_created=0
      first_publication_indeterminate=0
    fi
  fi
  (( ! first_publication_indeterminate || failed_copy_status )) \
    || failed_copy_status=1
  (( ! first_publication_indeterminate )) \
    || die "published verification failed and the failed repository could not be identified (status ${failed_copy_status}); published: $publish_dir; failed destination: $failed_dir"
  die "published repository failed post-promotion verification; no previous repository existed; failed copy retained at $failed_dir"
fi

if (( had_previous )); then
  retention_status=0
  retention_complete=0
  publication_state=verified_unretained
  move_to_unused_path "$candidate_dir" "$previous_dir" \
    || retention_status=$?
  if (( test_mode )) \
      && [[ ${ARCH_PKGS_PUBLISH_TEST_SIGNAL_DURING_RETENTION_FINALIZATION:-0} == 1 ]]; then
    kill -TERM $$
  fi
  if [[ ! -e "$candidate_dir" && -d "$previous_dir" ]]; then
    current_publish_identity=
    retained_previous_identity=
    if current_publish_identity=$(directory_identity "$publish_dir") \
        && retained_previous_identity=$(directory_identity "$previous_dir") \
        && [[ "$current_publish_identity" == "$candidate_identity" \
        && "$retained_previous_identity" == "$previous_identity" ]]; then
      retention_complete=1
      publication_state=original
    fi
  fi
  (( retention_complete || retention_status )) || retention_status=1
  finish_signal_deferral
  (( retention_complete )) \
    || die "verified repository was published but the previous repository could not be retained (status ${retention_status})"
  print -- "Retained previous pacman repo: $previous_dir"
else
  if (( test_mode )) \
      && [[ ${ARCH_PKGS_PUBLISH_TEST_SIGNAL_DURING_FIRST_FINALIZATION:-0} == 1 ]]; then
    kill -TERM $$
  fi
  publication_created=0
  finish_signal_deferral
fi
print -- "Published verified pacman repo: $publish_dir"
print -- "Verified repository-manifest SHA-256: $staging_manifest_sha256"
