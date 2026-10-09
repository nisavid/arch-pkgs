#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT
mkdir -p "$scratch/procedure" "$scratch/review"
cp "$source_root/procedure/write-run-inventory.sh" "$scratch/procedure/"
printf 'acceptance_gate=open\n' >"$scratch/review/validation-status.txt"
/usr/bin/bash "$scratch/procedure/write-run-inventory.sh" "$scratch" \
  "$scratch/review/final-source-and-evidence.inventory.tsv"
recorded=$(awk -F'\t' '$4 == "review/validation-status.txt" { print $3 }' \
  "$scratch/review/final-source-and-evidence.inventory.tsv")
[[ $recorded == "$(sha256sum "$scratch/review/validation-status.txt" | cut -d' ' -f1)" ]]
printf 'acceptance_gate=closed\n' >"$scratch/review/validation-status.txt"
[[ $recorded != "$(sha256sum "$scratch/review/validation-status.txt" | cut -d' ' -f1)" ]]
printf 'run inventory binds validation status: PASS\n'
