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
  *)
    printf 'unsupported synthetic setup case: %s\n' "$kind" >&2
    exit 2
    ;;
esac
