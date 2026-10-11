#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
manifest="$root/control/frozen-boundary.sha256"
inventory="$root/control/frozen-boundary.inventory.tsv"

[[ -f $manifest && ! -L $manifest && -f $inventory && ! -L $inventory ]]
/usr/bin/bash "$root/procedure/verify-reviewed-source.sh"
for maintained_root in procedure recipes tests review-admission; do
  [[ -d $root/$maintained_root && ! -L $root/$maintained_root ]]
  [[ -z $(find "$root/$maintained_root" -mindepth 1 ! -type f ! -type d -print -quit) ]]
done
[[ -d $root/inputs && ! -L $root/inputs ]]
[[ -d $root/inputs/rustup && ! -L $root/inputs/rustup ]]
[[ -z $(find "$root/inputs" -path "$root/inputs/rustup" -prune -o -mindepth 1 \
  ! -type f ! -type d -print -quit) ]]

current_inventory() {
  local relative canonical
  printf 'type\tmode\tbytes\tsha256\tcanonical_path\tpath\n'
  while IFS= read -r -d '' relative; do
    [[ $relative != *$'\t'* && $relative != *$'\n'* ]]
    [[ -f $root/$relative && ! -L $root/$relative ]]
    canonical=$(realpath -e -- "$root/$relative")
    [[ $canonical == "$root/$relative" && $canonical == "$root"/* ]]
    printf 'file\t%s\t%s\t%s\t%s\t%s\n' \
      "$(stat -c %a "$root/$relative")" "$(stat -c %s "$root/$relative")" \
      "$(sha256sum "$root/$relative" | cut -d' ' -f1)" "$canonical" "$relative"
  done < <(
    cd "$root"
    find procedure recipes tests inputs review-admission -type f -print0 | LC_ALL=C sort -z
  )
}

diff -u "$inventory" <(current_inventory)
(cd "$root" && sha256sum -c control/frozen-boundary.sha256)
