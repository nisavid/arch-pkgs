#!/usr/bin/bash
set -Eeuo pipefail
export LC_ALL=C

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
admission="$root/review-admission"
revision_file="$admission/source-revision.txt"
inventory="$admission/maintained-source.inventory.tsv"
header=$'type\tmode\tbytes\tsha256\trepository_path\tstaged_path'

[[ -d $admission && ! -L $admission ]]
[[ -f $revision_file && ! -L $revision_file ]]
[[ -f $inventory && ! -L $inventory ]]
[[ $(find "$admission" -mindepth 1 -maxdepth 1 -type f | wc -l) == 2 ]]
[[ -z $(find "$admission" -mindepth 1 -maxdepth 1 ! -type f -print -quit) ]]

mapfile -t revision_lines <"$revision_file"
[[ ${#revision_lines[@]} == 1 && ${revision_lines[0]} =~ ^[0-9a-f]{40}$ ]]
IFS= read -r actual_header <"$inventory"
[[ $actual_header == "$header" ]]
awk -F'\t' 'NR > 1 && NF != 6 { exit 1 }' "$inventory"

declare -A admitted=()
previous=
row_count=0
while IFS=$'\t' read -r type mode bytes sha256 repository_path staged_path extra; do
  [[ -z $extra && -n $staged_path ]]
  [[ $type == file && $mode =~ ^[0-7]{3,4}$ && $bytes =~ ^(0|[1-9][0-9]*)$ ]]
  [[ $sha256 =~ ^[0-9a-f]{64}$ ]]
  [[ $repository_path != *$'\n'* && $staged_path != *$'\n'* ]]
  [[ $staged_path != /* && $staged_path != *'/../'* && $staged_path != ../* && $staged_path != */.. ]]
  case $staged_path in
    procedure/*|tests/*)
      expected_repository_path="scripts/hatchery/sequoia-pqc-build/$staged_path"
      ;;
    recipes/*)
      expected_repository_path="packages/${staged_path#recipes/}"
      ;;
    *)
      printf 'unrecognized staged source path: %s\n' "$staged_path" >&2
      exit 1
      ;;
  esac
  [[ $repository_path == "$expected_repository_path" ]]
  [[ -z ${admitted[$staged_path]-} ]]
  [[ -z $previous || $previous < $staged_path ]]
  staged_file="$root/$staged_path"
  [[ -f $staged_file && ! -L $staged_file ]]
  canonical=$(realpath -e -- "$staged_file")
  [[ $canonical == "$staged_file" && $canonical == "$root"/* ]]
  [[ $(stat -c %a "$staged_file") == "$mode" ]]
  [[ $(stat -c %s "$staged_file") == "$bytes" ]]
  [[ $(sha256sum "$staged_file" | cut -d' ' -f1) == "$sha256" ]]
  admitted[$staged_path]=1
  previous=$staged_path
  row_count=$((row_count + 1))
done < <(tail -n +2 "$inventory")

actual_count=0
for maintained_root in procedure recipes tests; do
  [[ -d $root/$maintained_root && ! -L $root/$maintained_root ]]
  [[ -z $(find "$root/$maintained_root" -mindepth 1 ! -type f ! -type d -print -quit) ]]
done
while IFS= read -r -d '' staged_file; do
  relative=${staged_file#"$root/"}
  [[ $relative != *$'\t'* && $relative != *$'\n'* ]]
  [[ -n ${admitted[$relative]-} ]]
  actual_count=$((actual_count + 1))
done < <(find "$root/procedure" "$root/recipes" "$root/tests" -type f -print0 | LC_ALL=C sort -z)
[[ $row_count == "$actual_count" ]]
