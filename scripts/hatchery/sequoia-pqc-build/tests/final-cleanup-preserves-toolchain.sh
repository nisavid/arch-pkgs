#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT
mkdir -p "$scratch/procedure" "$scratch/recipes" "$scratch/tests" "$scratch/inputs/rustup" \
  "$scratch/setup-scratch/home" "$scratch/setup-scratch/cargo" \
  "$scratch/attempts/pkg-attempt-001/work/cargo" "$scratch/attempts/pkg-attempt-001/work/srcdest" \
  "$scratch/attempts/pkg-attempt-001/receipts" "$scratch/attempts/pkg-attempt-002/work/cargo"
cp "$source_root/procedure/final-cleanup.sh" "$scratch/procedure/"
cp "$source_root/procedure/verify-toolchain.sh" "$scratch/procedure/"
cp "$source_root/procedure/verify-toolchain-links.sh" "$scratch/procedure/"
cp "$source_root/procedure/freeze-boundary.sh" "$scratch/procedure/"
cp "$source_root/procedure/verify-frozen-boundary.sh" "$scratch/procedure/"
printf 'replayable toolchain bytes\n' >"$scratch/inputs/rustup/tool"
ln -s tool "$scratch/inputs/rustup/tool-link"
printf 'discard\n' >"$scratch/setup-scratch/home/state"
printf 'discard\n' >"$scratch/setup-scratch/cargo/cache"
printf 'discard\n' >"$scratch/attempts/pkg-attempt-001/work/cargo/cache"
printf 'discard\n' >"$scratch/attempts/pkg-attempt-001/work/srcdest/source"
touch "$scratch/attempts/pkg-attempt-001/receipts/ACCEPTED"
printf 'preserve failed attempt\n' >"$scratch/attempts/pkg-attempt-002/work/cargo/cache"
(
  cd "$scratch"
  sha256sum inputs/rustup/tool >inputs/rust-toolchain.sha256
  printf 'type\tmode\tbytes\tsha256_or_target\tpath\n' >inputs/rust-toolchain.inventory.tsv
  printf 'file\t%s\t%s\t%s\tinputs/rustup/tool\n' "$(stat -c %a inputs/rustup/tool)" \
    "$(stat -c %s inputs/rustup/tool)" "$(sha256sum inputs/rustup/tool | cut -d' ' -f1)" \
    >>inputs/rust-toolchain.inventory.tsv
  printf 'symlink\t%s\t0\ttool\tinputs/rustup/tool-link\n' "$(stat -c %a inputs/rustup/tool-link)" \
    >>inputs/rust-toolchain.inventory.tsv
)
/usr/bin/bash "$scratch/procedure/freeze-boundary.sh" >/dev/null
/usr/bin/bash "$scratch/procedure/final-cleanup.sh"
(
  cd "$scratch"
  sha256sum -c inputs/rust-toolchain.sha256 >/dev/null
)
[[ -f $scratch/inputs/rustup/tool ]]
[[ $(readlink "$scratch/inputs/rustup/tool-link") == tool ]]
for path in setup-scratch/home setup-scratch/cargo \
  attempts/pkg-attempt-001/work/cargo attempts/pkg-attempt-001/work/srcdest; do
  [[ -z $(find "$scratch/$path" -mindepth 1 -print -quit) ]]
done
[[ -f $scratch/attempts/pkg-attempt-002/work/cargo/cache ]]
ln -sfn wrong-target "$scratch/inputs/rustup/tool-link"
if /usr/bin/bash "$scratch/procedure/verify-toolchain.sh" >/dev/null 2>&1; then exit 1; fi
printf 'final cleanup preserves replayable toolchain: PASS\n'
