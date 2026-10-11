#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d /tmp/hatchery-final-cleanup-containment.XXXXXX)
cleanup() {
  chmod -R u+rwX "$scratch" 2>/dev/null || true
  find "$scratch" -depth -delete
}
trap cleanup EXIT

add_attempt() {
  local run=$1 package=$2 attempt
  /usr/bin/bash "$source_root/tests/fixtures/create-accepted-attempt.sh" \
    "$run" "$package" 001 "$lifecycle_sha"
  attempt="$run/attempts/${package}-attempt-001"
  printf 'cargo\n' >"$attempt/work/cargo/cache"
  printf 'source\n' >"$attempt/work/srcdest/source"
}

make_run() {
  local run="$scratch/$1"
  mkdir -p "$run/procedure" "$run/recipes" "$run/tests" "$run/inputs/rustup" \
    "$run/setup-scratch/home" "$run/setup-scratch/cargo"
  cp "$source_root/procedure/final-cleanup.sh" \
    "$source_root/procedure/lifecycle-admission.sh" \
    "$source_root/procedure/validate-canonical-attempt.sh" \
    "$source_root/procedure/freeze-boundary.sh" \
    "$source_root/procedure/verify-frozen-boundary.sh" \
    "$source_root/procedure/verify-reviewed-source.sh" \
    "$source_root/procedure/verify-toolchain.sh" \
    "$source_root/procedure/verify-toolchain-links.sh" "$run/procedure/"
  printf 'toolchain\n' >"$run/inputs/rustup/tool"
  (
    cd "$run"
    sha256sum inputs/rustup/tool >inputs/rust-toolchain.sha256
    printf 'type\tmode\tbytes\tsha256_or_target\tpath\n' >inputs/rust-toolchain.inventory.tsv
    printf 'file\t%s\t%s\t%s\tinputs/rustup/tool\n' \
      "$(stat -c %a inputs/rustup/tool)" "$(stat -c %s inputs/rustup/tool)" \
      "$(sha256sum inputs/rustup/tool | cut -d' ' -f1)" \
      >>inputs/rust-toolchain.inventory.tsv
  )
  /usr/bin/bash "$source_root/tests/fixtures/create-reviewed-source-admission.sh" "$run"
  /usr/bin/bash "$run/procedure/freeze-boundary.sh" >/dev/null
  /usr/bin/bash "$source_root/tests/fixtures/create-lifecycle-admission.sh" "$run"
  lifecycle_sha=$(sha256sum "$run/control/lifecycle-admission.txt" | cut -d' ' -f1)
  add_attempt "$run" sequoia-sq-pqc
  add_attempt "$run" sequoia-sqv-pqc
  printf '%s\n' "$run"
}

expect_cleanup_rejection() {
  local run=$1 log=$2 sentinel
  shift 2
  if /usr/bin/bash "$run/procedure/final-cleanup.sh" \
    sequoia-sq-pqc=001 sequoia-sqv-pqc=001 >"$log" 2>&1; then
    printf 'unsafe cleanup unexpectedly succeeded: %s\n' "$run" >&2
    exit 1
  fi
  for sentinel in "$@"; do [[ -e $sentinel ]]; done
}

valid=$(make_run valid)
printf 'delete setup home\n' >"$valid/setup-scratch/home/state"
printf 'delete setup cargo\n' >"$valid/setup-scratch/cargo/cache"
mkdir -p "$valid/attempts/failed/work/cargo"
printf 'preserve failed cache\n' >"$valid/attempts/failed/work/cargo/cache"
/usr/bin/bash "$valid/procedure/final-cleanup.sh" \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001 >/dev/null
for cache_root in setup-scratch/home setup-scratch/cargo \
  attempts/sequoia-sq-pqc-attempt-001/work/cargo \
  attempts/sequoia-sq-pqc-attempt-001/work/srcdest \
  attempts/sequoia-sqv-pqc-attempt-001/work/cargo \
  attempts/sequoia-sqv-pqc-attempt-001/work/srcdest; do
  [[ -z $(find "$valid/$cache_root" -mindepth 1 -print -quit) ]]
done
[[ -f $valid/attempts/failed/work/cargo/cache ]]

attempt_alias=$(make_run attempt-alias)
outside_attempt="$scratch/outside-attempt"
mv "$attempt_alias/attempts/sequoia-sq-pqc-attempt-001" "$outside_attempt"
ln -s "$outside_attempt" "$attempt_alias/attempts/sequoia-sq-pqc-attempt-001"
expect_cleanup_rejection "$attempt_alias" "$scratch/attempt-alias.log" \
  "$outside_attempt/work/cargo/cache" "$outside_attempt/work/srcdest/source"

work_alias=$(make_run work-alias)
outside_work="$scratch/outside-work"
mv "$work_alias/attempts/sequoia-sq-pqc-attempt-001/work" "$outside_work"
ln -s "$outside_work" "$work_alias/attempts/sequoia-sq-pqc-attempt-001/work"
expect_cleanup_rejection "$work_alias" "$scratch/work-alias.log" \
  "$outside_work/cargo/cache" "$outside_work/srcdest/source"

marker_alias=$(make_run marker-alias)
outside_marker="$scratch/outside-accepted-marker"
touch "$outside_marker"
rm "$marker_alias/attempts/sequoia-sq-pqc-attempt-001/receipts/ACCEPTED"
ln -s "$outside_marker" \
  "$marker_alias/attempts/sequoia-sq-pqc-attempt-001/receipts/ACCEPTED"
expect_cleanup_rejection "$marker_alias" "$scratch/marker-alias.log" \
  "$marker_alias/attempts/sequoia-sq-pqc-attempt-001/work/cargo/cache"

setup_alias=$(make_run setup-alias)
outside_setup="$scratch/outside-setup"
mv "$setup_alias/setup-scratch" "$outside_setup"
ln -s "$outside_setup" "$setup_alias/setup-scratch"
expect_cleanup_rejection "$setup_alias" "$scratch/setup-alias.log" \
  "$outside_setup/home" "$outside_setup/cargo"

printf 'final cleanup canonical containment and legitimate controls: PASS\n'
