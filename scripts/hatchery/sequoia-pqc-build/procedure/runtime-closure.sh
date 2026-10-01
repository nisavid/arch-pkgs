#!/usr/bin/bash
set -Eeuo pipefail

(( $# == 1 )) || { printf 'usage: %s CANDIDATE\n' "$0" >&2; exit 2; }
candidate=$1
[[ -x $candidate && ! -L $candidate ]]
candidate_canonical=$(realpath -e -- "$candidate")
test_mode=${HATCHERY_RUNTIME_CLOSURE_TEST_MODE-0}
case "$test_mode" in
  0)
    [[ -z ${HATCHERY_TEST_LDD_COMMAND-}${HATCHERY_TEST_RUNTIME_ROOT-}${HATCHERY_TEST_OWNER_COMMAND-} ]]
    [[ $candidate_canonical == /candidate/* ]]
    ldd_command=/usr/bin/ldd
    runtime_root=/usr/lib
    owner_command=/usr/bin/pacman
    ;;
  1)
    ldd_command=${HATCHERY_TEST_LDD_COMMAND-}
    runtime_root=${HATCHERY_TEST_RUNTIME_ROOT-}
    owner_command=${HATCHERY_TEST_OWNER_COMMAND-}
    [[ -x $ldd_command && ! -L $ldd_command ]]
    [[ -d $runtime_root && ! -L $runtime_root ]]
    runtime_root=$(realpath -e -- "$runtime_root")
    [[ -x $owner_command && ! -L $owner_command ]]
    ;;
  *) exit 2 ;;
esac

set +e
ldd_output=$("$ldd_command" "$candidate_canonical" 3>&- 2>&1)
ldd_status=$?
set -e
printf '%s\n' "$ldd_output" >&3
(( ldd_status == 0 ))

closure_status=0
while IFS= read -r missing_object; do
  [[ -z $missing_object ]] && continue
  printf 'missing_runtime_object=%s\n' "$missing_object" >&2
  closure_status=1
done < <(
  printf '%s\n' "$ldd_output" |
    awk '$2 == "=>" && $3 == "not" && $4 == "found" { print $1 }' |
    LC_ALL=C sort -u
)
while IFS= read -r reported_path; do
  if ! canonical_path=$(realpath -e -- "$reported_path"); then
    printf 'missing_runtime_object=%s\n' "$reported_path" >&2
    closure_status=1
    continue
  fi
  if [[ $canonical_path != "$runtime_root/"* || ! -f $canonical_path || -L $canonical_path ]]; then
    printf 'invalid_runtime_object=%s\n' "$reported_path" >&2
    closure_status=1
    continue
  fi
  if ! owner=$("$owner_command" -Qo -- "$canonical_path"); then
    closure_status=1
    continue
  fi
  printf 'reported_path=%s\ncanonical_path=%s\nsha256=%s\nowner=%s\n' \
    "$reported_path" "$canonical_path" \
    "$(sha256sum "$canonical_path" | cut -d' ' -f1)" "$owner"
done < <(
  printf '%s\n' "$ldd_output" |
    awk '{ for (i=1; i<=NF; i++) if ($i ~ /^\//) print $i }' |
    LC_ALL=C sort -u
)
(( closure_status == 0 ))
