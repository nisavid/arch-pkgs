#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'chmod -R u+rwX "$scratch" 2>/dev/null || true; find "$scratch" -depth -delete' EXIT
mkdir -p "$scratch/procedure" "$scratch/recipes" "$scratch/tests" \
  "$scratch/inputs/rustup/empty-dir" "$scratch/setup-scratch/home" "$scratch/setup-scratch/cargo"
cp "$source_root/procedure/final-cleanup.sh" \
  "$source_root/procedure/verify-toolchain.sh" \
  "$source_root/procedure/verify-toolchain-links.sh" \
  "$source_root/procedure/freeze-boundary.sh" \
  "$source_root/procedure/verify-frozen-boundary.sh" \
  "$source_root/procedure/verify-reviewed-source.sh" "$scratch/procedure/"
printf 'replayable toolchain bytes\n' >"$scratch/inputs/rustup/tool"
ln -s tool "$scratch/inputs/rustup/tool-link"
printf 'discard\n' >"$scratch/setup-scratch/home/state"
printf 'discard\n' >"$scratch/setup-scratch/cargo/cache"
(
  cd "$scratch"
  sha256sum inputs/rustup/tool >inputs/rust-toolchain.sha256
  {
    printf 'type\tmode\tbytes\tsha256_or_target\tpath\n'
    printf 'directory\t%s\t0\t-\tinputs/rustup/empty-dir\n' \
      "$(stat -c %a inputs/rustup/empty-dir)"
    printf 'file\t%s\t%s\t%s\tinputs/rustup/tool\n' "$(stat -c %a inputs/rustup/tool)" \
      "$(stat -c %s inputs/rustup/tool)" "$(sha256sum inputs/rustup/tool | cut -d' ' -f1)"
    printf 'symlink\t%s\t0\ttool\tinputs/rustup/tool-link\n' \
      "$(stat -c %a inputs/rustup/tool-link)"
  } >inputs/rust-toolchain.inventory.tsv
)
/usr/bin/bash "$source_root/tests/fixtures/create-reviewed-source-admission.sh" "$scratch"
/usr/bin/bash "$scratch/procedure/freeze-boundary.sh" >/dev/null

for package in sequoia-sq-pqc sequoia-sqv-pqc; do
  if [[ $package == sequoia-sq-pqc ]]; then version=1.4.0; else version=1.5.0; fi
  attempt="$scratch/attempts/${package}-attempt-001"
  archive="$scratch/output/archives/${package}-${version}-4-x86_64.pkg.tar.zst"
  mkdir -p "$attempt/receipts" "$attempt/work/cargo" "$attempt/work/srcdest" \
    "$scratch/output/archives"
  printf 'discard\n' >"$attempt/work/cargo/cache"
  printf 'discard\n' >"$attempt/work/srcdest/source"
  printf 'archive\n' >"$archive"
  touch "$attempt/receipts/ACCEPTED"
  printf 'accepted=false\nouter_exit=0\naccepted=true\n' >"$attempt/receipts/outer-launcher.txt"
  sha256sum "$archive" >"$attempt/receipts/output-archive.sha256"
done
mkdir -p "$scratch/attempts/failed/work/cargo"
printf 'preserve failed attempt\n' >"$scratch/attempts/failed/work/cargo/cache"

/usr/bin/bash "$scratch/procedure/final-cleanup.sh" \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001
(
  cd "$scratch"
  sha256sum -c inputs/rust-toolchain.sha256 >/dev/null
)
[[ -f $scratch/inputs/rustup/tool ]]
[[ $(readlink "$scratch/inputs/rustup/tool-link") == tool ]]
for path in setup-scratch/home setup-scratch/cargo \
  attempts/sequoia-sq-pqc-attempt-001/work/cargo \
  attempts/sequoia-sq-pqc-attempt-001/work/srcdest \
  attempts/sequoia-sqv-pqc-attempt-001/work/cargo \
  attempts/sequoia-sqv-pqc-attempt-001/work/srcdest; do
  [[ -z $(find "$scratch/$path" -mindepth 1 -print -quit) ]]
done
[[ -f $scratch/attempts/failed/work/cargo/cache ]]
ln -sfn wrong-target "$scratch/inputs/rustup/tool-link"
if /usr/bin/bash "$scratch/procedure/verify-toolchain.sh" >/dev/null 2>&1; then exit 1; fi
printf 'final cleanup preserves replayable toolchain: PASS\n'
