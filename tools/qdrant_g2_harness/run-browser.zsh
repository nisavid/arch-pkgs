#!/usr/bin/env zsh
# G2 browser acceptance launcher.
#
# Extracts the exact qdrant and qdrant-web-ui archives, then runs Qdrant with
# the packaged configuration and the host's reviewed Chrome/Playwright inside a
# Bubblewrap user, mount, network, PID, UTS, and IPC namespace that exposes
# only loopback. /home, /root, and the host's Qdrant configuration and state
# are not mounted. Nothing on the host is installed or started.
#
# Usage: run-browser.zsh <run-root> <qdrant-archive> <qdrant-sha256> <web-ui-archive> <web-ui-sha256> <binary-sha256>

emulate -R zsh
setopt ERR_RETURN NO_UNSET PIPE_FAIL

readonly HERE=${0:A:h}
log() { print -r -- "[g2-browser $(date -u +%H:%M:%SZ)] $*" >&2 }
die() { log "FATAL: $*"; return 1 }

typeset -g RUN=''
cleanup() { [[ -n $RUN && -e $RUN/private/secret.env ]] && rm -f -- $RUN/private/secret.env; return 0 }
# zsh skips EXIT traps when ERR_EXIT fires, so failures return to the
# top level, which always cleans up.
trap 'cleanup; exit 143' TERM
trap 'cleanup; exit 130' INT

check_file() {
  emulate -L zsh
  setopt ERR_RETURN NO_UNSET PIPE_FAIL
  local file=$1 want=$2 got
  [[ -f $file && ! -L $file ]] || die "not a regular file: $file"
  got=$(sha256sum -- $file | cut -d" " -f1)
  [[ $got == $want ]] || die "digest mismatch for ${file:t}: $got"
}

main() {
  (( $# == 6 )) || die 'usage: run-browser.zsh <run-root> <qdrant-archive> <qdrant-sha256> <web-ui-archive> <web-ui-sha256> <binary-sha256>'
  RUN=$1
  local qpkg=${2:A} qsha=$3 wpkg=${4:A} wsha=$5 bsha=$6
  [[ ! -e $RUN ]] || die "run root exists: $RUN"
  check_file $qpkg $qsha
  check_file $wpkg $wsha
  mkdir -p -- $RUN/{qdrant-root,ui-root,out/raw,private} $RUN/state/{storage,snapshots,tmp}
  chmod 700 $RUN/private
  bsdtar -xf $qpkg -C $RUN/qdrant-root --exclude '.PKGINFO' --exclude '.BUILDINFO' --exclude '.MTREE'
  bsdtar -xf $wpkg -C $RUN/ui-root --exclude '.PKGINFO' --exclude '.BUILDINFO' --exclude '.MTREE'
  check_file $RUN/qdrant-root/usr/bin/qdrant $bsha
  umask 077
  print -r -- "QDRANT__SERVICE__API_KEY=$(openssl rand -hex 32)" >$RUN/private/secret.env
  sha256sum $HERE/run-browser.zsh $HERE/browser-namespace.sh $HERE/browser_acceptance.py \
    $HERE/browser_seed.py >$RUN/out/raw/harness.sha256

  local -a etc_binds=()
  local e
  for e in fonts ld.so.cache passwd group nsswitch.conf localtime hosts ssl ca-certificates; do
    [[ -e /etc/$e ]] && etc_binds+=(--ro-bind /etc/$e /etc/$e)
  done

  log 'running the isolated browser acceptance'
  local rc=0
  bwrap --unshare-user --unshare-net --unshare-pid --unshare-uts --unshare-ipc \
    --new-session --die-with-parent --clearenv \
    --overlay-src /usr --overlay-src $RUN/qdrant-root/usr --overlay-src $RUN/ui-root/usr \
    --ro-overlay /usr \
    --symlink usr/bin /bin --symlink usr/bin /sbin \
    --symlink usr/lib /lib --symlink usr/lib /lib64 \
    --proc /proc --dev /dev --tmpfs /tmp \
    --dir /etc $etc_binds \
    --dir /etc/qdrant --ro-bind $RUN/qdrant-root/etc/qdrant/config.yaml /etc/qdrant/config.yaml \
    --dir /var --dir /var/lib --bind $RUN/state /var/lib/qdrant \
    --ro-bind /opt/google/chrome /opt/google/chrome \
    --ro-bind $HERE /g2 \
    --ro-bind $RUN/private /g2-private \
    --bind $RUN/out /g2-out \
    --setenv PATH /usr/bin --setenv HOME /tmp --setenv LANG C.UTF-8 \
    -- /g2/browser-namespace.sh >$RUN/out/raw/namespace.log 2>&1 || rc=$?
  rm -f -- $RUN/private/secret.env
  local ns found=0 p
  ns=$(<$RUN/out/raw/pid-namespace)
  for p in /proc/<->/ns/pid(N); do
    [[ "$(readlink $p 2>/dev/null)" == $ns ]] && found=1
  done
  {
    print -r -- "namespace_exit_status=$rc"
    print -r -- "namespace_processes_remaining=$found"
    print -r -- "secret_host_copy_present=$([[ -e $RUN/private/secret.env ]] && echo yes || echo no)"
  } >$RUN/out/raw/cleanup-outside.txt
  (( rc == 0 )) || die "browser namespace failed with status $rc (see $RUN/out/raw/namespace.log)"
  (( found == 0 )) || die 'processes survived the browser namespace'
  log "done: $RUN"
}

main "$@" && rc=0 || rc=$?
cleanup
exit $rc
