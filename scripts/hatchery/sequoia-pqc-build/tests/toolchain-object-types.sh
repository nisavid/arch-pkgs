#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
scratch=$(mktemp -d "${TMPDIR:-/tmp}/hatchery-toolchain-objects.XXXXXX")
cleanup() {
  chmod -R u+w "$scratch" 2>/dev/null || true
  find "$scratch" -depth -delete
}
trap cleanup EXIT

make_run() {
  local run="$scratch/$1" tool_hash
  mkdir -p "$run/procedure" "$run/inputs/rustup/empty-dir"
  cp -a "$source_root/procedure/." "$run/procedure/"
  printf 'tool\n' >"$run/inputs/rustup/tool"
  ln -s tool "$run/inputs/rustup/tool-link"
  chmod 755 "$run/inputs/rustup/empty-dir"
  chmod 444 "$run/inputs/rustup/tool"
  (
    cd "$run"
    sha256sum inputs/rustup/tool >inputs/rust-toolchain.sha256
    tool_hash=$(sha256sum inputs/rustup/tool | cut -d' ' -f1)
    {
      printf 'type\tmode\tbytes\tsha256_or_target\tpath\n'
      printf 'directory\t755\t0\t-\tinputs/rustup/empty-dir\n'
      printf 'file\t444\t5\t%s\tinputs/rustup/tool\n' "$tool_hash"
      printf 'symlink\t777\t0\ttool\tinputs/rustup/tool-link\n'
    } >inputs/rust-toolchain.inventory.tsv
  )
  printf '%s\n' "$run"
}

write_toolchain_inventory() {
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

expect_rejected_link_case() {
  local link_case=$1 run outside log
  run=$(make_run "verify-link-$link_case")
  outside="$run/inputs/outside-tool"
  printf 'outside\n' >"$outside"
  rm "$run/inputs/rustup/tool-link"
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
    *)
      printf 'unsupported link test case: %s\n' "$link_case" >&2
      exit 2
      ;;
  esac
  write_toolchain_inventory "$run"
  log="$scratch/verify-link-$link_case.log"
  if /usr/bin/bash "$run/procedure/verify-toolchain.sh" >"$log" 2>&1; then
    printf '%s unexpectedly passed toolchain verification\n' "$link_case" >&2
    exit 1
  fi
  grep -Fq 'toolchain symlink' "$log"
}

expect_rejected_type() {
  local object_type=$1 run object_path log
  run=$(make_run "verify-$object_type")
  object_path="$run/inputs/rustup/empty-dir"
  rmdir "$object_path"
  case $object_type in
    fifo)
      mkfifo -m 755 "$object_path"
      ;;
    socket)
      python3 - "$object_path" <<'PY'
import socket
import sys
import os
from pathlib import Path

path = Path(sys.argv[1])
os.chdir(path.parent)
sock = socket.socket(socket.AF_UNIX)
sock.bind(path.name)
sock.close()
PY
      chmod 755 "$object_path"
      ;;
    *)
      printf 'unsupported test object type: %s\n' "$object_type" >&2
      exit 2
      ;;
  esac
  log="$scratch/verify-$object_type.log"
  if /usr/bin/bash "$run/procedure/verify-toolchain.sh" >"$log" 2>&1; then
    printf '%s unexpectedly passed toolchain verification\n' "$object_type" >&2
    exit 1
  fi
  grep -Fq "unsupported toolchain object type: inputs/rustup/empty-dir" "$log"
}

expect_rejected_additional_type() {
  local object_type=$1 run object_path log
  run=$(make_run "verify-additional-$object_type")
  object_path="$run/inputs/rustup/zz-special"
  case $object_type in
    fifo)
      mkfifo -m 755 "$object_path"
      ;;
    socket)
      python3 - "$object_path" <<'PY'
import socket
import sys
import os
from pathlib import Path

path = Path(sys.argv[1])
os.chdir(path.parent)
sock = socket.socket(socket.AF_UNIX)
sock.bind(path.name)
sock.close()
PY
      chmod 755 "$object_path"
      ;;
  esac
  log="$scratch/verify-additional-$object_type.log"
  if /usr/bin/bash "$run/procedure/verify-toolchain.sh" >"$log" 2>&1; then
    printf 'additional %s unexpectedly passed toolchain verification\n' \
      "$object_type" >&2
    exit 1
  fi
  grep -Fq "unsupported toolchain object type: inputs/rustup/zz-special" "$log"
}

prepare_fake_bin() {
  local command_name
  fake_bin="$scratch/fake-bin"
  mkdir "$fake_bin"
  for command_name in bash chmod cut date dirname env find grep ln mkdir mkfifo \
    python3 readlink realpath sha256sum sort stat xargs; do
    ln -s "/host/usr/bin/$command_name" "$fake_bin/$command_name"
  done
  cp "$source_root/tests/fixtures/setup-rustup.sh" "$fake_bin/rustup"
  cp "$source_root/tests/fixtures/setup-curl.sh" "$fake_bin/curl"
  cp "$source_root/tests/fixtures/setup-gpg.sh" "$fake_bin/gpg"
  cp "$source_root/tests/fixtures/setup-rustc.sh" "$fake_bin/rustc"
  cp "$source_root/tests/fixtures/setup-cargo.sh" "$fake_bin/cargo"
  chmod 755 "$fake_bin/rustup" "$fake_bin/curl" "$fake_bin/gpg" \
    "$fake_bin/rustc" "$fake_bin/cargo"
}

run_setup_case() {
  local object_type=$1 expected=$2 run="$scratch/setup-$1" log status
  mkdir -p "$run/procedure"
  cp "$source_root/procedure/setup-common.sh" "$run/procedure/"
  if [[ -f $source_root/procedure/verify-toolchain-links.sh ]]; then
    cp "$source_root/procedure/verify-toolchain-links.sh" "$run/procedure/"
  fi
  printf '#!/usr/bin/bash\nexit 0\n' >"$run/procedure/verify-toolchain.sh"
  printf '%s\n' "$object_type" >"$run/object-kind"
  log="$scratch/setup-$object_type.log"
  set +e
  /usr/bin/bwrap --unshare-all --die-with-parent --clearenv --dev /dev --proc /proc \
    --ro-bind /usr /host/usr --dir /usr \
    --ro-bind /usr/lib /usr/lib --ro-bind /usr/share /usr/share \
    --ro-bind "$fake_bin" /usr/bin --symlink usr/bin /bin \
    --symlink usr/lib /lib --symlink usr/lib /lib64 \
    --bind "$run" /run-tree \
    --chdir /run-tree --setenv PATH /usr/bin:/bin \
    /usr/bin/bash /run-tree/procedure/setup-common.sh >"$log" 2>&1
  status=$?
  set -e
  if [[ $expected == pass ]]; then
    (( status == 0 )) || {
      cat "$log" >&2
      printf 'valid synthetic setup failed with exit %s\n' "$status" >&2
      exit 1
    }
    grep -Fq $'directory\t555\t0\t-\tinputs/rustup/empty-dir' \
      "$run/inputs/rust-toolchain.inventory.tsv"
    grep -Fq $'file\t444\t5\t' "$run/inputs/rust-toolchain.inventory.tsv"
    grep -Fq $'symlink\t777\t0\ttool\tinputs/rustup/tool-link' \
      "$run/inputs/rust-toolchain.inventory.tsv"
    grep -Fq 'setup_exit=0' "$run/setup-evidence/common-setup.txt"
  else
    (( status != 0 )) || {
      printf '%s unexpectedly passed setup inventory generation\n' "$object_type" >&2
      exit 1
    }
    if [[ $object_type == fifo || $object_type == socket ]]; then
      grep -Fq "unsupported toolchain object type: inputs/rustup/special" "$log"
    else
      grep -Fq 'toolchain symlink' "$log"
    fi
    if grep -Fq 'setup_exit=0' "$run/setup-evidence/common-setup.txt"; then
      printf '%s rejection recorded setup success\n' "$object_type" >&2
      exit 1
    fi
  fi
}

valid=$(make_run verify-valid)
/usr/bin/bash "$valid/procedure/verify-toolchain.sh" >/dev/null
expect_rejected_type fifo
expect_rejected_additional_type fifo
for link_case in relative-escape absolute-escape chained-escape broken cyclic; do
  expect_rejected_link_case "$link_case"
done
expect_rejected_type socket
expect_rejected_additional_type socket
prepare_fake_bin
run_setup_case valid pass
run_setup_case fifo reject
run_setup_case socket reject
for link_case in relative-escape absolute-escape chained-escape broken cyclic; do
  run_setup_case "$link_case" reject
done

printf 'toolchain object type controls: PASS\n'
