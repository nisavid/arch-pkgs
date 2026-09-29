#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
(( $# == 2 )) || { printf 'usage: %s sequoia-sq-pqc=ID sequoia-sqv-pqc=ID\n' "$0" >&2; exit 2; }
out="$root/output"
prov="$out/provenance"
review="$root/review"
cleanup_receipt="$out/receipts/final-public-cache-cleanup.txt"
[[ -f $cleanup_receipt ]]
receipt_field() {
  local key=$1
  awk -F= -v key="$key" '
    $1 == key { count++; value=substr($0, length(key) + 2) }
    END { if (count != 1) exit 1; print value }
  ' "$cleanup_receipt"
}
[[ $(receipt_field schema) == arch-pq-final-public-cache-cleanup-v2 ]]
[[ $(receipt_field toolchain_preserved) == true ]]
[[ $(receipt_field cleanup_exit) == 0 ]]
mkdir -p "$prov" "$review"
sha256sum "$cleanup_receipt" >"$prov/final-public-cache-cleanup.sha256"
/usr/bin/bash "$root/procedure/verify-frozen-boundary.sh" \
  >"$prov/final-frozen-input-verification.txt" 2>&1
/usr/bin/bash "$root/procedure/verify-toolchain.sh" \
  >>"$prov/final-frozen-input-verification.txt" 2>&1

printf 'package\tattempt\tarchive_bytes\tarchive_sha256\texecutable_sha256\n' \
  >"$prov/candidate-identities.tsv"
declare -A selected=()
for selection in "$@"; do
  package=${selection%%=*}
  attempt_id=${selection#*=}
  case "$package" in
    sequoia-sq-pqc) version=1.4.0 executable=sq ;;
    sequoia-sqv-pqc) version=1.5.0 executable=sqv ;;
    *) exit 2 ;;
  esac
  [[ -z ${selected[$package]-} ]] || { printf 'duplicate package selection: %s\n' "$package" >&2; exit 2; }
  selected[$package]=1
  [[ $attempt_id =~ ^[0-9]{3}$ ]]
  attempt="$root/attempts/${package}-attempt-${attempt_id}"
  archive="$out/archives/${package}-${version}-4-x86_64.pkg.tar.zst"
  [[ -f $attempt/receipts/ACCEPTED && -f $archive ]]
  [[ $(awk -F= '$1 == "accepted" { value=$2 } END { print value }' \
    "$attempt/receipts/outer-launcher.txt") == true ]]
  grep -Fxq 'outer_exit=0' "$attempt/receipts/outer-launcher.txt"
  sha256sum -c "$attempt/receipts/output-archive.sha256"
  printf '%s\t%s\t%s\t%s\t%s\n' "$package" "$attempt_id" "$(stat -c %s "$archive")" \
    "$(sha256sum "$archive" | cut -d' ' -f1)" \
    "$(sha256sum "$attempt/extracted/usr/bin/$executable" | cut -d' ' -f1)" \
    >>"$prov/candidate-identities.tsv"
done
[[ ${selected[sequoia-sq-pqc]-0} == 1 && ${selected[sequoia-sqv-pqc]-0} == 1 ]]

printf 'status=successor-candidates-built-but-not-independently-accepted\n' >"$review/validation-status.txt"
printf 'downstream_operation_gate=open\nmacos_interoperability_gate=open\ninstallation_gate=open\nrollback_authenticity_gate=open\nacceptance_gate=open\ndeployment_gate=open\n' \
  >>"$review/validation-status.txt"
inventory="$review/final-source-and-evidence.inventory.tsv"
/usr/bin/bash "$root/procedure/write-run-inventory.sh" "$root" "$inventory"
