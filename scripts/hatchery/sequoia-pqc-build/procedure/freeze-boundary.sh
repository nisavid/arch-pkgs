#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
manifest="$root/control/frozen-boundary.sha256"
inventory="$root/control/frozen-boundary.inventory.tsv"
record="$root/control/frozen-boundary.txt"
[[ -d $root/inputs/rustup && ! -L $root/inputs/rustup && -f $root/inputs/rust-toolchain.sha256 ]]
[[ ! -e $manifest && ! -e $inventory && ! -e $record ]] || {
  printf 'frozen boundary already exists\n' >&2
  exit 2
}
/usr/bin/bash "$root/procedure/verify-reviewed-source.sh"
mkdir -p "$root/control"
(
  cd "$root"
  for maintained_root in procedure recipes tests review-admission; do
    [[ -d $maintained_root && ! -L $maintained_root ]]
    [[ -z $(find "$maintained_root" -mindepth 1 ! -type f ! -type d -print -quit) ]]
  done
  [[ -d inputs && ! -L inputs ]]
  [[ -z $(find inputs -path inputs/rustup -prune -o -mindepth 1 \
    ! -type f ! -type d -print -quit) ]]
  find procedure recipes tests inputs review-admission -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum \
    >control/frozen-boundary.sha256
  {
    printf 'type\tmode\tbytes\tsha256\tcanonical_path\tpath\n'
    while IFS= read -r -d '' path; do
      [[ $path != *$'\t'* && $path != *$'\n'* && -f $path && ! -L $path ]]
      canonical=$(realpath -e -- "$path")
      [[ $canonical == "$root/$path" && $canonical == "$root"/* ]]
      printf 'file\t%s\t%s\t%s\t%s\t%s\n' "$(stat -c %a "$path")" \
        "$(stat -c %s "$path")" "$(sha256sum "$path" | cut -d' ' -f1)" \
        "$canonical" "$path"
    done < <(find procedure recipes tests inputs review-admission -type f -print0 | LC_ALL=C sort -z)
  } >control/frozen-boundary.inventory.tsv
  /usr/bin/bash procedure/verify-frozen-boundary.sh
)
{
  printf 'schema=arch-pq-frozen-boundary-v1\n'
  printf 'manifest_path=control/frozen-boundary.sha256\nmanifest_sha256=%s\n' \
    "$(sha256sum "$manifest" | cut -d' ' -f1)"
  printf 'inventory_path=control/frozen-boundary.inventory.tsv\ninventory_sha256=%s\n' \
    "$(sha256sum "$inventory" | cut -d' ' -f1)"
  printf 'frozen_boundary_exit=0\n'
} >"$record"
chmod 444 "$manifest" "$inventory" "$record"
