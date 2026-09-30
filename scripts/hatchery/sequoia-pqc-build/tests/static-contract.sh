#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
root=${tests_dir%/*}
invoke="$root/procedure/invoke-attempt.sh"
body="$root/procedure/attempt-body.sh"
cleanup="$root/procedure/final-cleanup.sh"
setup="$root/procedure/setup-common.sh"
post_build="$root/procedure/post-build-verify.sh"
assemble="$root/procedure/assemble-evidence.sh"
freeze="$root/procedure/freeze-boundary.sh"
frozen_verify="$root/procedure/verify-frozen-boundary.sh"
reviewed_source_verify="$root/procedure/verify-reviewed-source.sh"
runtime_closure="$root/procedure/runtime-closure.sh"
lifecycle="$root/procedure/lifecycle-admission.sh"

assert_absent_fixed() {
  local pattern=$1 path=$2 grep_exit
  if grep -Fq -- "$pattern" "$path"; then
    printf 'forbidden source pattern found in %s: %s\n' "$path" "$pattern" >&2
    return 1
  else
    grep_exit=$?
    if (( grep_exit != 1 )); then
      printf 'grep failed while checking %s for: %s\n' "$path" "$pattern" >&2
      return "$grep_exit"
    fi
  fi
}

assert_absent_extended() {
  local pattern=$1 path=$2 grep_exit
  if grep -Eq -- "$pattern" "$path"; then
    printf 'forbidden source pattern found in %s: %s\n' "$path" "$pattern" >&2
    return 1
  else
    grep_exit=$?
    if (( grep_exit != 1 )); then
      printf 'grep failed while checking %s for: %s\n' "$path" "$pattern" >&2
      return "$grep_exit"
    fi
  fi
}

# shellcheck disable=SC2016 # Static assertions match literal source fragments.
assert_absent_fixed '--bind "$host_root" /work' "$invoke"
# shellcheck disable=SC2016 # Static assertions match literal source fragments.
grep -Fq -- '--ro-bind "$host_root/procedure" /work/procedure' "$invoke"
# shellcheck disable=SC2016 # Static assertions match literal source fragments.
grep -Fq -- '--ro-bind "$host_root/recipes/$package" /work/recipe' "$invoke"
# shellcheck disable=SC2016 # Static assertions match literal source fragments.
grep -Fq -- '--ro-bind "$host_root/inputs/rustup" /work/inputs/rustup' "$invoke"
assert_absent_extended 'receipts/|ACCEPTED|output/' "$body"
# shellcheck disable=SC1003 # The trailing backslash is the literal source pattern.
assert_absent_fixed 'inputs/rustup" \' "$cleanup"
grep -Fq 'CARGO_NET_OFFLINE=true' "$body"
grep -Fq 'capture-source-view.sh' "$invoke"
grep -Fq 'verify-source-tag.sh' "$post_build"
# shellcheck disable=SC2016 # Static assertions match literal source fragments.
assert_absent_fixed 'git -C "$work/srcdest/$repo" verify-tag' "$post_build"
grep -Fq 'final-public-cache-cleanup.sha256' "$assemble"
grep -Fq 'arch-pq-final-public-cache-cleanup-v3' "$assemble"
grep -Fq 'lifecycle-admission.sh" verify' "$invoke"
grep -Fq 'lifecycle-admission.sh" verify' "$assemble"
grep -Fq 'arch-pq-lifecycle-admission-v1' "$lifecycle"
grep -Fq 'lifecycle_admission_sha256' "$invoke"
grep -Fq 'lifecycle_admission_sha256' "$assemble"
# shellcheck disable=SC2016 # Static assertions match literal source fragments.
grep -Fq 'mkdir -p "$prov/lifecycle"' "$assemble"
grep -Fq 'procedure-complete-successor-candidates-built' "$assemble"
grep -Fq 'reviewed-source-admission.sha256' "$assemble"
grep -Fq 'deployment_gate=open' "$assemble"
grep -Fq 'procedure recipes tests inputs review-admission' "$freeze"
grep -Fq 'verify-reviewed-source.sh' "$invoke"
grep -Fq 'verify-reviewed-source.sh' "$setup"
grep -Fq 'maintained-source.inventory.tsv' "$reviewed_source_verify"
grep -Fq 'verify-frozen-boundary.sh' "$invoke"
grep -Fq 'canonical_path' "$frozen_verify"
grep -Fq '/controller/runtime-closure.sh' "$post_build"
# shellcheck disable=SC2016 # Static assertions match literal source fragments.
if grep -Fq 'sha256sum "$object"' "$post_build"; then exit 1; fi
grep -Fq '3>&-' "$runtime_closure"
grep -Fq 'pkgrel=4' "$root/recipes/sequoia-sq-pqc/PKGBUILD"
grep -Fq 'pkgrel=4' "$root/recipes/sequoia-sqv-pqc/PKGBUILD"
# shellcheck disable=SC2016 # Static assertions match literal source fragments.
grep -Fq 'local asset_home="$srcdir/asset-home"' "$root/recipes/sequoia-sq-pqc/PKGBUILD"
grep -Fq 'historical 1.4.0-3' "$root/recipes/sequoia-sq-pqc/README.md"
grep -Fq 'historical 1.5.0-3' "$root/recipes/sequoia-sqv-pqc/README.md"
printf 'static procedure contract: PASS\n'
