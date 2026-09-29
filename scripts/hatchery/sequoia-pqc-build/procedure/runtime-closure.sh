#!/usr/bin/bash
set -Eeuo pipefail

(( $# == 1 )) || { printf 'usage: %s CANDIDATE\n' "$0" >&2; exit 2; }
candidate=$1
[[ -x $candidate && ! -L $candidate ]]
candidate_canonical=$(realpath -e -- "$candidate")
[[ $candidate_canonical == /candidate/* ]]

set +e
ldd_output=$(/usr/bin/ldd "$candidate_canonical" 3>&- 2>&1)
ldd_status=$?
set -e
printf '%s\n' "$ldd_output" >&3
(( ldd_status == 0 ))

closure_status=0
while IFS= read -r reported_path; do
  if ! canonical_path=$(realpath -e -- "$reported_path"); then
    printf 'missing_runtime_object=%s\n' "$reported_path" >&2
    closure_status=1
    continue
  fi
  if [[ $canonical_path != /usr/lib/* || ! -f $canonical_path || -L $canonical_path ]]; then
    printf 'invalid_runtime_object=%s\n' "$reported_path" >&2
    closure_status=1
    continue
  fi
  if ! owner=$(pacman -Qo -- "$canonical_path"); then
    closure_status=1
    continue
  fi
  printf 'reported_path=%s\ncanonical_path=%s\nsha256=%s\nowner=%s\n' \
    "$reported_path" "$canonical_path" \
    "$(sha256sum "$canonical_path" | cut -d' ' -f1)" "$owner"
done < <(
  printf '%s\n' "$ldd_output" |
    awk '/=> \/|^\// { for (i=1; i<=NF; i++) if ($i ~ /^\//) { print $i; break } }' |
    LC_ALL=C sort -u
)
(( closure_status == 0 ))
