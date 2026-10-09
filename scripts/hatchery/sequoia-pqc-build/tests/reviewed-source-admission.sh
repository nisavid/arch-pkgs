#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT

make_run() {
  local run="$scratch/$1"
  mkdir -p "$run"
  cp -a "$source_root/procedure" "$run/procedure"
  cp -a "$source_root/recipes" "$run/recipes"
  cp -a "$source_root/tests" "$run/tests"
  /usr/bin/bash "$run/tests/fixtures/create-reviewed-source-admission.sh" "$run" \
    741b9c59331ea65f610a4586857e27c3bf1d06ed
  printf '%s\n' "$run"
}

tampered=$(make_run tampered)
printf 'unreviewed change\n' >>"$tampered/procedure/PROCEDURE.md"
if /usr/bin/bash "$tampered/procedure/verify-reviewed-source.sh" >/dev/null 2>&1; then
  printf 'changed maintained source passed reviewed-source admission\n' >&2
  exit 1
fi
set +e
/usr/bin/bash "$tampered/procedure/invoke-attempt.sh" sequoia-sq-pqc 001 \
  >"$scratch/tampered-attempt.log" 2>&1
status=$?
set -e
(( status != 0 ))
[[ ! -e $tampered/attempts ]]

exact=$(make_run exact)
/usr/bin/bash "$exact/procedure/verify-reviewed-source.sh" >/dev/null
mkdir -p "$exact/inputs/rustup" "$exact/review"
printf 'toolchain\n' >"$exact/inputs/rustup/tool"
(
  cd "$exact"
  sha256sum inputs/rustup/tool >inputs/rust-toolchain.sha256
  printf 'type\tmode\tbytes\tsha256_or_target\tpath\n' >inputs/rust-toolchain.inventory.tsv
  printf 'file\t%s\t%s\t%s\tinputs/rustup/tool\n' \
    "$(stat -c %a inputs/rustup/tool)" "$(stat -c %s inputs/rustup/tool)" \
    "$(sha256sum inputs/rustup/tool | cut -d' ' -f1)" \
    >>inputs/rust-toolchain.inventory.tsv
)
/usr/bin/bash "$exact/procedure/freeze-boundary.sh" >/dev/null
printf 'status=inert-source-admission-proof\n' >"$exact/review/validation-status.txt"
inventory="$exact/review/final-source-and-evidence.inventory.tsv"
/usr/bin/bash "$exact/procedure/write-run-inventory.sh" "$exact" "$inventory"
revision_sha=$(sha256sum "$exact/review-admission/source-revision.txt" | cut -d' ' -f1)
manifest_sha=$(sha256sum "$exact/review-admission/maintained-source.inventory.tsv" | cut -d' ' -f1)
awk -F'\t' -v sha="$revision_sha" \
  '$3 == sha && $4 == "review-admission/source-revision.txt" { found=1 } END { exit !found }' \
  "$inventory"
awk -F'\t' -v sha="$manifest_sha" \
  '$3 == sha && $4 == "review-admission/maintained-source.inventory.tsv" { found=1 } END { exit !found }' \
  "$inventory"
printf 'reviewed source admission and retained provenance: PASS\n'
