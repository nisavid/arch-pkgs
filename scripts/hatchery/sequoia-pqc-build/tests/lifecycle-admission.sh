#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT

prerequisite_paths=(
  output/receipts/prebuild-environment.txt
  setup-evidence/common-setup.txt
  control/frozen-boundary.txt
  review/failure-boundary-self-test.txt
)
prerequisite_schemas=(
  arch-pq-prebuild-environment-v1
  arch-pq-common-setup-v2
  arch-pq-frozen-boundary-v1
  arch-pq-failure-boundary-self-test-v1
)
terminal_keys=(prebuild_capture_exit setup_exit frozen_boundary_exit self_test_exit)

make_run() {
  local run="$scratch/$1" package version executable attempt archive lifecycle_sha
  mkdir -p "$run"
  cp -a "$source_root/procedure" "$run/procedure"
  cp -a "$source_root/recipes" "$run/recipes"
  cp -a "$source_root/tests" "$run/tests"
  /usr/bin/bash "$run/tests/fixtures/create-reviewed-source-admission.sh" "$run"
  mkdir -p "$run/inputs/rustup" "$run/setup-scratch/home" "$run/setup-scratch/cargo"
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
  lifecycle_sha=$(sha256sum "$run/control/lifecycle-admission.txt" | cut -d' ' -f1)

  for package in sequoia-sq-pqc sequoia-sqv-pqc; do
    if [[ $package == sequoia-sq-pqc ]]; then version=1.4.0 executable=sq; else version=1.5.0 executable=sqv; fi
    attempt="$run/attempts/${package}-attempt-001"
    archive="$run/output/archives/${package}-${version}-4-x86_64.pkg.tar.zst"
    mkdir -p "$attempt/receipts" "$attempt/extracted/usr/bin" \
      "$attempt/work/cargo" "$attempt/work/srcdest" "$run/output/archives"
    printf 'accepted archive for %s\n' "$package" >"$archive"
    printf 'executable for %s\n' "$package" >"$attempt/extracted/usr/bin/$executable"
    touch "$attempt/receipts/ACCEPTED"
    printf 'schema=arch-pq-outer-launcher-v3\npackage=%s\nattempt=001\nstarted_utc=2026-09-30T00:00:00Z\ninitialization_claim_sha256=%064d\naccepted=false\nouter_exit=0\naccepted=true\nlifecycle_admission_sha256=%s\n' \
      "$package" 0 "$lifecycle_sha" >"$attempt/receipts/outer-launcher.txt"
    sha256sum "$archive" >"$attempt/receipts/output-archive.sha256"
  done
  /usr/bin/bash "$run/procedure/final-cleanup.sh" \
    sequoia-sq-pqc=001 sequoia-sqv-pqc=001 >/dev/null
  printf '%s\n' "$run"
}

mutate_prerequisite() {
  local run=$1 index=$2 mutation=$3
  local relative=${prerequisite_paths[$index]} record="$run/${prerequisite_paths[$index]}"
  local schema=${prerequisite_schemas[$index]} terminal=${terminal_keys[$index]}
  chmod u+w "$record" 2>/dev/null || true
  case "$mutation" in
    missing)
      rm "$record"
      ;;
    partial)
      sed -i "/^${terminal}=/d" "$record"
      ;;
    failed)
      sed -i "s/^${terminal}=0$/${terminal}=1/" "$record"
      ;;
    duplicate)
      printf '%s=0\n' "$terminal" >>"$record"
      ;;
    digest-mismatch)
      printf 'changed_after_admission=true\n' >>"$record"
      ;;
    substituted)
      printf 'schema=%s\nfixture=substituted-invalid-public-test-data\n%s=0\n' \
        "$schema" "$terminal" >"$record"
      ;;
    symlink)
      mv "$record" "$record.target"
      ln -s "$record.target" "$record"
      ;;
    nonregular)
      rm "$record"
      mkfifo "$record"
      ;;
    *) return 2 ;;
  esac
  printf '%s:%s' "$relative" "$mutation" >/dev/null
}

invoke_attempt() {
  local run=$1 attempt_id=$2
  env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
    HATCHERY_PROCEDURE_TEST_MODE=1 \
    HATCHERY_TEST_REQUIRE_LIFECYCLE=1 \
    HATCHERY_TEST_PHASE_RUNNER="$run/tests/fixtures/inert-phase-runner.sh" \
    /usr/bin/bash "$run/procedure/invoke-attempt.sh" synthetic-procedure-test "$attempt_id"
}

invoke_assembly() {
  local run=$1
  (cd "$run" && /usr/bin/bash procedure/assemble-evidence.sh \
    sequoia-sq-pqc=001 sequoia-sqv-pqc=001)
}

case_number=100
for index in 0 1 2 3; do
  for mutation in missing partial failed duplicate digest-mismatch substituted symlink nonregular; do
    run=$(make_run "attempt-${index}-${mutation}")
    mutate_prerequisite "$run" "$index" "$mutation"
    set +e
    invoke_attempt "$run" "$case_number" >/dev/null 2>&1
    attempt_exit=$?
    set -e
    (( attempt_exit != 0 ))
    [[ ! -e $run/attempts/synthetic-procedure-test-attempt-$case_number ]]

    run=$(make_run "assembly-${index}-${mutation}")
    mutate_prerequisite "$run" "$index" "$mutation"
    set +e
    invoke_assembly "$run" >/dev/null 2>&1
    assembly_exit=$?
    set -e
    (( assembly_exit != 0 ))
    [[ ! -e $run/review/final-source-and-evidence.inventory.tsv ]]
    case_number=$((case_number + 1))
  done
done

for seam in attempt assembly; do
  run=$(make_run "$seam-reordered")
  admission="$run/control/lifecycle-admission.txt"
  chmod u+w "$admission"
  awk 'NR == 3 { first=$0; next } NR == 4 { print; print first; next } { print }' \
    "$admission" >"$admission.reordered"
  mv "$admission.reordered" "$admission"
  set +e
  if [[ $seam == attempt ]]; then
    invoke_attempt "$run" 800 >/dev/null 2>&1
  else
    invoke_assembly "$run" >/dev/null 2>&1
  fi
  seam_exit=$?
  set -e
  (( seam_exit != 0 ))
done

run=$(make_run cross-attempt-mismatch)
sed -i 's/^lifecycle_admission_sha256=.*/lifecycle_admission_sha256=0000000000000000000000000000000000000000000000000000000000000000/' \
  "$run/attempts/sequoia-sqv-pqc-attempt-001/receipts/outer-launcher.txt"
set +e
invoke_assembly "$run" >/dev/null 2>&1
assembly_exit=$?
set -e
(( assembly_exit != 0 ))

run=$(make_run post-attempt-substitution)
old_lifecycle_sha=$(sha256sum "$run/control/lifecycle-admission.txt" | cut -d' ' -f1)
record="$run/output/receipts/prebuild-environment.txt"
printf 'schema=arch-pq-prebuild-environment-v1\nfixture=post-attempt-substitution\nprebuild_capture_exit=0\n' \
  >"$record"
chmod u+w "$run/control/lifecycle-admission.txt"
rm "$run/control/lifecycle-admission.txt"
/usr/bin/bash "$run/procedure/lifecycle-admission.sh" create >/dev/null
new_lifecycle_sha=$(sha256sum "$run/control/lifecycle-admission.txt" | cut -d' ' -f1)
[[ $new_lifecycle_sha != "$old_lifecycle_sha" ]]
set +e
invoke_attempt "$run" 801 >/dev/null 2>&1
attempt_exit=$?
set -e
(( attempt_exit != 0 ))
[[ ! -e $run/attempts/synthetic-procedure-test-attempt-801 ]]
set +e
invoke_assembly "$run" >/dev/null 2>&1
assembly_exit=$?
set -e
(( assembly_exit != 0 ))

run=$(make_run valid-attempt)
invoke_attempt "$run" 900 >/dev/null
attempt_receipt="$run/attempts/synthetic-procedure-test-attempt-900/receipts/outer-launcher.txt"
grep -Fxq "lifecycle_admission_sha256=$(sha256sum "$run/control/lifecycle-admission.txt" | cut -d' ' -f1)" \
  "$attempt_receipt"

run=$(make_run valid-assembly)
invoke_assembly "$run" >/dev/null
for relative in "${prerequisite_paths[@]}" control/lifecycle-admission.txt; do
  retained="$run/output/provenance/lifecycle/${relative##*/}"
  cmp -s "$run/$relative" "$retained"
  source_sha=$(sha256sum "$run/$relative" | cut -d' ' -f1)
  retained_sha=$(sha256sum "$retained" | cut -d' ' -f1)
  [[ $source_sha == "$retained_sha" ]]
  grep -Fq "$source_sha" "$run/output/provenance/lifecycle-admission.sha256"
done
grep -Fxq 'status=procedure-complete-successor-candidates-built-but-not-independently-accepted' \
  "$run/review/validation-status.txt"

printf 'lifecycle admission rejects incomplete or substituted prerequisites and retains exact success evidence: PASS\n'
