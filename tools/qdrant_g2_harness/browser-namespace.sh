#!/usr/bin/bash
# Inner G2 browser run: executes inside the loopback-only Bubblewrap namespace
# that run-browser.zsh creates. /usr is the host /usr overlaid with the exact
# qdrant and qdrant-web-ui payloads; /etc/qdrant/config.yaml is the packaged
# configuration; /var/lib/qdrant is a fresh empty state root.
set -euo pipefail
export LC_ALL=C

readonly out=/g2-out/raw
readonly jwt_file=/tmp/browser.jwt
qdrant_pid=''

fail() { printf 'browser namespace: %s\n' "$1" >&2; exit 1; }

stop_qdrant() {
  if [[ -n $qdrant_pid ]] && kill -0 "$qdrant_pid" 2>/dev/null; then
    kill -TERM "$qdrant_pid"
    wait "$qdrant_pid" || true
  fi
  qdrant_pid=''
}
trap 'stop_qdrant; rm -f "$jwt_file"' EXIT

readlink /proc/self/ns/pid >"$out/pid-namespace"
readlink /proc/self/ns/net >"$out/net-namespace"

# Host-sensitive roots must be absent from this view.
{
  printf 'home_root_absent=%s\n' "$([[ ! -e /home ]] && echo true || echo false)"
  printf 'superuser_home_absent=%s\n' "$([[ ! -e /root ]] && echo true || echo false)"
  printf 'host_qdrant_config_entries=%s\n' "$(ls -A /etc/qdrant | tr '\n' ' ')"
  printf 'host_qdrant_state_initial_entries=%s\n' "$(find /var/lib/qdrant -mindepth 1 -not -type d | wc -l)"
  printf 'interfaces=%s\n' "$(ip -o link show | awk -F': ' '{print $2}' | tr '\n' ' ')"
  python3 - <<'PY'
import errno, socket
for family, address in ((socket.AF_INET, ("192.0.2.1", 80)), (socket.AF_INET6, ("2001:db8::1", 80))):
    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect(address)
        print(f"egress_{family.name}=connected")
    except OSError as error:
        print(f"egress_{family.name}={errno.errorcode.get(error.errno, error.errno)}")
    finally:
        s.close()
PY
} >"$out/isolation.txt"

grep -qx 'home_root_absent=true' "$out/isolation.txt" || fail '/home is visible'
grep -qx 'superuser_home_absent=true' "$out/isolation.txt" || fail '/root is visible'
grep -qx 'host_qdrant_config_entries=config.yaml ' "$out/isolation.txt" || fail 'unexpected /etc/qdrant entries'
grep -qx 'interfaces=lo ' "$out/isolation.txt" || fail 'a non-loopback interface is present'
if grep -q '=connected$' "$out/isolation.txt"; then fail 'non-loopback egress connected'; fi

sha256sum /usr/bin/qdrant /etc/qdrant/config.yaml /usr/share/qdrant/qdrant.spdx.json \
  /usr/share/qdrant/web-ui/cloud/data.json >"$out/payload-inputs.sha256"
(cd / && find usr/share/qdrant/web-ui -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) \
  >"$out/web-ui-tree.txt"

cd /var/lib/qdrant
(
  set -a
  # shellcheck disable=SC1091
  . /g2-private/secret.env
  set +a
  exec /usr/bin/qdrant --config-path /etc/qdrant/config.yaml
) >"$out/qdrant.log" 2>&1 &
qdrant_pid=$!

python3 /g2/browser_seed.py /g2-private/secret.env "$jwt_file" "$out/seed.json"
ss -H -ltnu >"$out/listeners-running.txt"
python3 /g2/browser_acceptance.py "$jwt_file" "$out/browser-acceptance.json"
rm -f "$jwt_file"
stop_qdrant
ss -H -ltnu >"$out/listeners-after-stop.txt"
printf 'qdrant_stopped=true\ncredential_files_removed=%s\n' \
  "$([[ ! -e $jwt_file ]] && echo true || echo false)" >"$out/cleanup-inside.txt"
