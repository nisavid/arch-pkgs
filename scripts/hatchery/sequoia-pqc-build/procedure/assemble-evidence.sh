#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
(( $# == 2 )) || { printf 'usage: %s sequoia-sq-pqc=ID sequoia-sqv-pqc=ID\n' "$0" >&2; exit 2; }
out="$root/output"
prov="$out/provenance"
review="$root/review"
lifecycle_admission_sha256=$(
  /usr/bin/bash "$root/procedure/lifecycle-admission.sh" verify
)
cleanup_receipt="$out/receipts/final-public-cache-cleanup.txt"
[[ -f $cleanup_receipt && ! -L $cleanup_receipt ]]
[[ $(realpath -e -- "$cleanup_receipt") == "$cleanup_receipt" ]]

receipt_field() {
  local key=$1
  awk -F= -v key="$key" '
    $1 == key { count++; value=substr($0, length(key) + 2) }
    END { if (count != 1) exit 1; print value }
  ' "$cleanup_receipt"
}
[[ $(receipt_field schema) == arch-pq-final-public-cache-cleanup-v3 ]]
[[ $(receipt_field toolchain_preserved) == true ]]
[[ $(receipt_field cleanup_exit) == 0 ]]
[[ $(awk -F'\t' '$1 == "selection" { if (NF != 6) exit 2; count++ } END { print count+0 }' \
  "$cleanup_receipt") == 2 ]]

declare -A selected=()
declare -A archive_bytes=()
declare -A archive_digests=()
declare -A executable_digests=()
for selection in "$@"; do
  package=${selection%%=*}
  attempt_id=${selection#*=}
  case "$package" in
    sequoia-sq-pqc) version=1.4.0 executable=sq ;;
    sequoia-sqv-pqc) version=1.5.0 executable=sqv ;;
    *) exit 2 ;;
  esac
  [[ -z ${selected[$package]-} ]] || { printf 'duplicate package selection: %s\n' "$package" >&2; exit 2; }
  [[ $attempt_id =~ ^[0-9]{3}$ ]]
  selected[$package]=$attempt_id
  attempt="$root/attempts/${package}-attempt-${attempt_id}"
  archive="$out/archives/${package}-${version}-4-x86_64.pkg.tar.zst"
  [[ -d $attempt && ! -L $attempt && $(realpath -e -- "$attempt") == "$attempt" ]]
  [[ -f $attempt/receipts/ACCEPTED && ! -L $attempt/receipts/ACCEPTED ]]
  [[ $(realpath -e -- "$attempt/receipts/ACCEPTED") == "$attempt/receipts/ACCEPTED" ]]
  [[ -f $attempt/receipts/outer-launcher.txt && ! -L $attempt/receipts/outer-launcher.txt ]]
  [[ -f $attempt/receipts/output-archive.sha256 && ! -L $attempt/receipts/output-archive.sha256 ]]
  [[ -f $archive && ! -L $archive ]]
  [[ $(awk -F= '$1 == "accepted" { count++; value=$2 } END { if (count == 0) exit 1; print value }' \
    "$attempt/receipts/outer-launcher.txt") == true ]]
  [[ $(awk -F= '$1 == "outer_exit" { count++; value=$2 } END { if (count != 1) exit 1; print value }' \
    "$attempt/receipts/outer-launcher.txt") == 0 ]]
  [[ $(awk -F= '$1 == "lifecycle_admission_sha256" { count++; value=$2 } END { if (count != 1) exit 1; print value }' \
    "$attempt/receipts/outer-launcher.txt") == "$lifecycle_admission_sha256" ]]
  digest=$(sha256sum "$archive" | cut -d' ' -f1)
  IFS= read -r recorded_archive_line <"$attempt/receipts/output-archive.sha256"
  [[ $recorded_archive_line == "$digest  $archive" ]]
  [[ $(realpath -e -- "$archive") == "$archive" && $archive == "$out/archives/"* ]]
  grep -Fxq $'selection\t'"$package"$'\t'"$attempt_id"$'\t'"$digest"$'\ttrue\ttrue' \
    "$cleanup_receipt"
  for cache_root in "$attempt/work/cargo" "$attempt/work/srcdest"; do
    [[ -d $cache_root && ! -L $cache_root ]]
    [[ $(realpath -e -- "$cache_root") == "$cache_root" && $cache_root == "$attempt/"* ]]
    [[ -z $(find "$cache_root" -mindepth 1 -print -quit) ]]
  done
  archive_bytes[$package]=$(stat -c %s "$archive")
  archive_digests[$package]=$digest
  executable_path="$attempt/extracted/usr/bin/$executable"
  [[ -f $executable_path && ! -L $executable_path ]]
  [[ $(realpath -e -- "$executable_path") == "$executable_path" && $executable_path == "$attempt/"* ]]
  executable_digests[$package]=$(sha256sum "$executable_path" | cut -d' ' -f1)
done
[[ ${selected[sequoia-sq-pqc]-} =~ ^[0-9]{3}$ && ${selected[sequoia-sqv-pqc]-} =~ ^[0-9]{3}$ ]]

/usr/bin/bash "$root/procedure/verify-frozen-boundary.sh" >/dev/null
/usr/bin/bash "$root/procedure/verify-toolchain.sh" >/dev/null
mkdir -p "$prov" "$review"
sha256sum "$cleanup_receipt" >"$prov/final-public-cache-cleanup.sha256"
mkdir -p "$prov/lifecycle"
for lifecycle_path in \
  output/receipts/prebuild-environment.txt \
  setup-evidence/common-setup.txt \
  control/frozen-boundary.txt \
  review/failure-boundary-self-test.txt \
  control/lifecycle-admission.txt
do
  lifecycle_name=${lifecycle_path##*/}
  cp -- "$root/$lifecycle_path" "$prov/lifecycle/$lifecycle_name"
  cmp -s "$root/$lifecycle_path" "$prov/lifecycle/$lifecycle_name"
done
(
  cd "$root"
  sha256sum \
    output/receipts/prebuild-environment.txt \
    setup-evidence/common-setup.txt \
    control/frozen-boundary.txt \
    review/failure-boundary-self-test.txt \
    control/lifecycle-admission.txt \
    output/provenance/lifecycle/prebuild-environment.txt \
    output/provenance/lifecycle/common-setup.txt \
    output/provenance/lifecycle/frozen-boundary.txt \
    output/provenance/lifecycle/failure-boundary-self-test.txt \
    output/provenance/lifecycle/lifecycle-admission.txt
) >"$prov/lifecycle-admission.sha256"
/usr/bin/bash "$root/procedure/verify-frozen-boundary.sh" \
  >"$prov/final-frozen-input-verification.txt" 2>&1
/usr/bin/bash "$root/procedure/verify-toolchain.sh" \
  >>"$prov/final-frozen-input-verification.txt" 2>&1
cp -- "$root/review-admission/source-revision.txt" "$prov/reviewed-source-revision.txt"
cp -- "$root/review-admission/maintained-source.inventory.tsv" \
  "$prov/reviewed-maintained-source.inventory.tsv"
(
  cd "$root"
  sha256sum review-admission/source-revision.txt \
    review-admission/maintained-source.inventory.tsv \
    output/provenance/reviewed-source-revision.txt \
    output/provenance/reviewed-maintained-source.inventory.tsv
) >"$prov/reviewed-source-admission.sha256"

printf 'package\tattempt\tarchive_bytes\tarchive_sha256\texecutable_sha256\n' \
  >"$prov/candidate-identities.tsv"
for package in sequoia-sq-pqc sequoia-sqv-pqc; do
  printf '%s\t%s\t%s\t%s\t%s\n' "$package" "${selected[$package]}" \
    "${archive_bytes[$package]}" "${archive_digests[$package]}" \
    "${executable_digests[$package]}" >>"$prov/candidate-identities.tsv"
done

printf 'status=procedure-complete-successor-candidates-built-but-not-independently-accepted\n' \
  >"$review/validation-status.txt"
printf 'downstream_operation_gate=open\nmacos_interoperability_gate=open\ninstallation_gate=open\nrollback_authenticity_gate=open\nacceptance_gate=open\ndeployment_gate=open\n' \
  >>"$review/validation-status.txt"
inventory="$review/final-source-and-evidence.inventory.tsv"
/usr/bin/bash "$root/procedure/write-run-inventory.sh" "$root" "$inventory"
