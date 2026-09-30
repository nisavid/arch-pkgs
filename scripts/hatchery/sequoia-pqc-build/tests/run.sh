#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
for test_script in \
  "$tests_dir/reviewed-source-admission.sh" \
  "$tests_dir/real-wrapper-failure.sh" \
  "$tests_dir/controller-source-view-isolation.sh" \
  "$tests_dir/actual-boundary-isolation.sh" \
  "$tests_dir/payload-path-scan.sh" \
  "$tests_dir/archive-list-safety.sh" \
  "$tests_dir/frozen-input-object-types.sh" \
  "$tests_dir/final-cleanup-preserves-toolchain.sh" \
  "$tests_dir/final-cleanup-containment.sh" \
  "$tests_dir/lifecycle-admission.sh" \
  "$tests_dir/assembly-cleanup-admission.sh" \
  "$tests_dir/finalization-selection-binding.sh" \
  "$tests_dir/self-test-input-binding.sh" \
  "$tests_dir/self-test-freeze-alias.sh" \
  "$tests_dir/runtime-closure-isolation.sh" \
  "$tests_dir/run-inventory-binds-status.sh" \
  "$tests_dir/toolchain-symlink-confinement.sh" \
  "$tests_dir/toolchain-object-types.sh" \
  "$tests_dir/static-contract.sh" \
  "$tests_dir/negative-source-assertions.sh"
do
  /usr/bin/bash "$test_script"
done
printf 'procedure test suite: PASS\n'
