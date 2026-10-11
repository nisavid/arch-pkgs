#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT
run_root="$scratch/run"
mkdir -p "$run_root/recipes/synthetic-procedure-test" "$run_root/inputs/rustup" \
  "$run_root/inputs/gnupg-public"
cp -a "$source_root/procedure" "$run_root/procedure"
printf 'inert recipe input\n' >"$run_root/recipes/synthetic-procedure-test/README"
printf 'inert toolchain input\n' >"$run_root/inputs/rustup/tool"
printf 'inert public verification input\n' >"$run_root/inputs/gnupg-public/pubring.kbx"

set +e
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  HATCHERY_PROCEDURE_TEST_MODE=1 \
  HATCHERY_TEST_USE_REAL_BOUNDARY=1 \
  HATCHERY_TEST_PHASE_RUNNER="$tests_dir/fixtures/inert-phase-runner.sh" \
  HATCHERY_TEST_FAIL_PHASE=verifysource \
  HATCHERY_TEST_FAIL_EXIT=31 \
  /usr/bin/bash "$run_root/procedure/invoke-attempt.sh" synthetic-procedure-test 001 \
  >"$scratch/wrapper.stdout" 2>"$scratch/wrapper.stderr"
status=$?
set -e
attempt="$run_root/attempts/synthetic-procedure-test-attempt-001"
(( status == 31 )) || {
  sed -n '1,120p' "$scratch/wrapper.stderr" >&2
  sed -n '1,160p' "$attempt/logs/boundary.log" >&2
  exit 1
}
awk -F'\t' '$1 == "boundary" && $4 == 0 { found=1 } END { exit !found }' \
  "$attempt/receipts/phase-exits.tsv"
awk -F'\t' '$1 == "verifysource" && $4 == 31 { found=1 } END { exit !found }' \
  "$attempt/receipts/phase-exits.tsv"
[[ ! -e $attempt/receipts/ACCEPTED ]]
[[ -z $(find "$run_root/output/archives" -mindepth 1 -print -quit) ]]
[[ -z $(find "$run_root/procedure" "$run_root/recipes" "$run_root/inputs" -name .forbidden-write-probe -print -quit) ]]
printf 'actual namespace boundary isolation: PASS\n'
