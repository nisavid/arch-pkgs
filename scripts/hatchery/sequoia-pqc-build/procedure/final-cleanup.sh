#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
(( $# == 2 )) || { printf 'usage: %s sequoia-sq-pqc=ID sequoia-sqv-pqc=ID\n' "$0" >&2; exit 2; }

declare -A selected=()
declare -A versions=([sequoia-sq-pqc]=1.4.0 [sequoia-sqv-pqc]=1.5.0)
for selection in "$@"; do
  package=${selection%%=*}
  attempt_id=${selection#*=}
  [[ -n ${versions[$package]-} && $attempt_id =~ ^[0-9]{3}$ ]]
  [[ -z ${selected[$package]-} ]] || { printf 'duplicate package selection: %s\n' "$package" >&2; exit 2; }
  selected[$package]=$attempt_id
done
[[ -n ${selected[sequoia-sq-pqc]-} && -n ${selected[sequoia-sqv-pqc]-} ]]

receipt="$root/output/receipts/final-public-cache-cleanup.txt"
[[ ! -e $receipt && ! -L $receipt ]] || { printf 'final cleanup receipt already exists\n' >&2; exit 2; }
mkdir -p "$root/output/receipts"
[[ -d $root/output/receipts && ! -L $root/output/receipts ]]
[[ $(realpath -e -- "$root/output/receipts") == "$root/output/receipts" ]]
printf 'schema=arch-pq-final-public-cache-cleanup-v3\nstarted_utc=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$receipt"
{
  /usr/bin/bash "$root/procedure/verify-frozen-boundary.sh"
  /usr/bin/bash "$root/procedure/verify-toolchain.sh"
} >>"$receipt" 2>&1

cache_roots=()
declare -A archive_digests=()

contained_directory() {
  local candidate=$1 parent=$2 canonical
  [[ -d $candidate && ! -L $candidate ]] || {
    printf 'cleanup path is not an actual directory: %s\n' "$candidate" >&2
    return 1
  }
  canonical=$(realpath -e -- "$candidate")
  [[ $canonical == "$candidate" && $canonical == "$parent"/* ]] || {
    printf 'cleanup path escapes its fixed parent: %s\n' "$candidate" >&2
    return 1
  }
  printf '%s\n' "$canonical"
}

queue_cache_root() {
  local candidate=$1 parent=$2 required=${3-false} canonical
  if [[ ! -e $candidate && ! -L $candidate ]]; then
    [[ $required == false ]] && return 0
    printf 'selected cache path is missing: %s\n' "$candidate" >&2
    return 1
  fi
  canonical=$(contained_directory "$candidate" "$parent")
  cache_roots+=("$canonical")
}

receipt_field() {
  local receipt_path=$1 key=$2
  awk -F= -v key="$key" '
    $1 == key { count++; value=substr($0, length(key) + 2) }
    END { if (count != 1) exit 1; print value }
  ' "$receipt_path"
}

last_receipt_field() {
  local receipt_path=$1 key=$2
  awk -F= -v key="$key" '
    $1 == key { count++; value=substr($0, length(key) + 2) }
    END { if (count == 0) exit 1; print value }
  ' "$receipt_path"
}

if [[ -e $root/setup-scratch || -L $root/setup-scratch ]]; then
  setup_scratch=$(contained_directory "$root/setup-scratch" "$root")
  queue_cache_root "$setup_scratch/home" "$setup_scratch"
  queue_cache_root "$setup_scratch/cargo" "$setup_scratch"
fi

attempts_root=$(contained_directory "$root/attempts" "$root")
for package in sequoia-sq-pqc sequoia-sqv-pqc; do
  attempt_id=${selected[$package]}
  version=${versions[$package]}
  attempt=$(contained_directory "$attempts_root/${package}-attempt-${attempt_id}" "$attempts_root")
  receipts=$(contained_directory "$attempt/receipts" "$attempt")
  accepted="$receipts/ACCEPTED"
  launcher="$receipts/outer-launcher.txt"
  archive_receipt="$receipts/output-archive.sha256"
  archive="$root/output/archives/${package}-${version}-4-x86_64.pkg.tar.zst"
  [[ -f $accepted && ! -L $accepted ]]
  [[ -f $launcher && ! -L $launcher ]]
  [[ -f $archive_receipt && ! -L $archive_receipt ]]
  [[ -f $archive && ! -L $archive ]]
  [[ $(realpath -e -- "$archive") == "$archive" && $archive == "$root/output/archives/"* ]]
  [[ $(last_receipt_field "$launcher" accepted) == true ]]
  [[ $(receipt_field "$launcher" outer_exit) == 0 ]]
  actual_digest=$(sha256sum "$archive" | cut -d' ' -f1)
  IFS= read -r recorded_archive_line <"$archive_receipt"
  [[ $recorded_archive_line == "$actual_digest  $archive" ]]
  archive_digests[$package]=$actual_digest
  queue_cache_root "$attempt/work/cargo" "$attempt" true
  queue_cache_root "$attempt/work/srcdest" "$attempt" true
done

for cache_root in "${cache_roots[@]}"; do
  [[ $(realpath -e -- "$cache_root") == "$cache_root" ]]
  printf 'cache_root=%s\ncanonical_cache_root=%s\nremoval=find-depth-delete-unread\n' \
    "$cache_root" "$cache_root" >>"$receipt"
  chmod -R u+rwX "$cache_root" 2>/dev/null || true
  find "$cache_root" -mindepth 1 -depth -delete >/dev/null 2>&1
  [[ -z $(find "$cache_root" -mindepth 1 -print -quit) ]]
done

for package in sequoia-sq-pqc sequoia-sqv-pqc; do
  attempt_id=${selected[$package]}
  attempt="$root/attempts/${package}-attempt-${attempt_id}"
  [[ -z $(find "$attempt/work/cargo" -mindepth 1 -print -quit) ]]
  [[ -z $(find "$attempt/work/srcdest" -mindepth 1 -print -quit) ]]
  archive="$root/output/archives/${package}-${versions[$package]}-4-x86_64.pkg.tar.zst"
  [[ $(sha256sum "$archive" | cut -d' ' -f1) == "${archive_digests[$package]}" ]]
  printf 'selection\t%s\t%s\t%s\ttrue\ttrue\n' \
    "$package" "$attempt_id" "${archive_digests[$package]}" >>"$receipt"
done
{
  /usr/bin/bash "$root/procedure/verify-frozen-boundary.sh"
  /usr/bin/bash "$root/procedure/verify-toolchain.sh"
} >>"$receipt" 2>&1
printf 'toolchain_preserved=true\ncompleted_utc=%s\ncleanup_exit=0\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$receipt"
chmod 444 "$receipt"
