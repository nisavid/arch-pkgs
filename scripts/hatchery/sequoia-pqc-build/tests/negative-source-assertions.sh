#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
cleanup() {
  chmod -R u+rwX "$scratch" 2>/dev/null || true
  find "$scratch" -depth -delete
}
trap cleanup EXIT

run_positive_control() {
  local test_script=$1
  if ! /usr/bin/bash "$source_root/tests/$test_script" >/dev/null; then
    printf '%s: unchanged positive control failed\n' "$test_script" >&2
    exit 1
  fi
}

expect_injection_rejected() {
  local case_name=$1 test_script=$2 target=$3 forbidden=$4
  local case_root="$scratch/$case_name" status
  mkdir -p "$case_root"
  cp -a "$source_root/." "$case_root/"
  printf '\n%s\n' "$forbidden" >>"$case_root/$target"
  set +e
  /usr/bin/bash "$case_root/tests/$test_script" \
    >"$scratch/$case_name.stdout" 2>"$scratch/$case_name.stderr"
  status=$?
  set -e
  if (( status == 0 )); then
    printf '%s: forbidden source pattern was not rejected\n' "$case_name" >&2
    exit 1
  fi
}

run_positive_control static-contract.sh
run_positive_control controller-source-view-isolation.sh
# shellcheck disable=SC2016 # The injected source fragment must stay literal.
expect_injection_rejected broad-work-bind static-contract.sh \
  procedure/invoke-attempt.sh '# --bind "$host_root" /work'
expect_injection_rejected build-phase-admission-write static-contract.sh \
  procedure/attempt-body.sh '# receipts/'
# shellcheck disable=SC1003 # The trailing backslash is the literal source pattern.
expect_injection_rejected cleanup-removes-toolchain static-contract.sh \
  procedure/final-cleanup.sh 'inputs/rustup" \'
# shellcheck disable=SC2016 # The injected source fragment must stay literal.
expect_injection_rejected post-build-source-verification static-contract.sh \
  procedure/post-build-verify.sh '# git -C "$work/srcdest/$repo" verify-tag'
# shellcheck disable=SC2016 # The injected source fragment must stay literal.
expect_injection_rejected controller-post-build-source-verification \
  controller-source-view-isolation.sh procedure/post-build-verify.sh \
  '# git -C "$work/srcdest/$repo" verify-tag'

printf 'negative source assertions reject every forbidden pattern: PASS\n'
