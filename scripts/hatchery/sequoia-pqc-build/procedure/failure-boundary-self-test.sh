#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
result="$root/review/failure-boundary-self-test.txt"
[[ ! -e $result ]] || { printf 'self-test output already exists\n' >&2; exit 2; }
mkdir -p "$root/review"
start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
invoke_sha=$(sha256sum "$root/procedure/invoke-attempt.sh" | cut -d' ' -f1)
/usr/bin/bash "$root/procedure/verify-frozen-boundary.sh" >"$result" 2>&1
/usr/bin/bash "$root/tests/real-wrapper-failure.sh" >>"$result" 2>&1
grep -Fxq "early_executed_invoke_attempt_sha256=$invoke_sha" "$result"
grep -Fxq "late_executed_invoke_attempt_sha256=$invoke_sha" "$result"
grep -Fxq "success_executed_invoke_attempt_sha256=$invoke_sha" "$result"
/usr/bin/bash "$root/procedure/verify-frozen-boundary.sh" >>"$result" 2>&1
printf 'started_utc=%s\nreal_wrapper_sha256=%s\nreal_wrapper_test_sha256=%s\ninert_phase_fixture_sha256=%s\ncompleted_utc=%s\nself_test_exit=0\n' \
  "$start" "$invoke_sha" \
  "$(sha256sum "$root/tests/real-wrapper-failure.sh" | cut -d' ' -f1)" \
  "$(sha256sum "$root/tests/fixtures/inert-phase-runner.sh" | cut -d' ' -f1)" \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$result"
