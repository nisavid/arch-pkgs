#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT

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
    printf 'cache\n' >"$attempt/work/cargo/cache"
    printf 'source\n' >"$attempt/work/srcdest/source"
    touch "$attempt/receipts/ACCEPTED"
    printf 'schema=arch-pq-outer-launcher-v2\naccepted=false\nouter_exit=0\naccepted=true\nlifecycle_admission_sha256=%s\n' \
      "$lifecycle_sha" >"$attempt/receipts/outer-launcher.txt"
    sha256sum "$archive" >"$attempt/receipts/output-archive.sha256"
  done
  printf '%s\n' "$run"
}

missing=$(make_run missing)
find "$missing/attempts" -depth -delete
set +e
/usr/bin/bash "$missing/procedure/final-cleanup.sh" \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001 >/dev/null 2>&1
status=$?
set -e
(( status != 0 ))

exact=$(make_run exact)
/usr/bin/bash "$exact/procedure/final-cleanup.sh" \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001 >/dev/null
receipt="$exact/output/receipts/final-public-cache-cleanup.txt"
grep -Fxq 'schema=arch-pq-final-public-cache-cleanup-v3' "$receipt"
[[ $(grep -c $'^selection\t' "$receipt") == 2 ]]
for package in sequoia-sq-pqc sequoia-sqv-pqc; do
  [[ -z $(find "$exact/attempts/${package}-attempt-001/work/cargo" -mindepth 1 -print -quit) ]]
  [[ -z $(find "$exact/attempts/${package}-attempt-001/work/srcdest" -mindepth 1 -print -quit) ]]
done
(cd "$exact" && /usr/bin/bash procedure/assemble-evidence.sh \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001) >/dev/null

substituted=$(make_run substituted)
/usr/bin/bash "$substituted/procedure/final-cleanup.sh" \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001 >/dev/null
printf 'substituted archive\n' \
  >>"$substituted/output/archives/sequoia-sq-pqc-1.4.0-4-x86_64.pkg.tar.zst"
set +e
(cd "$substituted" && /usr/bin/bash procedure/assemble-evidence.sh \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001) >/dev/null 2>&1
status=$?
set -e
(( status != 0 ))

recontaminated=$(make_run recontaminated)
/usr/bin/bash "$recontaminated/procedure/final-cleanup.sh" \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001 >/dev/null
printf 'later cache content\n' \
  >"$recontaminated/attempts/sequoia-sq-pqc-attempt-001/work/cargo/later"
set +e
(cd "$recontaminated" && /usr/bin/bash procedure/assemble-evidence.sh \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001) >/dev/null 2>&1
status=$?
set -e
(( status != 0 ))

attempt_substitution=$(make_run attempt-substitution)
/usr/bin/bash "$attempt_substitution/procedure/final-cleanup.sh" \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001 >/dev/null
cp -a "$attempt_substitution/attempts/sequoia-sq-pqc-attempt-001" \
  "$attempt_substitution/attempts/sequoia-sq-pqc-attempt-002"
set +e
(cd "$attempt_substitution" && /usr/bin/bash procedure/assemble-evidence.sh \
  sequoia-sq-pqc=002 sequoia-sqv-pqc=001) >/dev/null 2>&1
status=$?
set -e
(( status != 0 ))

sealed=$(make_run sealed)
/usr/bin/bash "$sealed/procedure/final-cleanup.sh" \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001 >/dev/null
find "$sealed/output/archives" -type f -delete
set +e
/usr/bin/bash "$sealed/procedure/invoke-attempt.sh" sequoia-sq-pqc 002 \
  >"$scratch/sealed-attempt.log" 2>&1
status=$?
set -e
(( status != 0 ))
[[ ! -e $sealed/attempts/sequoia-sq-pqc-attempt-002 ]]
grep -Fq 'finalization' "$scratch/sealed-attempt.log"
printf 'cleanup and assembly bind exact final selections: PASS\n'
