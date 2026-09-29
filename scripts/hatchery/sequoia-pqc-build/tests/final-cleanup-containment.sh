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

make_run() {
  local run="$scratch/$1"
  mkdir -p "$run/procedure" "$run/recipes" "$run/tests" "$run/inputs/rustup" \
    "$run/setup-scratch/home" "$run/setup-scratch/cargo" "$run/attempts"
  cp "$source_root/procedure/final-cleanup.sh" \
    "$source_root/procedure/freeze-boundary.sh" \
    "$source_root/procedure/verify-frozen-boundary.sh" \
    "$source_root/procedure/verify-toolchain.sh" "$run/procedure/"
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
  /usr/bin/bash "$run/procedure/freeze-boundary.sh" >/dev/null
  printf '%s\n' "$run"
}

expect_cleanup_rejection() {
  local run=$1 log=$2 sentinel
  shift 2
  if /usr/bin/bash "$run/procedure/final-cleanup.sh" >"$log" 2>&1; then
    for sentinel in "$@"; do
      [[ ! -e $sentinel ]] || {
        printf 'unsafe cleanup passed without deleting expected sentinel: %s\n' \
          "$sentinel" >&2
        exit 1
      }
    done
    printf 'unsafe cleanup deleted protected sentinels: %s\n' "$run" >&2
    exit 1
  fi
  for sentinel in "$@"; do
    [[ -e $sentinel ]]
  done
}

valid=$(make_run valid)
mkdir -p "$valid/attempts/accepted/work/cargo" "$valid/attempts/accepted/work/srcdest" \
  "$valid/attempts/accepted/receipts" "$valid/attempts/failed/work/cargo"
touch "$valid/attempts/accepted/receipts/ACCEPTED"
printf 'delete setup home\n' >"$valid/setup-scratch/home/state"
printf 'delete setup cargo\n' >"$valid/setup-scratch/cargo/cache"
printf 'delete accepted cargo\n' >"$valid/attempts/accepted/work/cargo/cache"
printf 'delete accepted source\n' >"$valid/attempts/accepted/work/srcdest/source"
printf 'preserve failed cache\n' >"$valid/attempts/failed/work/cargo/cache"
/usr/bin/bash "$valid/procedure/final-cleanup.sh" >/dev/null
for cache_root in setup-scratch/home setup-scratch/cargo \
  attempts/accepted/work/cargo attempts/accepted/work/srcdest; do
  [[ -z $(find "$valid/$cache_root" -mindepth 1 -print -quit) ]]
done
[[ -f $valid/attempts/failed/work/cargo/cache ]]

attempt_alias=$(make_run attempt-alias)
outside_attempt="$scratch/outside-attempt"
mkdir -p "$outside_attempt/receipts" "$outside_attempt/work/cargo" \
  "$outside_attempt/work/srcdest"
touch "$outside_attempt/receipts/ACCEPTED"
printf 'external cargo sentinel\n' >"$outside_attempt/work/cargo/sentinel"
printf 'external source sentinel\n' >"$outside_attempt/work/srcdest/sentinel"
ln -s "$outside_attempt" "$attempt_alias/attempts/forged"
expect_cleanup_rejection "$attempt_alias" "$scratch/attempt-alias.log" \
  "$outside_attempt/work/cargo/sentinel" "$outside_attempt/work/srcdest/sentinel"
[[ -f $outside_attempt/work/cargo/sentinel ]]
[[ -f $outside_attempt/work/srcdest/sentinel ]]

work_alias=$(make_run work-alias)
outside_work="$scratch/outside-work"
mkdir -p "$work_alias/attempts/accepted/receipts" "$outside_work/cargo" "$outside_work/srcdest"
touch "$work_alias/attempts/accepted/receipts/ACCEPTED"
printf 'external cargo sentinel\n' >"$outside_work/cargo/sentinel"
printf 'external source sentinel\n' >"$outside_work/srcdest/sentinel"
ln -s "$outside_work" "$work_alias/attempts/accepted/work"
expect_cleanup_rejection "$work_alias" "$scratch/work-alias.log" \
  "$outside_work/cargo/sentinel" "$outside_work/srcdest/sentinel"
[[ -f $outside_work/cargo/sentinel ]]
[[ -f $outside_work/srcdest/sentinel ]]

marker_alias=$(make_run marker-alias)
outside_marker="$scratch/outside-accepted-marker"
mkdir -p "$marker_alias/attempts/forged/receipts" \
  "$marker_alias/attempts/forged/work/cargo" "$marker_alias/attempts/forged/work/srcdest"
touch "$outside_marker"
ln -s "$outside_marker" "$marker_alias/attempts/forged/receipts/ACCEPTED"
printf 'preserve forged cargo\n' >"$marker_alias/attempts/forged/work/cargo/cache"
expect_cleanup_rejection "$marker_alias" "$scratch/marker-alias.log" \
  "$marker_alias/attempts/forged/work/cargo/cache"
[[ -f $marker_alias/attempts/forged/work/cargo/cache ]]

setup_alias=$(make_run setup-alias)
outside_setup="$scratch/outside-setup"
rm -r "$setup_alias/setup-scratch"
mkdir -p "$outside_setup/home" "$outside_setup/cargo"
printf 'external home sentinel\n' >"$outside_setup/home/sentinel"
printf 'external cargo sentinel\n' >"$outside_setup/cargo/sentinel"
ln -s "$outside_setup" "$setup_alias/setup-scratch"
expect_cleanup_rejection "$setup_alias" "$scratch/setup-alias.log" \
  "$outside_setup/home/sentinel" "$outside_setup/cargo/sentinel"
[[ -f $outside_setup/home/sentinel ]]
[[ -f $outside_setup/cargo/sentinel ]]

printf 'final cleanup canonical containment and legitimate controls: PASS\n'
