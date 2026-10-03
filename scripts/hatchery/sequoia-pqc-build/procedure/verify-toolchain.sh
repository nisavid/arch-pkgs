#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$root"
/usr/bin/bash procedure/verify-toolchain-links.sh
sha256sum -c inputs/rust-toolchain.sha256
inventory() {
  printf 'type\tmode\tbytes\tsha256_or_target\tpath\n'
  while IFS= read -r -d '' path; do
    if [[ -L $path ]]; then
      printf 'symlink\t%s\t0\t%s\t%s\n' "$(stat -c %a "$path")" "$(readlink "$path")" "$path"
    elif [[ -f $path ]]; then
      printf 'file\t%s\t%s\t%s\t%s\n' "$(stat -c %a "$path")" "$(stat -c %s "$path")" \
        "$(sha256sum "$path" | cut -d' ' -f1)" "$path"
    elif [[ -d $path && ! -L $path ]]; then
      printf 'directory\t%s\t0\t-\t%s\n' "$(stat -c %a "$path")" "$path"
    else
      printf 'unsupported toolchain object type: %s\n' "$path" >&2
      return 1
    fi
  done < <(find inputs/rustup -mindepth 1 -print0 | LC_ALL=C sort -z)
}
inventory | diff -u inputs/rust-toolchain.inventory.tsv -
