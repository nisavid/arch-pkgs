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
dry_run=0
build_command=(make build-app pacman)

usage() {
  cat <<EOF
Usage: ${script_name} [--dry-run] [--source-dir DIR] [--repo-dir DIR] [--repo-name NAME]

Ingest the codex-app pacman package built by codex-app-linux.

Policy:
  - Use a codex-app package from source-dir/dist if it is newer than 24 hours.
  - Otherwise run 'make build-app pacman' in source-dir, then ingest the newest package.
  - If source-dir is missing, clone ${upstream_url} first.

Options:
  --dry-run  Print the paths inspected and actions that would run without
             cloning, building, staging, removing, or updating the repo db.
EOF
}

die() {
  print -ru2 -- "$*"
  exit 2
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

plan() {
  print -r -- "DRY-RUN: $*"
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
    if (( dry_run )); then
      plan "source dir exists: $source_dir"
    fi
    git -C "$source_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
      || die "source dir is not a git checkout: $source_dir"
    if (( dry_run )); then
      plan "validated source dir is a git checkout"
    fi
    return
  fi

  if (( dry_run )); then
    plan "source dir is absent: $source_dir"
    plan "would create parent directory: ${source_dir:h}"
    plan "would clone $upstream_url into $source_dir"
    cloned_source=1
    return
  fi

  mkdir -p -- "${source_dir:h}"
  print -ru2 -- "Cloning codex-app-linux into $source_dir"
  git clone "$upstream_url" "$source_dir"
  cloned_source=1
}

build_package() {
  if (( dry_run )); then
    plan "would run '${build_command[*]}' in $source_dir"
    return
  fi

  print -ru2 -- "No codex-app package newer than ${max_age_hours}h; running ${build_command[*]}"
  (cd -- "$source_dir" && "${build_command[@]}")
}

stage_package() {
  local package_path=$1
  local repo_db=${repo_dir}/${repo_name}.db.tar.zst
  local staged_path=${repo_dir}/${package_path:t}
  local package_name

  if (( dry_run )); then
    plan "would ensure repo dir exists: $repo_dir"
    if [[ -e "$package_path" ]]; then
      package_name=$(pacman -Qp -- "$package_path" | awk '{print $1}')
      [[ "$package_name" == codex-app ]] || die "expected codex-app package, got: $package_name"
      plan "verified package name from artifact: $package_name"
    else
      plan "would verify package name is codex-app once artifact exists: $package_path"
    fi

    if [[ -e "$repo_db" ]]; then
      plan "would remove existing codex-app entry from repo db: $repo_db"
    else
      plan "repo db does not exist yet: $repo_db"
    fi

    local existing_archive existing_meta existing_name removed_any=0
    for existing_archive in "$repo_dir"/*.pkg.tar.*(N); do
      existing_meta=$(pacman -Qp -- "$existing_archive" 2>/dev/null) || continue
      existing_name=${existing_meta%% *}
      if [[ "$existing_name" == codex-app ]]; then
        plan "would remove existing staged codex-app archive: $existing_archive"
        removed_any=1
      fi
    done
    (( removed_any )) || plan "no existing staged codex-app archives found in $repo_dir"

    plan "would stage artifact at: $staged_path"
    plan "would hard-link artifact, falling back to copy if needed"
    plan "would update pacman repo db with repo-add: $repo_db"
    return
  fi

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
      --dry-run)
        dry_run=1
        shift
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
  need_command pacman
  if (( ! dry_run )); then
    need_command make
    need_command repo-add
    need_command repo-remove
  fi

  if (( dry_run )); then
    print -r -- "Dry run for ${script_name}"
    plan "repo root: $repo_root"
    plan "source dir: $source_dir"
    plan "dist dir: ${source_dir}/dist"
    plan "repo dir: $repo_dir"
    plan "repo db: ${repo_dir}/${repo_name}.db.tar.zst"
    plan "repo name: $repo_name"
    plan "freshness window: ${max_age_hours} hours"
    plan "build command when no fresh artifact exists: ${build_command[*]}"
    plan "upstream clone URL: $upstream_url"
  fi

  ensure_source_dir

  local package_path
  if (( cloned_source )); then
    build_package
    if (( dry_run )); then
      plan "would look for newest codex-app package in ${source_dir}/dist after clone/build"
      package_path="${source_dir}/dist/codex-app-*.pkg.tar.zst"
    else
      package_path=$(latest_package "${source_dir}/dist" 0 || true)
    fi
  else
    if (( dry_run )); then
      plan "looking for codex-app package newer than ${max_age_hours} hours in ${source_dir}/dist"
    fi
    package_path=$(latest_package "${source_dir}/dist" $(( max_age_hours * 60 )) || true)
    if [[ -z "$package_path" ]]; then
      if (( dry_run )); then
        plan "no fresh codex-app package found in ${source_dir}/dist"
      fi
      build_package
      if (( dry_run )); then
        package_path=$(latest_package "${source_dir}/dist" 0 || true)
        if [[ -n "$package_path" ]]; then
          plan "newest existing package currently in dist, before the would-run build: $package_path"
        else
          plan "would look for newest codex-app package in ${source_dir}/dist after build"
          package_path="${source_dir}/dist/codex-app-*.pkg.tar.zst"
        fi
      else
        package_path=$(latest_package "${source_dir}/dist" 0 || true)
      fi
    elif (( dry_run )); then
      plan "fresh package selected: $package_path"
    fi
  fi

  [[ -n "$package_path" ]] || die "no codex-app package found in ${source_dir}/dist"
  stage_package "$package_path"
}

main "$@"
