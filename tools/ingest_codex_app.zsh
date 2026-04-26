#!/usr/bin/env zsh

emulate -L zsh
setopt errexit nounset pipefail

script_dir=${0:A:h}
script_name=${0:t}
repo_root=${script_dir:h}
source_dir=${CODEX_APP_LINUX_DIR:-${repo_root}/upstream/codex-app-linux}
repo_dir=${repo_root}/repo/x86_64
repo_name=nisavid
upstream_url=https://github.com/nisavid/codex-app-linux.git
max_age_hours=24
cloned_source=0

usage() {
  cat <<EOF
Usage: ${script_name} [--source-dir DIR] [--repo-dir DIR] [--repo-name NAME]

Ingest the codex-app pacman package built by codex-app-linux.

Policy:
  - Use a codex-app package from source-dir/dist if it is newer than 24 hours.
  - Otherwise run 'make pacman' in source-dir, then ingest the newest package.
  - If source-dir is missing, clone ${upstream_url} first.
EOF
}

die() {
  print -ru2 -- "$*"
  exit 2
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

latest_package() {
  emulate -L zsh
  setopt errexit nounset pipefail

  local dist_dir=$1
  local max_minutes=${2:-0}
  local -a find_cmd

  [[ -d "$dist_dir" ]] || return 1

  find_cmd=(
    find "$dist_dir" -maxdepth 1 -type f
    '(' -name 'codex-app-*.pkg.tar.zst' -o -name 'codex-app-*.pkg.tar.xz' ')'
  )
  if (( max_minutes > 0 )); then
    find_cmd+=(-mmin "-${max_minutes}")
  fi
  find_cmd+=(-printf '%T@ %p\n')

  "${find_cmd[@]}" \
    | sort -nr \
    | sed -n '1{s/^[^ ]* //;p;}'
}

ensure_source_dir() {
  if [[ -e "$source_dir" ]]; then
    git -C "$source_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
      || die "source dir is not a git checkout: $source_dir"
    return
  fi

  mkdir -p -- "${source_dir:h}"
  print -ru2 -- "Cloning codex-app-linux into $source_dir"
  git clone "$upstream_url" "$source_dir"
  cloned_source=1
}

build_package() {
  print -ru2 -- "No codex-app package newer than ${max_age_hours}h; running make pacman"
  (cd -- "$source_dir" && make pacman)
}

stage_package() {
  local package_path=$1
  local repo_db=${repo_dir}/${repo_name}.db.tar.zst
  local staged_path=${repo_dir}/${package_path:t}
  local package_name

  mkdir -p -- "$repo_dir"

  package_name=$(pacman -Qp -- "$package_path" | awk '{print $1}')
  [[ "$package_name" == codex-app ]] || die "expected codex-app package, got: $package_name"

  if [[ -e "$repo_db" ]]; then
    repo-remove "$repo_db" codex-app >/dev/null 2>&1 || true
  fi

  local existing_archive existing_meta existing_name
  for existing_archive in "$repo_dir"/*.pkg.tar.*(N); do
    existing_meta=$(pacman -Qp -- "$existing_archive" 2>/dev/null) || continue
    existing_name=${existing_meta%% *}
    if [[ "$existing_name" == codex-app ]]; then
      rm -f -- "$existing_archive"
    fi
  done

  rm -f -- "$staged_path"
  ln -- "$package_path" "$staged_path" 2>/dev/null || cp -f -- "$package_path" "$staged_path"
  repo-add "$repo_db" "$staged_path" >/dev/null

  print -- "Updated pacman repo: $repo_db"
  print -- "Staged package: ${staged_path:t}"
}

main() {
  while (( $# )); do
    case "$1" in
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
      -h|--help)
        usage
        return 0
        ;;
      *)
        die "unknown argument: $1"
        ;;
    esac
  done

  need_command git
  need_command make
  need_command pacman
  need_command repo-add
  need_command repo-remove

  ensure_source_dir

  local package_path
  if (( cloned_source )); then
    build_package
    package_path=$(latest_package "${source_dir}/dist" 0 || true)
  else
    package_path=$(latest_package "${source_dir}/dist" $(( max_age_hours * 60 )) || true)
    if [[ -z "$package_path" ]]; then
      build_package
      package_path=$(latest_package "${source_dir}/dist" 0 || true)
    fi
  fi

  [[ -n "$package_path" ]] || die "no codex-app package found in ${source_dir}/dist"
  stage_package "$package_path"
}

main "$@"
