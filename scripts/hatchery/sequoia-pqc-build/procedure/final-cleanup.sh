#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
receipt="$root/output/receipts/final-public-cache-cleanup.txt"
[[ ! -e $receipt ]] || { printf 'final cleanup receipt already exists\n' >&2; exit 2; }
mkdir -p "$root/output/receipts"
printf 'schema=arch-pq-final-public-cache-cleanup-v2\nstarted_utc=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$receipt"
{
  /usr/bin/bash "$root/procedure/verify-frozen-boundary.sh"
  /usr/bin/bash "$root/procedure/verify-toolchain.sh"
} >>"$receipt" 2>&1

cache_roots=()

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
  local candidate=$1 parent=$2 canonical
  [[ -e $candidate || -L $candidate ]] || return 0
  canonical=$(contained_directory "$candidate" "$parent")
  cache_roots+=("$canonical")
}

if [[ -e $root/setup-scratch || -L $root/setup-scratch ]]; then
  setup_scratch=$(contained_directory "$root/setup-scratch" "$root")
  queue_cache_root "$setup_scratch/home" "$setup_scratch"
  queue_cache_root "$setup_scratch/cargo" "$setup_scratch"
fi

if [[ -e $root/attempts || -L $root/attempts ]]; then
  attempts_root=$(contained_directory "$root/attempts" "$root")
  for attempt in "$attempts_root"/*; do
    [[ -e $attempt || -L $attempt ]] || continue
    [[ ! -L $attempt ]] || {
      printf 'symlinked attempt is not eligible for cleanup: %s\n' "$attempt" >&2
      exit 1
    }
    [[ -d $attempt ]] || continue
    canonical_attempt=$(contained_directory "$attempt" "$attempts_root")
    accepted="$canonical_attempt/receipts/ACCEPTED"
    [[ ! -L $accepted ]] || {
      printf 'symlinked acceptance marker is not eligible for cleanup: %s\n' "$accepted" >&2
      exit 1
    }
    [[ -f $accepted ]] || continue
    queue_cache_root "$canonical_attempt/work/cargo" "$canonical_attempt"
    queue_cache_root "$canonical_attempt/work/srcdest" "$canonical_attempt"
  done
fi

for cache_root in "${cache_roots[@]}"; do
  [[ $(realpath -e -- "$cache_root") == "$cache_root" ]]
  printf 'cache_root=%s\ncanonical_cache_root=%s\nremoval=find-depth-delete-unread\n' \
    "$cache_root" "$cache_root" >>"$receipt"
  chmod -R u+rwX "$cache_root" 2>/dev/null || true
  find "$cache_root" -mindepth 1 -depth -delete >/dev/null 2>&1
  [[ -z $(find "$cache_root" -mindepth 1 -print -quit) ]]
done
{
  /usr/bin/bash "$root/procedure/verify-frozen-boundary.sh"
  /usr/bin/bash "$root/procedure/verify-toolchain.sh"
} >>"$receipt" 2>&1
printf 'toolchain_preserved=true\ncompleted_utc=%s\ncleanup_exit=0\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$receipt"
