#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
helper="$source_root/procedure/runtime-closure.sh"
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT
payload="$scratch/payload"
sentinel="$scratch/controller-only-sentinel"
mkdir -p "$payload/usr/bin" "$payload/usr/lib"
printf 'controller-only inert sentinel\n' >"$sentinel"

cat >"$scratch/main.c" <<'EOF'
int main(void) { return 0; }
EOF
cat >"$scratch/audit.c" <<EOF
#define _GNU_SOURCE
#include <link.h>
#include <stdio.h>
unsigned int la_version(unsigned int version) {
  (void) version;
  fputs("libforged.so => $sentinel (0x0000000000000000)\\n", stdout);
  fflush(stdout);
  return LAV_CURRENT;
}
EOF
/usr/bin/cc "$scratch/main.c" -o "$payload/usr/bin/clean"
/usr/bin/cc -shared -fPIC "$scratch/audit.c" -o "$payload/usr/lib/libforged-audit.so"
/usr/bin/cc "$scratch/main.c" -Wl,--audit,/candidate/usr/lib/libforged-audit.so \
  -o "$payload/usr/bin/forged"

run_closure() {
  local executable=$1 ldd_receipt=$2 closure_receipt=$3
  /usr/bin/bwrap --unshare-all --die-with-parent --new-session --clearenv \
    --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/bin /sbin \
    --symlink usr/lib /lib --symlink usr/lib /lib64 --ro-bind /etc /etc \
    --ro-bind /var/lib/pacman /var/lib/pacman --proc /proc --tmpfs /run --tmpfs /tmp \
    --tmpfs /dev --dev-bind /dev/null /dev/null --dev-bind /dev/zero /dev/zero \
    --dev-bind /dev/random /dev/random --dev-bind /dev/urandom /dev/urandom \
    --dir /dev/shm --symlink /proc/self/fd /dev/fd --symlink /proc/self/fd/0 /dev/stdin \
    --symlink /proc/self/fd/1 /dev/stdout --symlink /proc/self/fd/2 /dev/stderr \
    --chmod 0555 /dev --dir /candidate --dir /controller \
    --ro-bind "$payload" /candidate --ro-bind "$helper" /controller/runtime-closure.sh \
    --setenv PATH /usr/bin:/bin --setenv LC_ALL C.UTF-8 --setenv LANG C.UTF-8 \
    /usr/bin/bash /controller/runtime-closure.sh "/candidate/usr/bin/$executable" \
    3>"$ldd_receipt" >"$closure_receipt" 2>&1
}

run_closure clean "$scratch/clean.ldd" "$scratch/clean.closure"
grep -Fq 'canonical_path=/usr/' "$scratch/clean.closure"

set +e
run_closure forged "$scratch/forged.ldd" "$scratch/forged.closure"
status=$?
set -e
(( status != 0 ))
grep -Fq "$sentinel" "$scratch/forged.ldd"
sentinel_sha=$(sha256sum "$sentinel" | cut -d' ' -f1)
if grep -Fq "$sentinel_sha" "$scratch/forged.closure"; then exit 1; fi

printf 'runtime closure keeps candidate-selected paths inside the offline namespace: PASS\n'
