#!/usr/bin/bash
set -Eeuo pipefail

(( $# == 1 )) || { printf 'usage: %s RUN_ROOT\n' "$0" >&2; exit 2; }
run=$(cd "$1" && pwd -P)
[[ -f $run/control/frozen-boundary.txt && ! -L $run/control/frozen-boundary.txt ]]
mkdir -p "$run/output/receipts" "$run/setup-evidence" "$run/review"
printf 'schema=arch-pq-prebuild-environment-v1\nfixture=invalid-public-test-data\nprebuild_capture_exit=0\n' \
  >"$run/output/receipts/prebuild-environment.txt"
printf 'schema=arch-pq-common-setup-v2\nfixture=invalid-public-test-data\nsetup_exit=0\n' \
  >"$run/setup-evidence/common-setup.txt"
printf 'schema=arch-pq-failure-boundary-self-test-v1\nfixture=invalid-public-test-data\nself_test_exit=0\n' \
  >"$run/review/failure-boundary-self-test.txt"
/usr/bin/bash "$run/procedure/lifecycle-admission.sh" create >/dev/null
