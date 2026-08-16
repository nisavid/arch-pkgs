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
[[ "$test_mode" == 0 || "$test_mode" == 1 ]] \
  || { print -u2 -- "ARCH_PKGS_PUBLISH_TEST_MODE must be 0 or 1"; exit 2; }

usage() {
  local default_publish_dir=${publish_dir:-/srv/pacman/${repo_name}/x86_64}
  cat <<EOF
Usage: ${script_name} [--dry-run] [--repo-dir DIR] [--repo-name NAME] [--publish-dir DIR]

Publish the checkout-local pacman repo to the pacman-visible system path.

Defaults:
  repo-dir:     ${repo_dir}
  repo-name:    ${repo_name}
  publish-dir: ${default_publish_dir}
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
import sys
from pathlib import Path

root = Path(sys.argv[1])
entries = []
for path in sorted(root.iterdir(), key=lambda item: os.fsencode(item.name)):
    # Pacman repository publication is intentionally flat; never recurse.
    metadata = path.lstat()
    if path.is_symlink():
        target = os.readlink(path)
        if "/" in target or target in ("", ".", ".."):
            raise SystemExit(f"unsafe repository symlink: {path.name} -> {target}")
        if not (root / target).is_file():
            raise SystemExit(f"repository symlink target is missing: {path.name} -> {target}")
        entries.append({"name": path.name, "target": target, "type": "symlink"})
    elif path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        entries.append(
            {
                "name": path.name,
                "sha256": digest.hexdigest(),
                "size": metadata.st_size,
                "type": "file",
            }
        )
    else:
        raise SystemExit(f"unsupported repository entry: {path.name}")

print(json.dumps({"entries": entries, "schemaVersion": 1}, indent=2, sort_keys=True))
PY
}

validate_repo_name() {
  [[ "$repo_name" =~ '^[A-Za-z0-9._-]+$' ]] || die "repo name contains unsupported characters: $repo_name"
  [[ "$repo_name" != "." && "$repo_name" != ".." ]] || die "repo name must not be a path segment: $repo_name"
}

validate_publish_dir() {
  local component path rel

  [[ -n "$publish_dir" ]] || die "publish dir must not be empty"
  [[ "$publish_dir" != "/" ]] || die "publish dir must not be /"
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
    path=/tmp
  else
    rel=${publish_dir#/srv/pacman/}
    path=/srv/pacman
  fi
  for component in ${(s:/:)rel}; do
    path=${path}/${component}
    [[ ! -L "$path" ]] || die "publish dir must not contain symlink components under /srv/pacman: $path"
  done
}

privileged() {
  if (( test_mode )); then
    "$@"
  else
    sudo "$@"
  fi
}

while (( $# )); do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
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

repo_dir=${repo_dir:a}
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
cleanup_manifest_dir() {
  local exit_status=$?
  [[ -d "$manifest_dir" ]] && rm -rf -- "$manifest_dir"
  return $exit_status
}
trap cleanup_manifest_dir EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

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
had_previous=0
publication_swapped=0

privileged install -d -- "$publish_parent"
privileged mkdir -- "$lock_dir" 2>/dev/null \
  || die "another publication appears to be active: $lock_dir"
cleanup_publication() {
  local exit_status=$?

  if (( publication_swapped && had_previous )) \
      && [[ -e "$candidate_dir" && -e "$publish_dir" ]]; then
    privileged mv --exchange --no-copy --no-target-directory -- "$candidate_dir" "$publish_dir" \
      >/dev/null 2>&1 || true
  fi
  privileged rmdir -- "$lock_dir" >/dev/null 2>&1 || true
  [[ -d "$manifest_dir" ]] && rm -rf -- "$manifest_dir"
  return $exit_status
}
trap cleanup_publication EXIT

privileged install -d -m 0755 -- "$candidate_dir"
privileged rsync -a --delete -- "${repo_dir}/" "${candidate_dir}/"
write_repo_manifest "$candidate_dir" "$candidate_manifest"
cmp -s -- "$staging_manifest" "$candidate_manifest" \
  || die "candidate repository does not match verified staging; candidate retained at $candidate_dir"

if [[ -e "$publish_dir" ]]; then
  had_previous=1
  if ! privileged mv --exchange --no-copy --no-target-directory -- "$candidate_dir" "$publish_dir"; then
    die "could not atomically exchange candidate and published repositories"
  fi
  publication_swapped=1
else
  privileged mv -- "$candidate_dir" "$publish_dir" \
    || die "could not promote candidate repository"
fi

if (( test_mode )) && [[ ${ARCH_PKGS_PUBLISH_TEST_SIGNAL_AFTER_PROMOTION:-0} == 1 ]]; then
  kill -TERM $$
fi

post_promotion_verified=1
write_repo_manifest "$publish_dir" "$published_manifest" \
  || post_promotion_verified=0
if (( post_promotion_verified )) \
    && ! cmp -s -- "$staging_manifest" "$published_manifest"; then
  post_promotion_verified=0
fi

if (( ! post_promotion_verified )); then
  if (( had_previous )); then
    privileged mv --exchange --no-copy --no-target-directory -- "$candidate_dir" "$publish_dir" \
      || die "published verification failed and the previous repository could not be restored"
    publication_swapped=0
    privileged mv -- "$candidate_dir" "$failed_dir"
    die "published repository failed post-promotion verification; previous repository restored; failed copy retained at $failed_dir"
  fi
  privileged mv -- "$publish_dir" "$failed_dir"
  die "published repository failed post-promotion verification; no previous repository existed; failed copy retained at $failed_dir"
fi

if (( had_previous )); then
  privileged mv -- "$candidate_dir" "$previous_dir"
  publication_swapped=0
  print -- "Retained previous pacman repo: $previous_dir"
fi
print -- "Published verified pacman repo: $publish_dir"
print -- "Verified repository-manifest SHA-256: $staging_manifest_sha256"
