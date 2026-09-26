#!/usr/bin/env zsh
# G2 exact packaged-unit acceptance in a disposable rootless container.
#
# Installs the exact qdrant and qdrant-web-ui archives into a fresh container
# from the pinned Arch base image (network none, private cgroup namespace,
# container-local privileged mode so the unit's namespace and cgroup directives
# take effect, 4 GiB memory envelope, 2 GiB tmpfs state), exercises secret
# preflight rejection, runs the exact packaged unit, and captures listener,
# policy, hardening, cgroup, API, JWT, gRPC, CORS, dashboard, strict-mode,
# restart, and cleanup evidence. Nothing on the host is installed or started.
#
# Usage: run-unit.zsh <run-root> <qdrant-archive> <qdrant-sha256> <web-ui-archive> <web-ui-sha256>

emulate -R zsh
setopt ERR_RETURN NO_UNSET PIPE_FAIL

readonly HERE=${0:A:h}
readonly IMAGE_ID=0864f97b9567bf14c4450f820234617de489069d5157a3aef4a14a3e9bdf7508
readonly IMAGE_DIGEST=sha256:ee205c220399524a683cf495d411691b921baed8ab47cdc6d732efa782fae484
readonly MEMORY_BYTES=4294967296
readonly STATE_BYTES=2147483648

log() { print -r -- "[g2-unit $(date -u +%H:%M:%SZ)] $*" >&2 }
die() { log "FATAL: $*"; return 1 }

typeset -g RUN='' NAME='' CPID=''

cleanup() {
  emulate -L zsh
  setopt NO_UNSET
  if [[ -n $NAME ]] && podman container exists $NAME 2>/dev/null; then
    podman exec $NAME rm -f /etc/qdrant/qdrant.env 2>/dev/null || true
    podman stop -t 30 $NAME >/dev/null 2>&1 || true
    podman rm -f $NAME >/dev/null 2>&1 || true
  fi
  [[ -n $RUN && -e $RUN/private/secret.env ]] && rm -f -- $RUN/private/secret.env
  return 0
}
# zsh skips EXIT traps when ERR_EXIT fires, so failures return to the
# top level, which always cleans up.
trap 'cleanup; exit 143' TERM
trap 'cleanup; exit 130' INT

cx() { podman exec $NAME "$@" }

check_archive() {
  emulate -L zsh
  setopt ERR_RETURN NO_UNSET PIPE_FAIL
  local file=$1 want=$2 got
  [[ -f $file && ! -L $file ]] || die "not a regular file: $file"
  got=$(sha256sum -- $file | cut -d" " -f1)
  [[ $got == $want ]] || die "archive digest mismatch for ${file:t}: $got"
}

service_attempt() {
  # Ask systemd to start qdrant.service and expect refusal before the server
  # runs. Record the outcome, then stop the restart loop and clear the failure.
  emulate -L zsh
  setopt ERR_RETURN NO_UNSET PIPE_FAIL
  local label=$1 cursor result='' j
  cursor=$(cx journalctl -n 0 --show-cursor --no-pager | sed -n 's/^-- cursor: //p')
  cx systemctl start --no-block qdrant.service
  for j in {1..240}; do
    result=$(cx systemctl show -p Result --value qdrant.service) || true
    [[ -n $result && $result != success ]] && break
    sleep 0.25
  done
  {
    print -r -- "result=$result"
    cx systemctl show qdrant.service -p ActiveState -p ExecMainPID
    print -r -- "qdrant_processes=$(cx pgrep -c -x qdrant || true)"
    cx journalctl --after-cursor=$cursor -o cat --no-pager |
      grep -E 'secret preflight|Failed to load environment' || true
  } >$RUN/raw/secret-$label.txt 2>&1
  cx systemctl stop qdrant.service >/dev/null 2>&1 || true
  cx systemctl reset-failed qdrant.service >/dev/null 2>&1 || true
  [[ -n $result && $result != success ]] || die "service did not refuse the $label secret"
  grep -qx 'qdrant_processes=0' $RUN/raw/secret-$label.txt || die "qdrant ran with the $label secret"
}

main() {
  (( $# == 5 )) || die 'usage: run-unit.zsh <run-root> <qdrant-archive> <qdrant-sha256> <web-ui-archive> <web-ui-sha256>'
  RUN=$1
  local qpkg=${2:A} qsha=$3 wpkg=${4:A} wsha=$5
  [[ ! -e $RUN ]] || die "run root exists: $RUN"
  mkdir -p -- $RUN/{raw,private}
  chmod 700 $RUN/private
  check_archive $qpkg $qsha
  check_archive $wpkg $wsha
  [[ "$(podman image inspect --format '{{.Id}}' $IMAGE_ID)" == $IMAGE_ID ]] ||
    die 'pinned base image is not present'

  NAME=qdrant-g2-unit-$(date -u +%Y%m%dT%H%M%SZ)
  log "starting disposable container $NAME"
  podman run -d --name $NAME --pull=never --network=none --cgroupns=private \
    --systemd=always --privileged --cgroups=split \
    --memory=$MEMORY_BYTES --memory-swap=$MEMORY_BYTES \
    --tmpfs /var/lib/qdrant:rw,nosuid,nodev,noexec,size=$STATE_BYTES,mode=0755 \
    --volume $qpkg:/run/g2-inputs/${qpkg:t}:ro \
    --volume $wpkg:/run/g2-inputs/${wpkg:t}:ro \
    --volume $RUN/private:/run/g2-private:ro \
    $IMAGE_ID /usr/lib/systemd/systemd >$RUN/raw/container-id
  CPID=$(podman inspect --format '{{.State.Pid}}' $NAME)
  local state='' i
  for i in {1..120}; do
    state=$(cx systemctl is-system-running 2>/dev/null) || true
    [[ $state == (running|degraded) ]] && break
    sleep 0.5
  done
  [[ $state == (running|degraded) ]] || die "container systemd did not settle: $state"
  { print -r -- "system_state=$state"; cx systemctl --failed --no-legend --plain --no-pager } \
    >$RUN/raw/system-state.txt 2>&1 || true
  podman inspect $NAME >$RUN/raw/container-inspect.json
  podman info --format '{{.Host.Security.Rootless}} {{.Version.Version}}' >$RUN/raw/podman.txt
  {
    print -r -- "image_digest=$IMAGE_DIGEST"
    print -r -- "memory_max=$(cx cat /sys/fs/cgroup/memory.max)"
    print -r -- "state_fs=$(cx findmnt -no FSTYPE,SIZE,OPTIONS /var/lib/qdrant)"
    print -r -- "state_files=$(cx find /var/lib/qdrant -mindepth 1 | wc -l)"
    print -r -- "state_use=$(cx df --output=used,pcent -B1 /var/lib/qdrant | tail -n 1)"
    print -r -- "interfaces=$(cx ip -o link show | awk -F': ' '{print $2}' | tr '\n' ' ')"
  } >$RUN/raw/container-initial.txt

  log 'installing the exact archives with pacman -U'
  cx pacman -U --noconfirm /run/g2-inputs/${wpkg:t} /run/g2-inputs/${qpkg:t} \
    >$RUN/raw/pacman-install.txt 2>&1 || die 'pacman -U failed'
  cx pacman -Q qdrant qdrant-web-ui >$RUN/raw/pacman-query.txt
  cx pacman -Qkk qdrant qdrant-web-ui >$RUN/raw/pacman-integrity.txt 2>&1 || true
  cx pacman -Qi qdrant >$RUN/raw/pacman-info-qdrant.txt
  cx pacman -Qi qdrant-web-ui >$RUN/raw/pacman-info-web-ui.txt
  cx sh -c 'cd / && find usr/share/qdrant/web-ui -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum' \
    >$RUN/raw/web-ui-tree.txt
  cx sha256sum /usr/bin/qdrant /usr/share/qdrant/qdrant.spdx.json /etc/qdrant/config.yaml \
    /usr/lib/systemd/system/qdrant.service /usr/lib/qdrant/qdrant-secret-preflight \
    /usr/share/qdrant/web-ui/cloud/data.json >$RUN/raw/installed-sha256.txt
  cx stat -c '%n %s %a %U:%G' /usr/bin/qdrant /usr/share/qdrant/qdrant.spdx.json \
    >$RUN/raw/installed-stat.txt
  cx id qdrant >$RUN/raw/service-identity.txt

  # qdrant.service orders itself after network-online.target. Reach that
  # target first so each refusal below reflects the unit, not the wait.
  cx systemctl start network-online.target >$RUN/raw/network-online.txt 2>&1 || true
  cx systemctl show network-online.target -p ActiveState >>$RUN/raw/network-online.txt

  log 'secret preflight rejection cases'
  cx rm -f /etc/qdrant/qdrant.env
  service_attempt missing
  cx install -o root -g qdrant -m 0640 /dev/null /etc/qdrant/qdrant.env
  service_attempt empty
  cx sh -c 'printf "QDRANT__SERVICE__API_KEY=not-a-hex-secret\n" >/run/g2-malformed &&
    install -o root -g qdrant -m 0640 /run/g2-malformed /etc/qdrant/qdrant.env &&
    rm -f /run/g2-malformed'
  service_attempt malformed
  umask 077
  print -r -- "QDRANT__SERVICE__API_KEY=$(openssl rand -hex 32)" >$RUN/private/secret.env
  cx install -o root -g qdrant -m 0644 /run/g2-private/secret.env /etc/qdrant/qdrant.env
  service_attempt wrong-mode
  cx install -o root -g qdrant -m 0640 /run/g2-private/secret.env /etc/qdrant/qdrant.env
  cx stat -c '%u:%G:%a' /etc/qdrant/qdrant.env >$RUN/raw/secret-valid-metadata.txt

  log 'starting the exact packaged unit'
  cx mkdir -p /home/g2-probe /root/g2-probe
  cx touch /home/g2-probe/marker /root/g2-probe/marker
  cx systemctl start qdrant.service
  local j
  for i in {1..120}; do
    cx curl -fsS -o /dev/null http://127.0.0.1:6333/readyz 2>/dev/null && break
    sleep 0.5
  done
  cx curl -fsS -o /dev/null http://127.0.0.1:6333/readyz || die 'service did not become ready'
  local spid
  spid=$(cx systemctl show -p MainPID --value qdrant.service)
  cx ss -H -ltnup >$RUN/raw/listeners-before-restart.txt
  cx ss -H -lnux >$RUN/raw/unix-listeners.txt || true
  cx ip -o addr show >$RUN/raw/interfaces.txt
  cx systemctl show qdrant.service >$RUN/raw/systemd-properties.txt
  cx systemd-analyze security qdrant.service --no-pager >$RUN/raw/systemd-security.txt 2>&1 || true
  cx cat /proc/$spid/status >$RUN/raw/process-status.txt
  {
    local f
    for f in memory.high memory.max pids.max pids.current memory.peak memory.events pids.events; do
      print -r -- "== $f"
      cx cat /sys/fs/cgroup/system.slice/qdrant.service/$f
    done
  } >$RUN/raw/cgroup-limits.txt
  {
    print -r -- "service_home=$(cx nsenter -t $spid -m ls -A /home | tr '\n' ' ')"
    print -r -- "service_root_home=$(cx nsenter -t $spid -m sh -c 'ls -A /root 2>&1' | tr '\n' ' ')"
    print -r -- "service_home_mount=$(cx nsenter -t $spid -m findmnt -no FSTYPE,OPTIONS /home)"
    print -r -- "container_home=$(cx ls -A /home | tr '\n' ' ')"
    print -r -- "container_root_home=$(cx ls -A /root | tr '\n' ' ')"
    local target
    for target in /usr/bin/g2-probe /etc/g2-probe /var/lib/g2-probe /var/lib/qdrant/.g2-probe; do
      if cx nsenter -t $spid -m setpriv --reuid=qdrant --regid=qdrant --clear-groups \
          sh -c "touch $target && rm -f $target" 2>/dev/null; then
        print -r -- "writable $target"
      else
        print -r -- "readonly $target"
      fi
    done
    print -r -- "service_root_mount=$(cx nsenter -t $spid -m findmnt -no OPTIONS /)"
  } >$RUN/raw/service-mount-namespace.txt

  log 'API, JWT, gRPC, CORS, dashboard, and strict-mode checks'
  podman unshare nsenter --target $CPID --net -- \
    python3 $HERE/unit_api_checks.py pre-restart $RUN/private/secret.env $RUN/raw/api-pre-restart.json

  log 'clean service restart'
  cx systemctl restart qdrant.service
  podman unshare nsenter --target $CPID --net -- \
    python3 $HERE/unit_api_checks.py post-restart $RUN/private/secret.env $RUN/raw/api-post-restart.json
  cx ss -H -ltnup >$RUN/raw/listeners-after-restart.txt
  {
    print -r -- "state_use=$(cx df --output=used,pcent -B1 /var/lib/qdrant | tail -n 1)"
    print -r -- "state_fs=$(cx findmnt -no FSTYPE /var/lib/qdrant)"
    print -r -- "n_restarts=$(cx systemctl show -p NRestarts --value qdrant.service)"
  } >$RUN/raw/state-after-restart.txt
  spid=$(cx systemctl show -p MainPID --value qdrant.service)
  cx cat /proc/$spid/status >$RUN/raw/process-status-after-restart.txt
  {
    local f
    for f in pids.current memory.peak memory.events pids.events; do
      print -r -- "== $f"
      cx cat /sys/fs/cgroup/system.slice/qdrant.service/$f
    done
  } >$RUN/raw/cgroup-final.txt

  log 'cleanup'
  cx systemctl stop qdrant.service
  {
    print -r -- "qdrant_processes=$(cx pgrep -c -x qdrant || true)"
    print -r -- "listeners=$(cx ss -H -ltnu | wc -l)"
    cx rm -f /etc/qdrant/qdrant.env
    print -r -- "secret_file_present=$(cx sh -c 'test -e /etc/qdrant/qdrant.env && echo yes || echo no')"
    print -r -- "secret_in_state=$(cx sh -c "grep -rlF \"\$(cut -d= -f2 /run/g2-private/secret.env)\" /var/lib/qdrant 2>/dev/null | wc -l")"
  } >$RUN/raw/cleanup-inside.txt
  cx ss -H -ltnu >$RUN/raw/listeners-after-stop.txt || true
  podman stop -t 30 $NAME >/dev/null
  podman rm $NAME >/dev/null
  rm -f -- $RUN/private/secret.env
  {
    print -r -- "container_exists=$(podman container exists $NAME && echo yes || echo no)"
    print -r -- "secret_host_copy_present=$([[ -e $RUN/private/secret.env ]] && echo yes || echo no)"
  } >$RUN/raw/cleanup-outside.txt
  NAME=''
  log "done: $RUN"
}

main "$@" && rc=0 || rc=$?
cleanup
exit $rc
