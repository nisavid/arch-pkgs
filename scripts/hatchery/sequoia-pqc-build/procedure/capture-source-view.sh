#!/usr/bin/bash
set -Eeuo pipefail

(( $# == 8 )) || {
  printf 'usage: %s BOUNDARY_ROOT SOURCE_REPOSITORY CONTROLLER_VIEW TAG EXPECTED_TAG_OBJECT EXPECTED_COMMIT RECEIPT MANIFEST\n' "$0" >&2
  exit 2
}
boundary_root=$(realpath -- "$1")
source_repo=$(realpath -- "$2")
view=$3
tag=$4
expected_tag_object=$5
expected_commit=$6
receipt=$7
manifest=$8

[[ -d $boundary_root && -d $source_repo && ! -L $source_repo ]]
[[ $source_repo == "$boundary_root"/* && $view == "$boundary_root"/* ]]
[[ $receipt == "$boundary_root"/* && $manifest == "$boundary_root"/* ]]
[[ $expected_tag_object =~ ^[0-9a-f]{40}$ && $expected_commit =~ ^[0-9a-f]{40}$ ]]
[[ ! -e $view && ! -e $receipt && ! -e $manifest ]]
mkdir -p "${view%/*}" "${receipt%/*}" "${manifest%/*}"

source_git="$source_repo/.git"
[[ -d $source_git && ! -L $source_git ]]
[[ ! -e $source_git/commondir && ! -e $source_git/gitdir ]]
[[ ! -e $source_git/objects/info/alternates && ! -e $source_git/objects/info/http-alternates ]]
[[ -z $(find "$source_git" -mindepth 1 ! -type f ! -type d -print -quit) ]]
mkdir "$view"
cp -a --no-preserve=ownership "$source_git/objects" "$source_git/refs" "$view/"
for optional in packed-refs shallow; do
  [[ ! -f $source_git/$optional ]] || cp -a --no-preserve=ownership "$source_git/$optional" "$view/"
done
printf 'ref: refs/heads/controller-source-view\n' >"$view/HEAD"

git_command=(
  env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 HOME="$boundary_root"
  GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_NO_REPLACE_OBJECTS=1
  GIT_TERMINAL_PROMPT=0 /usr/bin/git --no-replace-objects --git-dir="$view"
)
tag_object=$("${git_command[@]}" rev-parse "$tag^{tag}")
source_commit=$("${git_command[@]}" rev-parse "$tag^{commit}")
[[ $tag_object == "$expected_tag_object" && $source_commit == "$expected_commit" ]]
"${git_command[@]}" fsck --full --strict >/dev/null

find "$view" -type f -exec chmod 0444 {} +
find "$view" -type d -exec chmod 0555 {} +
relative_view=${view#"$boundary_root/"}
relative_manifest=${manifest#"$boundary_root/"}
(
  cd "$boundary_root"
  find "$relative_view" -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum \
    >"$relative_manifest"
  sha256sum -c "$relative_manifest" >/dev/null
)
printf 'schema=arch-pq-controller-source-view-v1\nsource_view=%s\ntag=%s\ntag_object=%s\nsource_commit=%s\nconfig_copied=false\nalternates_present=false\n' \
  "$relative_view" "$tag" "$tag_object" "$source_commit" >"$receipt"
