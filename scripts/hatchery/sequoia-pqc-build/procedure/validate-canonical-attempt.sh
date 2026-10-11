#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
action=${1-}
attempt_root=${2-}
expected_package=${3-}
expected_attempt=${4-}
expected_lifecycle=${5-}
expected_binding=${6-}

(( $# == 6 )) || {
  printf 'usage: %s {initialized|accepted} ATTEMPT_PATH PACKAGE ATTEMPT_ID LIFECYCLE_SHA256 {staged|canonical|ARCHIVE}\n' "$0" >&2
  exit 2
}
[[ $expected_attempt =~ ^[0-9]{3}$ ]]
[[ -z $expected_lifecycle || $expected_lifecycle =~ ^[0-9a-f]{64}$ ]]
case "$expected_package" in
  sequoia-sq-pqc|sequoia-sqv-pqc|synthetic-procedure-test) ;;
  *) exit 2 ;;
esac

field() {
  local record=$1 key=$2
  awk -F= -v key="$key" '
    $1 == key { count++; value=substr($0, length(key) + 2) }
    END { if (count != 1) exit 1; print value }
  ' "$record"
}

canonical_regular_file() {
  local candidate=$1 expected=$2 canonical
  [[ -f $candidate && ! -L $candidate ]]
  canonical=$(realpath -e -- "$candidate")
  [[ $canonical == "$candidate" && $canonical == "$expected" ]]
}

[[ -d $attempt_root && ! -L $attempt_root ]]
attempt_canonical=$(realpath -e -- "$attempt_root")
[[ $attempt_canonical == "$attempt_root" ]]
case "$action" in
  initialized)
    case "$expected_binding" in
      staged)
        expected_attempt_root="$root/attempts/.initializing-${expected_package}-attempt-${expected_attempt}"
        ;;
      canonical)
        expected_attempt_root="$root/attempts/${expected_package}-attempt-${expected_attempt}"
        ;;
      *) exit 2 ;;
    esac
    ;;
  accepted)
    [[ -n $expected_lifecycle ]]
    expected_attempt_root="$root/attempts/${expected_package}-attempt-${expected_attempt}"
    ;;
  *) exit 2 ;;
esac
[[ $attempt_root == "$expected_attempt_root" ]]

receipts="$attempt_root/receipts"
launcher="$receipts/outer-launcher.txt"
claim="$attempt_root/initialization-claim.txt"
[[ -d $receipts && ! -L $receipts ]]
[[ $(realpath -e -- "$receipts") == "$receipts" ]]
canonical_regular_file "$launcher" "$attempt_root/receipts/outer-launcher.txt"
canonical_regular_file "$claim" "$attempt_root/initialization-claim.txt"

[[ $(field "$launcher" schema) == arch-pq-outer-launcher-v3 ]]
[[ $(field "$launcher" package) == "$expected_package" ]]
[[ $(field "$launcher" attempt) == "$expected_attempt" ]]
started=$(field "$launcher" started_utc)
[[ $started =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
claim_sha=$(field "$launcher" initialization_claim_sha256)
[[ $claim_sha =~ ^[0-9a-f]{64}$ ]]
[[ $(awk -F= '$1 == "accepted" { count++; if (count == 1) first=$2 }
    END { if (count == 0) exit 1; print first }' "$launcher") == false ]]
if [[ -n $expected_lifecycle ]]; then
  [[ $(field "$launcher" lifecycle_admission_sha256) == "$expected_lifecycle" ]]
  claim_lifecycle=$expected_lifecycle
else
  [[ $(awk -F= '$1 == "lifecycle_admission_sha256" { count++ }
      END { print count+0 }' "$launcher") == 0 ]]
  claim_lifecycle=none
fi
cmp -s -- "$claim" <(
  printf 'schema=arch-pq-attempt-initialization-v1\npackage=%s\nattempt=%s\nlifecycle_admission_sha256=%s\n' \
    "$expected_package" "$expected_attempt" "$claim_lifecycle"
)
[[ $(sha256sum "$claim" | cut -d' ' -f1) == "$claim_sha" ]]

if [[ $action == accepted ]]; then
  archive=$expected_binding
  accepted="$receipts/ACCEPTED"
  archive_receipt="$receipts/output-archive.sha256"
  canonical_regular_file "$accepted" "$attempt_root/receipts/ACCEPTED"
  canonical_regular_file "$archive_receipt" "$attempt_root/receipts/output-archive.sha256"
  canonical_regular_file "$archive" "$archive"
  [[ $archive == "$root/output/archives/"* ]]
  [[ $(field "$launcher" outer_exit) == 0 ]]
  completed=$(field "$launcher" completed_utc)
  [[ $completed =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
  [[ $(field "$launcher" output_archive) == "$archive" ]]
  awk -F= '
    $1 == "accepted" { count++; value[count]=$2 }
    END { exit !(count == 2 && value[1] == "false" && value[2] == "true") }
  ' "$launcher"
  archive_sha=$(sha256sum "$archive" | cut -d' ' -f1)
  [[ $(wc -l <"$archive_receipt") == 1 ]]
  IFS= read -r recorded_archive_line <"$archive_receipt"
  [[ $recorded_archive_line == "$archive_sha  $archive" ]]
fi
