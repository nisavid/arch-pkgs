#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)

cleanup() {
  find "$scratch" -depth -delete
}
trap cleanup EXIT

run_case() {
  local case_name=$1 attempt_id=$2 fail_phase=$3 fail_exit=$4 expected_calls=$5
  local run_root="$scratch/$case_name/run"
  mkdir -p "$run_root"
  cp -a "$source_root/procedure" "$run_root/procedure"

  set +e
  env -i \
    PATH=/usr/bin:/bin \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    HATCHERY_PROCEDURE_TEST_MODE=1 \
    HATCHERY_TEST_PHASE_RUNNER="$tests_dir/fixtures/inert-phase-runner.sh" \
    HATCHERY_TEST_FAIL_PHASE="$fail_phase" \
    HATCHERY_TEST_FAIL_EXIT="$fail_exit" \
    /usr/bin/bash "$run_root/procedure/invoke-attempt.sh" synthetic-procedure-test "$attempt_id" \
    >"$scratch/$case_name.wrapper.stdout" \
    2>"$scratch/$case_name.wrapper.stderr"
  local wrapper_exit=$?
  set -e

  local attempt="$run_root/attempts/synthetic-procedure-test-attempt-$attempt_id"
  if [[ $wrapper_exit != "$fail_exit" ]]; then
    printf '%s: expected real wrapper exit %s, got %s\n' \
      "$case_name" "$fail_exit" "$wrapper_exit" >&2
    sed -n '1,20p' "$scratch/$case_name.wrapper.stderr" >&2
    exit 1
  fi
  [[ ! -e "$attempt/receipts/INNER_ACCEPTED" ]]
  [[ ! -e "$attempt/receipts/ACCEPTED" ]]
  [[ -f "$attempt/receipts/outer-launcher.txt" ]]
  grep -Fxq "outer_exit=$fail_exit" "$attempt/receipts/outer-launcher.txt"
  grep -Fxq 'accepted=false' "$attempt/receipts/outer-launcher.txt"
  [[ -d "$run_root/output/archives" ]]
  [[ -z $(find "$run_root/output/archives" -mindepth 1 -print -quit) ]]
  while IFS= read -r secret_root; do
    [[ -z $(find "$attempt/work/$secret_root" -mindepth 1 -print -quit) ]]
  done < <(printf '%s\n' home tmp runtime-home gnupg-runtime builddir xdg-cache xdg-config xdg-data)
  diff -u <(printf '%s' "$expected_calls") "$attempt/inert-phase-runner.calls"
  printf '%s_executed_invoke_attempt_sha256=%s\n' "$case_name" \
    "$(sha256sum "$run_root/procedure/invoke-attempt.sh" | cut -d' ' -f1)"
}

run_case early 001 verifysource 23 $'boundary\nverifysource\n'
run_case late 002 post-build-verify 29 \
  $'boundary\nverifysource\nprefetch\ncapture-source-view\nchecked-build\npost-build-verify\n'

[[ -f "$scratch/late/run/attempts/synthetic-procedure-test-attempt-002/work/pkgdest/synthetic-procedure-test-0-0-any.pkg.tar.zst" ]]

set +e
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  HATCHERY_PROCEDURE_TEST_MODE=1 \
  HATCHERY_TEST_PHASE_RUNNER="$tests_dir/fixtures/inert-phase-runner.sh" \
  /usr/bin/bash "$scratch/late/run/procedure/invoke-attempt.sh" sequoia-sq-pqc 003 \
  >"$scratch/real-hook.stdout" 2>"$scratch/real-hook.stderr"
real_hook_exit=$?
set -e
(( real_hook_exit == 2 ))
grep -Fq 'test hooks are forbidden for real package attempts' "$scratch/real-hook.stderr"
[[ ! -e $scratch/late/run/attempts/sequoia-sq-pqc-attempt-003 ]]

printf 'real-wrapper failure propagation: PASS\n'
