#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
toolchain_root="$root/inputs/rustup"
[[ -d $toolchain_root && ! -L $toolchain_root ]] || {
  printf 'toolchain root is not an actual directory: %s\n' "$toolchain_root" >&2
  exit 1
}
canonical_root=$(realpath -e -- "$toolchain_root")
[[ $canonical_root == "$toolchain_root" ]] || {
  printf 'toolchain root is not canonical: %s\n' "$toolchain_root" >&2
  exit 1
}

while IFS= read -r -d '' path; do
  target=$(readlink -- "$path") || {
    printf 'toolchain symlink target cannot be read: %s\n' "$path" >&2
    exit 1
  }
  [[ $target != /* ]] || {
    printf 'toolchain symlink has an absolute target: %s -> %s\n' "$path" "$target" >&2
    exit 1
  }
  lexical_target=$(realpath -m -s -- "$(dirname "$path")/$target")
  [[ $lexical_target == "$canonical_root"/* ]] || {
    printf 'toolchain symlink escapes the toolchain root: %s -> %s\n' "$path" "$target" >&2
    exit 1
  }
  if ! resolved_target=$(realpath -e -- "$path"); then
    printf 'toolchain symlink is broken or cyclic: %s -> %s\n' "$path" "$target" >&2
    exit 1
  fi
  [[ $resolved_target == "$canonical_root"/* ]] || {
    printf 'toolchain symlink resolves outside the toolchain root: %s -> %s\n' \
      "$path" "$resolved_target" >&2
    exit 1
  }
  [[ -f $resolved_target || -d $resolved_target ]] || {
    printf 'toolchain symlink does not terminate in a file or directory: %s -> %s\n' \
      "$path" "$resolved_target" >&2
    exit 1
  }
done < <(find "$toolchain_root" -mindepth 1 -type l -print0 | LC_ALL=C sort -z)
