#!/usr/bin/bash
set -Eeuo pipefail

kind=$(< /run-tree/object-kind)
printf 'tool\n' >"$RUSTUP_HOME/tool"
case $kind in
  valid)
    mkdir "$RUSTUP_HOME/empty-dir"
    ln -s tool "$RUSTUP_HOME/tool-link"
    ;;
  fifo)
    mkfifo "$RUSTUP_HOME/special"
    ;;
  socket)
    python3 - "$RUSTUP_HOME/special" <<'PY'
import socket
import sys

sock = socket.socket(socket.AF_UNIX)
sock.bind(sys.argv[1])
sock.close()
PY
    ;;
  relative-escape)
    printf 'outside\n' >"$RUSTUP_HOME/../outside-tool"
    ln -s ../outside-tool "$RUSTUP_HOME/tool-link"
    ;;
  absolute-escape)
    printf 'outside\n' >/run-tree/setup-scratch/absolute-tool
    ln -s /run-tree/setup-scratch/absolute-tool "$RUSTUP_HOME/tool-link"
    ;;
  chained-escape)
    printf 'outside\n' >"$RUSTUP_HOME/../outside-tool"
    ln -s chain-link "$RUSTUP_HOME/tool-link"
    ln -s ../outside-tool "$RUSTUP_HOME/chain-link"
    ;;
  broken)
    ln -s missing "$RUSTUP_HOME/tool-link"
    ;;
  cyclic)
    ln -s cycle-link "$RUSTUP_HOME/tool-link"
    ln -s tool-link "$RUSTUP_HOME/cycle-link"
    ;;
  *)
    printf 'unsupported synthetic setup case: %s\n' "$kind" >&2
    exit 2
    ;;
esac
