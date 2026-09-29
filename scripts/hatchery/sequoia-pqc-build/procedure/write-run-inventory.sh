#!/usr/bin/bash
set -Eeuo pipefail

root=${1-}
inventory=${2-}
[[ -d $root && $inventory == "$root"/* ]]
inventory_roots=()
for candidate_root in procedure recipes tests inputs control setup-evidence attempts output review; do
  [[ -e $root/$candidate_root ]] && inventory_roots+=("$root/$candidate_root")
done
printf 'mode\tbytes\tsha256\tpath\n' >"$inventory"
while IFS= read -r -d '' path; do
  relative=${path#"$root/"}
  printf '%s\t%s\t%s\t%s\n' "$(stat -c %a "$path")" "$(stat -c %s "$path")" \
    "$(sha256sum "$path" | cut -d' ' -f1)" "$relative" >>"$inventory"
done < <(find "${inventory_roots[@]}" -type f ! -path "$inventory" -print0 | LC_ALL=C sort -z)

status="$root/review/validation-status.txt"
[[ -f $status ]]
expected=$(sha256sum "$status" | cut -d' ' -f1)
actual=$(awk -F'\t' '$4 == "review/validation-status.txt" { print $3 }' "$inventory")
[[ -n $actual && $actual == "$expected" ]]
