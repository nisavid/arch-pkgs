#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d)
cleanup() {
  chmod -R u+rwX "$scratch" 2>/dev/null || true
  find "$scratch" -depth -delete
}
trap cleanup EXIT

make_run() {
  local run="$scratch/$1" tool_hash
  mkdir -p "$run/procedure" "$run/inputs/rustup/empty-dir"
  cp "$source_root/procedure/verify-toolchain.sh" \
    "$source_root/procedure/verify-toolchain-links.sh" "$run/procedure/"
  printf 'tool\n' >"$run/inputs/rustup/tool"
  chmod 755 "$run/inputs/rustup/empty-dir"
  chmod 444 "$run/inputs/rustup/tool"
  printf '%s\n' "$run"
}

write_inventory() {
  local run=$1 tool_hash
  (
    cd "$run"
    sha256sum inputs/rustup/tool >inputs/rust-toolchain.sha256
    tool_hash=$(sha256sum inputs/rustup/tool | cut -d' ' -f1)
    {
      printf 'type\tmode\tbytes\tsha256_or_target\tpath\n'
      printf 'directory\t755\t0\t-\tinputs/rustup/empty-dir\n'
      printf 'file\t444\t5\t%s\tinputs/rustup/tool\n' "$tool_hash"
      while IFS= read -r -d '' path; do
        printf 'symlink\t777\t0\t%s\t%s\n' "$(readlink "$path")" "$path"
      done < <(find inputs/rustup -type l -print0 | LC_ALL=C sort -z)
    } >inputs/rust-toolchain.inventory.tsv
  )
}

expect_rejected() {
  local link_case=$1 run outside log
  run=$(make_run "$link_case")
  outside="$run/inputs/outside-tool"
  printf 'outside\n' >"$outside"
  case $link_case in
    relative-escape)
      ln -s ../outside-tool "$run/inputs/rustup/tool-link"
      ;;
    absolute-escape)
      ln -s "$outside" "$run/inputs/rustup/tool-link"
      ;;
    chained-escape)
      ln -s chain-link "$run/inputs/rustup/tool-link"
      ln -s ../outside-tool "$run/inputs/rustup/chain-link"
      ;;
    broken)
      ln -s missing "$run/inputs/rustup/tool-link"
      ;;
    cyclic)
      ln -s cycle-link "$run/inputs/rustup/tool-link"
      ln -s tool-link "$run/inputs/rustup/cycle-link"
      ;;
  esac
  write_inventory "$run"
  log="$scratch/$link_case.log"
  if /usr/bin/bash "$run/procedure/verify-toolchain.sh" >"$log" 2>&1; then
    printf '%s unexpectedly passed toolchain verification\n' "$link_case" >&2
    exit 1
  fi
  grep -Fq 'toolchain symlink' "$log"
}

valid=$(make_run valid)
ln -s tool "$valid/inputs/rustup/tool-link"
write_inventory "$valid"
/usr/bin/bash "$valid/procedure/verify-toolchain.sh" >/dev/null

for link_case in relative-escape absolute-escape chained-escape broken cyclic; do
  expect_rejected "$link_case"
done

grep -Fq '/usr/bin/bash procedure/verify-toolchain-links.sh' \
  "$source_root/procedure/setup-common.sh"
grep -Fq '/usr/bin/bash procedure/verify-toolchain-links.sh' \
  "$source_root/procedure/verify-toolchain.sh"
printf 'toolchain symlink confinement: PASS\n'
