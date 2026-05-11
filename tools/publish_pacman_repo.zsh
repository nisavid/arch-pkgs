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

validate_repo_name() {
  [[ "$repo_name" =~ '^[A-Za-z0-9._-]+$' ]] || die "repo name contains unsupported characters: $repo_name"
  [[ "$repo_name" != "." && "$repo_name" != ".." ]] || die "repo name must not be a path segment: $repo_name"
}

validate_publish_dir() {
  local component path rel

  [[ -n "$publish_dir" ]] || die "publish dir must not be empty"
  [[ "$publish_dir" != "/" ]] || die "publish dir must not be /"
  [[ "$publish_dir" == /srv/pacman/* ]] || die "publish dir must be under /srv/pacman: $publish_dir"
  [[ "$publish_dir" != "$repo_dir" ]] || die "publish dir must differ from repo dir: $publish_dir"

  rel=${publish_dir#/srv/pacman/}
  path=/srv/pacman
  for component in ${(s:/:)rel}; do
    path=${path}/${component}
    [[ ! -L "$path" ]] || die "publish dir must not contain symlink components under /srv/pacman: $path"
  done
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
  need_command sudo
  need_command rsync
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
  print -r -- "DRY-RUN: would run: sudo install -d -- ${(q)publish_dir}"
  print -r -- "DRY-RUN: would run: sudo rsync -a --delete -- ${(q)repo_dir}/ ${(q)publish_dir}/"
  exit 0
fi

sudo install -d -- "$publish_dir"
sudo rsync -a --delete -- "${repo_dir}/" "${publish_dir}/"

print -- "Published pacman repo: $publish_dir"
