#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT

make_run() {
  local name=$1 behavior=$2 run
  run="$scratch/$name"
  mkdir -p "$run/procedure" "$run/recipes/inert" "$run/tests/fixtures" "$run/inputs/rustup"
  cp "$source_root/procedure/freeze-boundary.sh" \
    "$source_root/procedure/failure-boundary-self-test.sh" \
    "$source_root/procedure/lifecycle-admission.sh" \
    "$source_root/procedure/verify-frozen-boundary.sh" \
    "$source_root/procedure/verify-reviewed-source.sh" "$run/procedure/"
  printf '%s\n' '#!/usr/bin/bash' 'exit 0' >"$run/procedure/invoke-attempt.sh"
  chmod 755 "$run/procedure/invoke-attempt.sh"
  printf 'recipe\n' >"$run/recipes/inert/README"
  printf 'toolchain\n' >"$run/inputs/rustup/tool"
  (cd "$run" && sha256sum inputs/rustup/tool >inputs/rust-toolchain.sha256)
  printf 'fixture\n' >"$run/tests/fixtures/inert-phase-runner.sh"
  if [[ $behavior == mutates_fixture ]]; then
    # shellcheck disable=SC2016 # Expansion belongs to the generated wrapper.
    printf '%s\n' '#!/usr/bin/bash' 'printf "changed\\n" >>"${BASH_SOURCE[0]%/*}/fixtures/inert-phase-runner.sh"' \
      'printf "real-wrapper failure propagation: PASS\\n"' >"$run/tests/real-wrapper-failure.sh"
  else
    printf '%s\n' '#!/usr/bin/bash' 'printf "real-wrapper failure propagation: PASS\\n"' \
      >"$run/tests/real-wrapper-failure.sh"
  fi
  # shellcheck disable=SC2016 # Expansion belongs to the generated wrapper.
  printf '%s\n' \
    'invoke_sha=$(sha256sum "${BASH_SOURCE[0]%/*}/../procedure/invoke-attempt.sh" | cut -d" " -f1)' \
    'printf "early_executed_invoke_attempt_sha256=%s\\n" "$invoke_sha"' \
    'printf "late_executed_invoke_attempt_sha256=%s\\n" "$invoke_sha"' \
    'printf "success_executed_invoke_attempt_sha256=%s\\n" "$invoke_sha"' \
    >>"$run/tests/real-wrapper-failure.sh"
  chmod 755 "$run/tests/real-wrapper-failure.sh" "$run/tests/fixtures/inert-phase-runner.sh"
  mkdir -p "$run/output/receipts" "$run/setup-evidence"
  printf 'schema=arch-pq-prebuild-environment-v1\nfixture=invalid-public-test-data\nprebuild_capture_exit=0\n' \
    >"$run/output/receipts/prebuild-environment.txt"
  printf 'schema=arch-pq-common-setup-v2\nfixture=invalid-public-test-data\nsetup_exit=0\n' \
    >"$run/setup-evidence/common-setup.txt"
  /usr/bin/bash "$source_root/tests/fixtures/create-reviewed-source-admission.sh" "$run"
  /usr/bin/bash "$run/procedure/freeze-boundary.sh" >/dev/null
  printf '%s\n' "$run"
}

run=$(make_run before before)
printf 'changed-before\n' >>"$run/tests/fixtures/inert-phase-runner.sh"
set +e
/usr/bin/bash "$run/procedure/failure-boundary-self-test.sh" >/dev/null 2>&1
status=$?
set -e
(( status != 0 ))

run=$(make_run during mutates_fixture)
set +e
/usr/bin/bash "$run/procedure/failure-boundary-self-test.sh" >/dev/null 2>&1
status=$?
set -e
(( status != 0 ))

run=$(make_run mode mode)
chmod 644 "$run/tests/fixtures/inert-phase-runner.sh"
set +e
/usr/bin/bash "$run/procedure/failure-boundary-self-test.sh" >/dev/null 2>&1
status=$?
set -e
(( status != 0 ))

run=$(make_run valid valid)
/usr/bin/bash "$run/procedure/failure-boundary-self-test.sh"
receipt="$run/review/failure-boundary-self-test.txt"
grep -Fxq "real_wrapper_test_sha256=$(sha256sum "$run/tests/real-wrapper-failure.sh" | cut -d' ' -f1)" "$receipt"
grep -Fxq "inert_phase_fixture_sha256=$(sha256sum "$run/tests/fixtures/inert-phase-runner.sh" | cut -d' ' -f1)" "$receipt"
grep -Fxq "early_executed_invoke_attempt_sha256=$(sha256sum "$run/procedure/invoke-attempt.sh" | cut -d' ' -f1)" "$receipt"
grep -Fxq "late_executed_invoke_attempt_sha256=$(sha256sum "$run/procedure/invoke-attempt.sh" | cut -d' ' -f1)" "$receipt"
grep -Fxq "success_executed_invoke_attempt_sha256=$(sha256sum "$run/procedure/invoke-attempt.sh" | cut -d' ' -f1)" "$receipt"
grep -Fq 'tests/real-wrapper-failure.sh' "$run/control/frozen-boundary.sha256"
grep -Fq 'tests/fixtures/inert-phase-runner.sh' "$run/control/frozen-boundary.sha256"
grep -Fq $'type\tmode\tbytes\tsha256\tcanonical_path\tpath' \
  "$run/control/frozen-boundary.inventory.tsv"
[[ -f $run/control/lifecycle-admission.txt ]]
printf 'self-test input freeze, replay, and identity binding: PASS\n'
