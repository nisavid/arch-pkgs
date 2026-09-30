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

make_run() {
  local name=$1 run="$scratch/$1"
  mkdir -p "$run"
  cp -a "$source_root/procedure" "$run/procedure"
  cp -a "$source_root/tests" "$run/tests"
  printf '%s\n' "$run"
}

make_lifecycle_run() {
  local name=$1 run
  run=$(make_run "$name")
  mkdir -p "$run/recipes/invalid-public-fixture" "$run/inputs/rustup"
  printf 'invalid public recipe fixture\n' >"$run/recipes/invalid-public-fixture/PKGBUILD"
  /usr/bin/bash "$run/tests/fixtures/create-reviewed-source-admission.sh" "$run"
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
  /usr/bin/bash "$run/tests/fixtures/create-lifecycle-admission.sh" "$run"
  printf '%s\n' "$run"
}

invoke_synthetic() {
  local run=$1 attempt_id=$2 hook_kind=${3-} hook_step=${4-} require_lifecycle=${5-0}
  local -a hook=()
  case "$hook_kind" in
    '') ;;
    fail) hook=(HATCHERY_TEST_INITIALIZE_FAIL_STEP="$hook_step") ;;
    signal) hook=(HATCHERY_TEST_INITIALIZE_SIGNAL_STEP="$hook_step") ;;
    interrupt) hook=(HATCHERY_TEST_INITIALIZE_INTERRUPT_STEP="$hook_step") ;;
    *) return 2 ;;
  esac
  env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
    HATCHERY_PROCEDURE_TEST_MODE=1 \
    HATCHERY_TEST_REQUIRE_LIFECYCLE="$require_lifecycle" \
    HATCHERY_TEST_PHASE_RUNNER="$run/tests/fixtures/inert-phase-runner.sh" \
    "${hook[@]}" \
    /usr/bin/bash "$run/procedure/invoke-attempt.sh" synthetic-procedure-test "$attempt_id"
}

tree_identity() {
  local tree=$1
  (
    cd "$tree"
    find . -mindepth 1 -printf '%y\t%m\t%p\n' | LC_ALL=C sort
    find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum
  )
}

assert_failed_initialization() {
  local case_name=$1 hook_kind=$2 hook_step=$3 run staging canonical test_exit
  local evidence_root evidence_before evidence_after same_id_exit path_count
  run=$(make_run "$case_name")
  staging="$run/attempts/.initializing-synthetic-procedure-test-attempt-001"
  canonical="$run/attempts/synthetic-procedure-test-attempt-001"
  set +e
  invoke_synthetic "$run" 001 "$hook_kind" "$hook_step" >/dev/null 2>&1
  test_exit=$?
  set -e
  (( test_exit != 0 ))
  [[ ! -e $canonical/receipts/ACCEPTED ]]
  [[ ! -e $run/output/archives/synthetic-procedure-test-0-4-x86_64.pkg.tar.zst ]]

  case "$hook_step" in
    after-canonical-rename)
      [[ ! -e $staging && -d $canonical ]]
      evidence_root=$canonical
      ;;
    after-staging|after-claim-*|after-directory-*|after-chmod-*|after-launcher-*|before-canonical-rename)
      [[ -d $staging && ! -e $canonical ]]
      evidence_root=$staging
      ;;
    *)
      [[ ! -e $staging && ! -e $canonical ]]
      return 0
      ;;
  esac

  evidence_before=$(tree_identity "$evidence_root")
  set +e
  invoke_synthetic "$run" 001 >/dev/null 2>&1
  same_id_exit=$?
  set -e
  (( same_id_exit != 0 ))
  evidence_after=$(tree_identity "$evidence_root")
  [[ $evidence_after == "$evidence_before" ]]
  path_count=0
  [[ ! -e $staging ]] || path_count=$((path_count + 1))
  [[ ! -e $canonical ]] || path_count=$((path_count + 1))
  (( path_count == 1 ))
}

failure_steps=(
  after-attempts-root
  after-output-archives
  before-staging
  after-staging
  after-claim-write
  after-claim-chmod
  after-claim-publish
  after-directory-receipts
  after-directory-logs
  after-directory-extracted
  after-directory-procedure-snapshot
  after-directory-work
  after-directory-work-home
  after-directory-work-cargo
  after-directory-work-srcdest
  after-directory-work-builddir
  after-directory-work-pkgdest
  after-directory-work-logdest
  after-directory-work-tmp
  after-directory-work-runtime-home
  after-directory-work-gnupg-runtime
  after-directory-work-xdg-cache
  after-directory-work-xdg-config
  after-directory-work-xdg-data
  after-chmod-work-home
  after-chmod-work-tmp
  after-chmod-work-runtime-home
  after-launcher-write
  after-launcher-chmod
  after-launcher-publish
  after-launcher-validation
  before-canonical-rename
  after-canonical-rename
)
for step in "${failure_steps[@]}"; do
  assert_failed_initialization "failure-$step" fail "$step"
done
assert_failed_initialization catchable-signal signal after-launcher-publish
assert_failed_initialization abrupt-interruption interrupt after-launcher-publish

run=$(make_run successful-publication)
invoke_synthetic "$run" 001 >/dev/null
[[ ! -e $run/attempts/.initializing-synthetic-procedure-test-attempt-001 ]]
[[ -f $run/attempts/synthetic-procedure-test-attempt-001/receipts/ACCEPTED ]]
/usr/bin/bash "$run/procedure/initialize-attempt.sh" verify \
  "$run/attempts/synthetic-procedure-test-attempt-001" ''

run=$(make_lifecycle_run lifecycle-recovery)
lifecycle_sha=$(sha256sum "$run/control/lifecycle-admission.txt" | cut -d' ' -f1)
staging="$run/attempts/.initializing-synthetic-procedure-test-attempt-001"
set +e
invoke_synthetic "$run" 001 fail after-launcher-publish 1 >/dev/null 2>&1
test_exit=$?
set -e
(( test_exit != 0 ))
grep -Fxq "lifecycle_admission_sha256=$lifecycle_sha" "$staging/receipts/outer-launcher.txt"
staged_before=$(tree_identity "$staging")
set +e
invoke_synthetic "$run" 001 '' '' 1 >/dev/null 2>&1
same_id_exit=$?
set -e
(( same_id_exit != 0 ))
[[ $(tree_identity "$staging") == "$staged_before" ]]
invoke_synthetic "$run" 002 '' '' 1 >/dev/null
grep -Fxq "lifecycle_admission_sha256=$lifecycle_sha" \
  "$run/attempts/synthetic-procedure-test-attempt-002/receipts/outer-launcher.txt"
[[ -d $staging ]]

write_launcher() {
  local launcher=$1 package=$2 attempt_id=$3 lifecycle_sha=$4
  printf 'schema=arch-pq-outer-launcher-v3\npackage=%s\nattempt=%s\nstarted_utc=2026-09-30T00:00:00Z\ninitialization_claim_sha256=%064d\naccepted=false\nlifecycle_admission_sha256=%s\n' \
    "$package" "$attempt_id" 0 "$lifecycle_sha" >"$launcher"
}

for mutation in missing malformed duplicate-field identity-mismatch lifecycle-mismatch; do
  run=$(make_lifecycle_run "canonical-$mutation")
  lifecycle_sha=$(sha256sum "$run/control/lifecycle-admission.txt" | cut -d' ' -f1)
  prior="$run/attempts/synthetic-procedure-test-attempt-001"
  mkdir -p "$prior/receipts"
  launcher="$prior/receipts/outer-launcher.txt"
  if [[ $mutation != missing ]]; then
    write_launcher "$launcher" synthetic-procedure-test 001 "$lifecycle_sha"
  fi
  case "$mutation" in
    missing) ;;
    malformed) sed -i 's/^schema=.*/schema=invalid/' "$launcher" ;;
    duplicate-field) printf 'package=synthetic-procedure-test\n' >>"$launcher" ;;
    identity-mismatch) sed -i 's/^attempt=001$/attempt=999/' "$launcher" ;;
    lifecycle-mismatch)
      sed -i 's/^lifecycle_admission_sha256=.*/lifecycle_admission_sha256=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff/' "$launcher"
      ;;
  esac
  set +e
  invoke_synthetic "$run" 002 '' '' 1 >/dev/null 2>&1
  test_exit=$?
  set -e
  (( test_exit != 0 ))
  [[ ! -e $run/attempts/synthetic-procedure-test-attempt-002 ]]
  [[ ! -e $run/attempts/.initializing-synthetic-procedure-test-attempt-002 ]]
  [[ ! -e $run/output/archives/synthetic-procedure-test-0-4-x86_64.pkg.tar.zst ]]
done

printf 'attempt initialization recovers without rewriting evidence and rejects invalid canonical receipts: PASS\n'
