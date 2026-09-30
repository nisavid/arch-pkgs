#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT

make_run() {
  local name=$1 run
  run="$scratch/$name"
  mkdir -p "$run/procedure" "$run/recipes/inert" "$run/tests/fixtures" "$run/inputs/rustup"
  cp "$source_root/procedure/freeze-boundary.sh" \
    "$source_root/procedure/failure-boundary-self-test.sh" \
    "$source_root/procedure/initialize-attempt.sh" \
    "$source_root/procedure/invoke-attempt.sh" \
    "$source_root/procedure/lifecycle-admission.sh" \
    "$source_root/procedure/verify-frozen-boundary.sh" \
    "$source_root/procedure/verify-reviewed-source.sh" "$run/procedure/"
  cp "$source_root/tests/real-wrapper-failure.sh" "$run/tests/"
  cp "$source_root/tests/fixtures/inert-phase-runner.sh" "$run/tests/fixtures/"
  printf 'recipe\n' >"$run/recipes/inert/README"
  printf 'toolchain\n' >"$run/inputs/rustup/tool"
  (cd "$run" && sha256sum inputs/rustup/tool >inputs/rust-toolchain.sha256)
  mkdir -p "$run/output/receipts" "$run/setup-evidence"
  printf 'schema=arch-pq-prebuild-environment-v1\nfixture=invalid-public-test-data\nprebuild_capture_exit=0\n' \
    >"$run/output/receipts/prebuild-environment.txt"
  printf 'schema=arch-pq-common-setup-v2\nfixture=invalid-public-test-data\nsetup_exit=0\n' \
    >"$run/setup-evidence/common-setup.txt"
  /usr/bin/bash "$source_root/tests/fixtures/create-reviewed-source-admission.sh" "$run"
  /usr/bin/bash "$run/procedure/freeze-boundary.sh" >/dev/null
  printf '%s\n' "$run"
}

clean_run=$(make_run clean)
/usr/bin/bash "$clean_run/procedure/failure-boundary-self-test.sh"
grep -Fxq 'self_test_exit=0' "$clean_run/review/failure-boundary-self-test.txt"

alias_run=$(make_run alias)
external="$scratch/external"
sentinel="$scratch/unfrozen-procedure-executed"
mkdir -p "$external/procedure" "$external/tests/fixtures"
cp "$alias_run/tests/real-wrapper-failure.sh" "$external/tests/"
cp "$alias_run/tests/fixtures/inert-phase-runner.sh" "$external/tests/fixtures/"
cp "$alias_run/procedure/invoke-attempt.sh" "$external/procedure/invoke-attempt.real"
# shellcheck disable=SC2016 # Expansion belongs to the generated wrapper.
printf '%s\n' '#!/usr/bin/bash' "printf 'executed\\n' >'$sentinel'" \
  'exec /usr/bin/bash "${BASH_SOURCE[0]%/*}/invoke-attempt.real" "$@"' \
  >"$external/procedure/invoke-attempt.sh"
chmod 755 "$external/procedure/invoke-attempt.sh" "$external/procedure/invoke-attempt.real"
rm "$alias_run/tests/real-wrapper-failure.sh"
ln -s "$external/tests/real-wrapper-failure.sh" "$alias_run/tests/real-wrapper-failure.sh"

set +e
/usr/bin/bash "$alias_run/procedure/failure-boundary-self-test.sh" >/dev/null 2>&1
status=$?
set -e
(( status != 0 ))
[[ ! -e $sentinel ]]

printf 'self-test rejects a same-byte symlink alias before execution: PASS\n'
