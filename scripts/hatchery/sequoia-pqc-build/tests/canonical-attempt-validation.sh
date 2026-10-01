#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'chmod -R u+rwX "$scratch" 2>/dev/null || true; find "$scratch" -depth -delete' EXIT

make_run() {
  local run="$scratch/$1" lifecycle_sha package version executable attempt archive
  mkdir -p "$run"
  cp -a "$source_root/procedure" "$run/procedure"
  cp -a "$source_root/recipes" "$run/recipes"
  cp -a "$source_root/tests" "$run/tests"
  /usr/bin/bash "$run/tests/fixtures/create-reviewed-source-admission.sh" "$run"
  mkdir -p "$run/inputs/rustup"
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
    if [[ $package == sequoia-sq-pqc ]]; then
      version=1.4.0
      executable=sq
    else
      version=1.5.0
      executable=sqv
    fi
    /usr/bin/bash "$run/procedure/initialize-attempt.sh" create \
      "$package" 001 "$lifecycle_sha"
    attempt="$run/attempts/${package}-attempt-001"
    archive="$run/output/archives/${package}-${version}-4-x86_64.pkg.tar.zst"
    mkdir -p "$attempt/extracted/usr/bin"
    printf 'accepted archive for %s\n' "$package" >"$archive"
    printf 'executable for %s\n' "$package" >"$attempt/extracted/usr/bin/$executable"
    printf 'cache sentinel\n' >"$attempt/work/cargo/cache"
    printf 'source sentinel\n' >"$attempt/work/srcdest/source"
    sha256sum "$archive" >"$attempt/receipts/output-archive.sha256"
    printf 'completed_utc=2026-09-30T00:00:01Z\nouter_exit=0\naccepted=true\noutput_archive=%s\n' \
      "$archive" >>"$attempt/receipts/outer-launcher.txt"
    touch "$attempt/receipts/ACCEPTED"
  done
  printf '%s\n' "$run"
}

save_attempt() {
  local run=$1
  cp -a "$run/attempts/sequoia-sq-pqc-attempt-001" "$run/.pristine-sq-attempt"
}

restore_attempt() {
  local run=$1 attempt
  attempt="$run/attempts/sequoia-sq-pqc-attempt-001"
  find "$attempt" -depth -delete
  cp -a "$run/.pristine-sq-attempt" "$attempt"
}

mutate_attempt() {
  local run=$1 mutation=$2
  local attempt="$run/attempts/sequoia-sq-pqc-attempt-001"
  local claim="$attempt/initialization-claim.txt"
  local launcher="$attempt/receipts/outer-launcher.txt"
  [[ ! -f $claim ]] || chmod u+w "$claim"
  case "$mutation" in
    claim-missing)
      rm -- "$claim"
      ;;
    claim-malformed)
      printf 'not-a-field\n' >>"$claim"
      ;;
    claim-duplicate-field)
      printf 'package=sequoia-sq-pqc\n' >>"$claim"
      ;;
    claim-wrong-type)
      rm -- "$claim"
      mkdir "$claim"
      ;;
    claim-package-mismatch)
      sed -i 's/^package=.*/package=sequoia-sqv-pqc/' "$claim"
      ;;
    claim-attempt-mismatch)
      sed -i 's/^attempt=.*/attempt=999/' "$claim"
      ;;
    claim-lifecycle-mismatch)
      sed -i 's/^lifecycle_admission_sha256=.*/lifecycle_admission_sha256=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff/' "$claim"
      ;;
    claim-digest-mismatch)
      sed -i 's/^initialization_claim_sha256=.*/initialization_claim_sha256=0000000000000000000000000000000000000000000000000000000000000000/' "$launcher"
      ;;
    launcher-package-mismatch)
      sed -i 's/^package=.*/package=sequoia-sqv-pqc/' "$launcher"
      ;;
    launcher-attempt-mismatch)
      sed -i 's/^attempt=.*/attempt=999/' "$launcher"
      ;;
    launcher-schema-missing)
      sed -i '/^schema=/d' "$launcher"
      ;;
    launcher-schema-obsolete)
      sed -i 's/^schema=.*/schema=arch-pq-outer-launcher-v2/' "$launcher"
      ;;
    launcher-duplicate-field)
      printf 'package=sequoia-sq-pqc\n' >>"$launcher"
      ;;
    *) return 2 ;;
  esac
}

invoke_cleanup() {
  local run=$1
  /usr/bin/bash "$run/procedure/final-cleanup.sh" \
    sequoia-sq-pqc=001 sequoia-sqv-pqc=001
}

invoke_assembly() {
  local run=$1
  (cd "$run" && /usr/bin/bash procedure/assemble-evidence.sh \
    sequoia-sq-pqc=001 sequoia-sqv-pqc=001)
}

verify_run=$(make_run verify-cases)
save_attempt "$verify_run"
verify_lifecycle_sha=$(sha256sum "$verify_run/control/lifecycle-admission.txt" | cut -d' ' -f1)

cleanup_run=$(make_run cleanup-cases)
save_attempt "$cleanup_run"

assembly_run=$(make_run assembly-cases)
invoke_cleanup "$assembly_run" >/dev/null
save_attempt "$assembly_run"

for mutation in \
  claim-missing \
  claim-malformed \
  claim-duplicate-field \
  claim-wrong-type \
  claim-package-mismatch \
  claim-attempt-mismatch \
  claim-lifecycle-mismatch \
  claim-digest-mismatch \
  launcher-package-mismatch \
  launcher-attempt-mismatch \
  launcher-schema-missing \
  launcher-schema-obsolete \
  launcher-duplicate-field
do
  restore_attempt "$verify_run"
  mutate_attempt "$verify_run" "$mutation"
  if /usr/bin/bash "$verify_run/procedure/initialize-attempt.sh" verify \
    "$verify_run/attempts/sequoia-sq-pqc-attempt-001" "$verify_lifecycle_sha" \
    >/dev/null 2>&1; then
    printf 'initialize verification accepted mutation: %s\n' "$mutation" >&2
    exit 1
  fi

  restore_attempt "$cleanup_run"
  rm -f -- "$cleanup_run/output/receipts/final-public-cache-cleanup.txt"
  mutate_attempt "$cleanup_run" "$mutation"
  if invoke_cleanup "$cleanup_run" >/dev/null 2>&1; then
    printf 'final cleanup accepted mutation: %s\n' "$mutation" >&2
    exit 1
  fi
  [[ -f $cleanup_run/attempts/sequoia-sq-pqc-attempt-001/work/cargo/cache ]]
  [[ -f $cleanup_run/attempts/sequoia-sq-pqc-attempt-001/work/srcdest/source ]]

  restore_attempt "$assembly_run"
  mutate_attempt "$assembly_run" "$mutation"
  if invoke_assembly "$assembly_run" >/dev/null 2>&1; then
    printf 'final assembly accepted mutation: %s\n' "$mutation" >&2
    exit 1
  fi
  [[ ! -e $assembly_run/review/final-source-and-evidence.inventory.tsv ]]
done

restore_attempt "$verify_run"
/usr/bin/bash "$verify_run/procedure/initialize-attempt.sh" verify \
  "$verify_run/attempts/sequoia-sq-pqc-attempt-001" "$verify_lifecycle_sha"

restore_attempt "$cleanup_run"
rm -f -- "$cleanup_run/output/receipts/final-public-cache-cleanup.txt"
invoke_cleanup "$cleanup_run" >/dev/null
[[ -z $(find "$cleanup_run/attempts/sequoia-sq-pqc-attempt-001/work/cargo" -mindepth 1 -print -quit) ]]

restore_attempt "$assembly_run"
invoke_assembly "$assembly_run" >/dev/null
grep -Fxq 'status=procedure-complete-successor-candidates-built-but-not-independently-accepted' \
  "$assembly_run/review/validation-status.txt"

printf 'canonical attempt validation rejects identity and claim substitution at every consumer: PASS\n'
