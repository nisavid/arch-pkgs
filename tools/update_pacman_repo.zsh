#!/usr/bin/env zsh

emulate -L zsh
setopt errexit nounset pipefail

script_dir=${0:A:h}
repo_root=${script_dir:h}
repo_dir=${repo_root}/repo/x86_64
repo_name=nisavid

usage() {
  cat <<EOF
Usage: ${0:t} [--repo-dir DIR] [--repo-name NAME] <package-dir>...

Refresh a local pacman repo from built package archives named by each package
directory's current PKGBUILD.

Build package archives first with:
  (cd packages/<pkgname> && makepkg -f)
EOF
}

die() {
  print -u2 -- "$*"
  exit 2
}

typeset -a package_dirs

while (( $# )); do
  case "$1" in
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
      exit 0
      ;;
    --)
      shift
      package_dirs+=("$@")
      break
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      package_dirs+=("$1")
      shift
      ;;
  esac
done

(( $#package_dirs )) || {
  usage
  exit 2
}

mkdir -p -- "$repo_dir"

typeset -a package_paths
typeset -A targeted_names
typeset -A staged_paths

for package_dir in "${package_dirs[@]}"; do
  package_dir=${package_dir:A}
  [[ -f "$package_dir/PKGBUILD" ]] || die "missing PKGBUILD in $package_dir"

  package_list=("${(@f)$(cd -- "$package_dir" && makepkg --packagelist)}")
  (( $#package_list )) || die "makepkg --packagelist returned no archives for $package_dir"

  for package_path in "${package_list[@]}"; do
    [[ "$package_path" = /* ]] || package_path=${package_dir}/${package_path}
    [[ -f "$package_path" ]] || die "expected package archive is missing: $package_path"
    staged_path=${repo_dir}/${package_path:t}
    if [[ -z ${staged_paths[$staged_path]-} ]]; then
      package_paths+=("$package_path")
      staged_paths[$staged_path]=1
    fi
  done

  package_names=("${(@f)$(cd -- "$package_dir" && makepkg --printsrcinfo | sed -n 's/^[[:space:]]*pkgname = //p')}")
  (( $#package_names )) || die "could not determine package names for $package_dir"

  for package_name in "${package_names[@]}"; do
    targeted_names[$package_name]=1
  done
done

repo_db=${repo_dir}/${repo_name}.db.tar.zst

if [[ -e "$repo_db" ]]; then
  for package_name in ${(k)targeted_names}; do
    repo-remove "$repo_db" "$package_name" >/dev/null 2>&1 || true
  done
fi

for existing_archive in "$repo_dir"/*.pkg.tar.*(N); do
  package_meta=$(pacman -Qp -- "$existing_archive" 2>/dev/null) || continue
  existing_name=${package_meta%% *}
  if [[ -n ${targeted_names[$existing_name]-} ]]; then
    rm -f -- "$existing_archive"
  fi
done

typeset -a repo_packages

for package_path in "${package_paths[@]}"; do
  staged_path=${repo_dir}/${package_path:t}
  rm -f -- "$staged_path"
  ln -- "$package_path" "$staged_path" 2>/dev/null || cp -f -- "$package_path" "$staged_path"
  repo_packages+=("$staged_path")
done

(( $#repo_packages )) || die "no package archives staged for ${repo_name}"

repo-add "$repo_db" "${repo_packages[@]}" >/dev/null

print -- "Updated pacman repo: $repo_db"
print -- "Staged packages:"
for staged_path in "${repo_packages[@]}"; do
  print -- "  ${staged_path:t}"
done
