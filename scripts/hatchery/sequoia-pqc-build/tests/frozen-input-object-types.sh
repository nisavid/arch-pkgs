#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d /tmp/hatchery-frozen-input-shape.XXXXXX)
cleanup() {
  find "$scratch" -depth -delete
}
trap cleanup EXIT

make_run() {
  local run="$scratch/$1"
  mkdir -p "$run/procedure" "$run/recipes/inert" "$run/tests" \
    "$run/inputs/rustup/empty-dir" "$run/inputs/gnupg-public/private-keys-v1.d" \
    "$run/inputs/public-keys"
  cp "$source_root/procedure/freeze-boundary.sh" \
    "$source_root/procedure/verify-frozen-boundary.sh" "$run/procedure/"
  printf 'recipe\n' >"$run/recipes/inert/README"
  printf 'test\n' >"$run/tests/marker"
  printf 'toolchain\n' >"$run/inputs/rustup/tool"
  ln -s tool "$run/inputs/rustup/tool-link"
  printf 'keyring\n' >"$run/inputs/gnupg-public/pubring.kbx"
  printf 'public key\n' >"$run/inputs/public-keys/key.asc"
  (cd "$run" && sha256sum inputs/rustup/tool >inputs/rust-toolchain.sha256)
  printf '%s\n' "$run"
}

add_special_object() {
  local object_type=$1 object_path=$2
  case $object_type in
    fifo)
      mkfifo "$object_path"
      ;;
    socket)
      /usr/bin/python3 - "$object_path" <<'PY'
import socket
import sys

sock = socket.socket(socket.AF_UNIX)
sock.bind(sys.argv[1])
sock.close()
PY
      ;;
    symlink)
      ln -s /work/work/srcdest/attacker-gpg.conf "$object_path"
      ;;
    *)
      printf 'unsupported test object type: %s\n' "$object_type" >&2
      exit 2
      ;;
  esac
}

expect_freeze_rejection() {
  local object_type=$1 run object_path log
  run=$(make_run "freeze-$object_type")
  object_path="$run/inputs/gnupg-public/zz-special"
  add_special_object "$object_type" "$object_path"
  log="$scratch/freeze-$object_type.log"
  if /usr/bin/bash "$run/procedure/freeze-boundary.sh" >"$log" 2>&1; then
    printf 'pre-freeze %s unexpectedly passed frozen-input admission\n' "$object_type" >&2
    exit 1
  fi
}

expect_replay_rejection() {
  local object_type=$1 run object_path log
  run=$(make_run "replay-$object_type")
  /usr/bin/bash "$run/procedure/freeze-boundary.sh" >/dev/null
  object_path="$run/inputs/gnupg-public/zz-special"
  add_special_object "$object_type" "$object_path"
  log="$scratch/replay-$object_type.log"
  if /usr/bin/bash "$run/procedure/verify-frozen-boundary.sh" >"$log" 2>&1; then
    printf 'appended %s unexpectedly passed frozen-input replay\n' "$object_type" >&2
    exit 1
  fi
}

valid=$(make_run valid)
/usr/bin/bash "$valid/procedure/freeze-boundary.sh" >/dev/null
/usr/bin/bash "$valid/procedure/verify-frozen-boundary.sh" >/dev/null

for object_type in fifo socket symlink; do
  expect_freeze_rejection "$object_type"
  expect_replay_rejection "$object_type"
done

input_root_alias=$(make_run non-toolchain-root-symlink)
mv "$input_root_alias/inputs/public-keys" "$scratch/external-public-keys"
ln -s "$scratch/external-public-keys" "$input_root_alias/inputs/public-keys"
if /usr/bin/bash "$input_root_alias/procedure/freeze-boundary.sh" >/dev/null 2>&1; then
  printf 'symlinked non-toolchain input root unexpectedly passed frozen-input admission\n' >&2
  exit 1
fi

rustup_alias=$(make_run rustup-root-symlink)
rm -r "$rustup_alias/inputs/rustup"
mkdir "$scratch/external-rustup"
printf 'external toolchain\n' >"$scratch/external-rustup/tool"
ln -s "$scratch/external-rustup" "$rustup_alias/inputs/rustup"
if /usr/bin/bash "$rustup_alias/procedure/freeze-boundary.sh" >/dev/null 2>&1; then
  printf 'symlinked Rustup root unexpectedly passed frozen-input admission\n' >&2
  exit 1
fi

printf 'frozen non-toolchain input object-shape replay: PASS\n'
