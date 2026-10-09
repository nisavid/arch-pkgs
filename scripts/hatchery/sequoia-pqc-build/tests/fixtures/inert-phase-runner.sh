#!/usr/bin/bash
set -Eeuo pipefail

phase=${1-}
package=${2-}
attempt=${3-}
fail_phase=${HATCHERY_TEST_FAIL_PHASE-}
fail_exit=${HATCHERY_TEST_FAIL_EXIT-}

[[ $package == synthetic-procedure-test ]]
[[ -d $attempt/work/pkgdest ]]
printf '%s\n' "$phase" >>"$attempt/inert-phase-runner.calls"

case "$phase" in
  boundary|verifysource|prefetch|capture-source-view)
    ;;
  checked-build)
    printf 'inert candidate archive\n' \
      >"$attempt/work/pkgdest/synthetic-procedure-test-0-4-x86_64.pkg.tar.zst"
    ;;
  post-build-verify)
    archive="$attempt/work/pkgdest/synthetic-procedure-test-0-4-x86_64.pkg.tar.zst"
    [[ -f $archive ]]
    sha256sum "$archive" >"$attempt/receipts/archive-immediate.sha256"
    ;;
  *)
    printf 'unexpected synthetic phase: %s\n' "$phase" >&2
    exit 97
    ;;
esac

if [[ $phase == "$fail_phase" ]]; then
  [[ $fail_exit =~ ^[1-9][0-9]?$|^1[0-9][0-9]$|^2[0-4][0-9]$|^25[0-5]$ ]]
  exit "$fail_exit"
fi
