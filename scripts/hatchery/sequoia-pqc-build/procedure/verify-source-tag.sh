#!/usr/bin/bash
set -Eeuo pipefail

(( $# == 8 )) || {
  printf 'usage: %s BOUNDARY_ROOT CONTROLLER_VIEW MANIFEST TAG EXPECTED_TAG_OBJECT EXPECTED_COMMIT GNUPGHOME RECEIPT\n' "$0" >&2
  exit 2
}
boundary_root=$(realpath -- "$1")
view=$(realpath -- "$2")
manifest=$(realpath -- "$3")
tag=$4
expected_tag_object=$5
expected_commit=$6
controller_gnupg=$(realpath -- "$7")
receipt=$8

[[ -d $boundary_root && -d $view && ! -L $view && -f $manifest ]]
[[ -d $controller_gnupg && $view == "$boundary_root"/* ]]
[[ $manifest == "$boundary_root"/* && $controller_gnupg == "$boundary_root"/* ]]
[[ $receipt == "$boundary_root"/* && ! -e $receipt ]]
[[ $expected_tag_object =~ ^[0-9a-f]{40}$ && $expected_commit =~ ^[0-9a-f]{40}$ ]]

relative_manifest=${manifest#"$boundary_root/"}
git_command=(
  env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 HOME="$boundary_root"
  GNUPGHOME="$controller_gnupg" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
  GIT_NO_REPLACE_OBJECTS=1 GIT_TERMINAL_PROMPT=0 /usr/bin/git --no-replace-objects
  -c gpg.format=openpgp -c gpg.program=/usr/bin/gpg
  -c gpg.openpgp.program=/usr/bin/gpg --git-dir="$view"
)
{
  printf 'schema=arch-pq-controller-tag-verification-v1\n'
  (cd "$boundary_root" && sha256sum -c "$relative_manifest")
  tag_object=$("${git_command[@]}" rev-parse "$tag^{tag}")
  source_commit=$("${git_command[@]}" rev-parse "$tag^{commit}")
  printf 'tag=%s\ntag_object=%s\nsource_commit=%s\n' "$tag" "$tag_object" "$source_commit"
  [[ $tag_object == "$expected_tag_object" && $source_commit == "$expected_commit" ]]
  "${git_command[@]}" verify-tag --raw "$tag"
} >"$receipt" 2>&1
grep -Eq '\[GNUPG:\] VALIDSIG (8F17777118A33DDA9BA48E62AACB3243630052D9|C03FA6411B03AE12576461187223B56678E02528 .* 8F17777118A33DDA9BA48E62AACB3243630052D9)' \
  "$receipt"
printf 'tag_verification_exit=0\n' >>"$receipt"
