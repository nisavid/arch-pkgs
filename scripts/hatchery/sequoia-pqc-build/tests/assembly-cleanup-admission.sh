#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT

make_run() {
  local name=$1 cleanup_state=$2 run package version executable attempt archive
  run="$scratch/$name"
  mkdir -p "$run/procedure" "$run/recipes" "$run/tests" "$run/inputs/rustup" \
    "$run/output/archives" "$run/output/receipts"
  cp "$source_root/procedure/assemble-evidence.sh" \
    "$source_root/procedure/final-cleanup.sh" \
    "$source_root/procedure/freeze-boundary.sh" \
    "$source_root/procedure/lifecycle-admission.sh" \
    "$source_root/procedure/verify-toolchain.sh" \
    "$source_root/procedure/verify-toolchain-links.sh" \
    "$source_root/procedure/verify-frozen-boundary.sh" \
    "$source_root/procedure/verify-reviewed-source.sh" \
    "$source_root/procedure/write-run-inventory.sh" "$run/procedure/"
  printf 'toolchain\n' >"$run/inputs/rustup/tool"
  (
    cd "$run"
    sha256sum inputs/rustup/tool >inputs/rust-toolchain.sha256
    printf 'type\tmode\tbytes\tsha256_or_target\tpath\n' >inputs/rust-toolchain.inventory.tsv
    printf 'file\t%s\t%s\t%s\tinputs/rustup/tool\n' "$(stat -c %a inputs/rustup/tool)" \
      "$(stat -c %s inputs/rustup/tool)" "$(sha256sum inputs/rustup/tool | cut -d' ' -f1)" \
      >>inputs/rust-toolchain.inventory.tsv
  )
  /usr/bin/bash "$source_root/tests/fixtures/create-reviewed-source-admission.sh" "$run"
  /usr/bin/bash "$run/procedure/freeze-boundary.sh" >/dev/null
  if [[ $name != missing-lifecycle ]]; then
    /usr/bin/bash "$source_root/tests/fixtures/create-lifecycle-admission.sh" "$run"
  fi
  lifecycle_sha=
  if [[ -f $run/control/lifecycle-admission.txt ]]; then
    lifecycle_sha=$(sha256sum "$run/control/lifecycle-admission.txt" | cut -d' ' -f1)
  fi

  for package in sequoia-sq-pqc sequoia-sqv-pqc; do
    if [[ $package == sequoia-sq-pqc ]]; then version=1.4.0 executable=sq; else version=1.5.0 executable=sqv; fi
    attempt="$run/attempts/${package}-attempt-001"
    archive="$run/output/archives/${package}-${version}-4-x86_64.pkg.tar.zst"
    mkdir -p "$attempt/receipts" "$attempt/extracted/usr/bin" \
      "$attempt/work/cargo" "$attempt/work/srcdest"
    printf 'accepted archive for %s\n' "$package" >"$archive"
    printf 'executable for %s\n' "$package" >"$attempt/extracted/usr/bin/$executable"
    touch "$attempt/receipts/ACCEPTED"
    printf 'schema=arch-pq-outer-launcher-v2\naccepted=false\nouter_exit=0\naccepted=true\n' \
      >"$attempt/receipts/outer-launcher.txt"
    if [[ -n $lifecycle_sha ]]; then
      printf 'lifecycle_admission_sha256=%s\n' "$lifecycle_sha" \
        >>"$attempt/receipts/outer-launcher.txt"
    fi
    sha256sum "$archive" >"$attempt/receipts/output-archive.sha256"
  done

  case "$cleanup_state" in
    missing) ;;
    partial)
      printf 'schema=arch-pq-final-public-cache-cleanup-v3\ntoolchain_preserved=true\n' \
        >"$run/output/receipts/final-public-cache-cleanup.txt"
      ;;
    failed)
      printf 'schema=arch-pq-final-public-cache-cleanup-v3\ntoolchain_preserved=true\ncleanup_exit=1\n' \
        >"$run/output/receipts/final-public-cache-cleanup.txt"
      ;;
    valid)
      /usr/bin/bash "$run/procedure/final-cleanup.sh" \
        sequoia-sq-pqc=001 sequoia-sqv-pqc=001 >/dev/null
      ;;
    *) return 2 ;;
  esac
  printf '%s\n' "$run"
}

for state in missing partial failed; do
  run=$(make_run "$state" "$state")
  set +e
  (cd "$run" && /usr/bin/bash procedure/assemble-evidence.sh \
    sequoia-sq-pqc=001 sequoia-sqv-pqc=001) >/dev/null 2>&1
  status=$?
  set -e
  (( status != 0 ))
  [[ ! -e $run/review/final-source-and-evidence.inventory.tsv ]]
done

run=$(make_run missing-lifecycle valid)
set +e
(cd "$run" && /usr/bin/bash procedure/assemble-evidence.sh \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001) >/dev/null 2>&1
status=$?
set -e
(( status != 0 ))
[[ ! -e $run/review/final-source-and-evidence.inventory.tsv ]]

run=$(make_run valid valid)
(cd "$run" && /usr/bin/bash procedure/assemble-evidence.sh \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001) >/dev/null
cleanup_receipt="$run/output/receipts/final-public-cache-cleanup.txt"
cleanup_hash="$run/output/provenance/final-public-cache-cleanup.sha256"
[[ -f $cleanup_hash ]]
grep -Fq "$(sha256sum "$cleanup_receipt" | cut -d' ' -f1)" "$cleanup_hash"
grep -Fq 'review-admission/source-revision.txt' \
  "$run/review/final-source-and-evidence.inventory.tsv"
grep -Fq 'output/provenance/reviewed-source-admission.sha256' \
  "$run/review/final-source-and-evidence.inventory.tsv"
cat >"$scratch/expected-status" <<'EOF'
status=procedure-complete-successor-candidates-built-but-not-independently-accepted
downstream_operation_gate=open
macos_interoperability_gate=open
installation_gate=open
rollback_authenticity_gate=open
acceptance_gate=open
deployment_gate=open
EOF
cmp -s "$scratch/expected-status" "$run/review/validation-status.txt"
printf 'assembly cleanup admission and complete gates: PASS\n'
