#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
package=${1-}
attempt_id=${2-}
case "$package" in
  sequoia-sq-pqc)
    version=1.4.0 executable=sq repo=sequoia-sq tag=v1.4.0
    expected_tag_object=122f3b8ff3b120013d8d96a962df333e7b114fa0
    expected_commit=558e1461d4f277924b0710f17a5bb56469f74ff2
    expected_lock=b8d698b3a0556cb0115aec4091a46dbf6ba909b2941a74ba61c99e69e01f5efa
    runtime_args=(version)
    ;;
  sequoia-sqv-pqc)
    version=1.5.0 executable=sqv repo=sequoia-sqv tag=v1.5.0
    expected_tag_object=e45dd76915c6f661c8f8f371de9218f59f788b9a
    expected_commit=e0dbf9133a1bf605eb2ead3869d9722d8dfc8252
    expected_lock=6509c7b5ecde46470e9c4cf7d67048ab5f06fc74ba207905361d6f760abb8b8f
    runtime_args=(--version)
    ;;
  *) exit 2 ;;
esac
[[ $attempt_id =~ ^[0-9]{3}$ ]] || exit 2

attempt="$root/attempts/${package}-attempt-${attempt_id}"
work="$attempt/work"
receipt="$attempt/receipts/post-build-verification.txt"
archive="$work/pkgdest/${package}-${version}-4-x86_64.pkg.tar.zst"
extracted="$attempt/extracted"
runtime_home="$work/runtime-home"
[[ -f $archive && -d $extracted && -z $(find "$extracted" -mindepth 1 -print -quit) ]]
[[ ! -e $receipt ]] || { printf 'post-build receipt already exists\n' >&2; exit 2; }
printf 'schema=arch-pq-post-build-verification-v3\nstarted_utc=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$receipt"

sha256sum "$archive" >"$attempt/receipts/archive-immediate.sha256"
sha512sum "$archive" >"$attempt/receipts/archive-immediate.sha512"
b2sum "$archive" >"$attempt/receipts/archive-immediate.b2"
zstd -t "$archive" >"$attempt/logs/archive-validation.log" 2>&1
pacman -Qp --info "$archive" >"$attempt/receipts/package-info.txt"
bsdtar -tf "$archive" >"$attempt/receipts/archive-contents.txt"

/usr/bin/bash "$root/procedure/validate-archive-list.sh" "$attempt/receipts/archive-contents.txt"
if bsdtar -tvf "$archive" | awk 'substr($0,1,1) !~ /[-d]/ { print; bad=1 } END { exit bad }' \
  >"$attempt/receipts/rejected-member-types.txt"; then
  :
else
  printf 'archive contains a link, device, or other disallowed member type\n' >&2
  exit 20
fi
bsdtar --no-same-owner --no-same-permissions -xf "$archive" -C "$extracted"
find "$extracted" -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum \
  >"$attempt/receipts/extracted-files.sha256"
/usr/bin/bash "$root/procedure/scan-payload-paths.sh" "$extracted" "$package" \
  >"$attempt/receipts/payload-path-scan.txt" 2>&1

candidate="$extracted/usr/bin/$executable"
[[ -x $candidate ]]
sha256sum "$candidate" >"$attempt/receipts/executable.sha256"
readelf -d "$candidate" >"$attempt/receipts/readelf-dynamic.txt"
if grep -Eiq 'lib(nettle|hogweed|gmp)' "$attempt/receipts/readelf-dynamic.txt"; then
  printf 'forbidden classical crypto linkage in candidate\n' >&2
  exit 21
fi
if grep -Eq '\((AUDIT|DEPAUDIT)\)' "$attempt/receipts/readelf-dynamic.txt"; then
  printf 'candidate requests a runtime audit module\n' >&2
  exit 23
fi

mapfile -t locks < <(find "$work/builddir" -type f -name Cargo.lock -print)
(( ${#locks[@]} == 1 ))
sha256sum "${locks[0]}" >"$attempt/receipts/final-lock-hashes.txt"
grep -Fq "$expected_lock" "$attempt/receipts/final-lock-hashes.txt"
controller_gnupg="$attempt/controller-gnupg"
[[ ! -e $controller_gnupg ]]
mkdir "$controller_gnupg"
cp -a "$root/inputs/gnupg-public/." "$controller_gnupg/"
chmod -R u+rwX "$controller_gnupg"
/usr/bin/bash "$root/procedure/verify-source-tag.sh" "$attempt" \
  "$attempt/controller-source/$repo.git" "$attempt/receipts/controller-source-view.sha256" \
  "$tag" "$expected_tag_object" "$expected_commit" "$controller_gnupg" \
  "$attempt/receipts/tag-signature.txt"
printf '%s\n' "$expected_commit" >"$attempt/receipts/source-commit.txt"
bsdtar -xOf "$archive" .BUILDINFO >"$attempt/receipts/BUILDINFO"
bsdtar -xOf "$archive" .PKGINFO >"$attempt/receipts/PKGINFO"
grep -Fxq 'buildenv = !ccache' "$attempt/receipts/BUILDINFO"
grep -Fxq 'buildenv = check' "$attempt/receipts/BUILDINFO"

mkdir -p "$runtime_home/sequoia"
runtime=(
  /usr/bin/bwrap --unshare-all --die-with-parent --new-session --clearenv
  --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/bin /sbin
  --symlink usr/lib /lib --symlink usr/lib /lib64 --ro-bind /etc /etc
  --ro-bind /var/lib/pacman /var/lib/pacman --proc /proc --tmpfs /run --tmpfs /tmp
  --tmpfs /dev --dev-bind /dev/null /dev/null --dev-bind /dev/zero /dev/zero
  --dev-bind /dev/random /dev/random --dev-bind /dev/urandom /dev/urandom
  --dir /dev/shm --symlink /proc/self/fd /dev/fd --symlink /proc/self/fd/0 /dev/stdin
  --symlink /proc/self/fd/1 /dev/stdout --symlink /proc/self/fd/2 /dev/stderr --chmod 0555 /dev
  --dir /candidate --dir /runtime-home --dir /controller
  --ro-bind "$extracted" /candidate --bind "$runtime_home" /runtime-home
  --ro-bind "$root/procedure/runtime-closure.sh" /controller/runtime-closure.sh
  --setenv PATH /usr/bin:/bin --setenv LC_ALL C.UTF-8 --setenv LANG C.UTF-8
  --setenv HOME /runtime-home --setenv SEQUOIA_HOME /runtime-home/sequoia
)
"${runtime[@]}" /usr/bin/bash /controller/runtime-closure.sh "/candidate/usr/bin/$executable" \
  3>"$attempt/receipts/ldd.txt" >"$attempt/receipts/runtime-closure.txt" 2>&1
if grep -Eiq 'lib(nettle|hogweed|gmp)' "$attempt/receipts/ldd.txt"; then exit 22; fi
"${runtime[@]}" "/candidate/usr/bin/$executable" "${runtime_args[@]}" \
  >"$attempt/receipts/runtime-identity.txt" 2>&1
failures=0
for ((iteration=1; iteration<=200; iteration++)); do
  "${runtime[@]}" "/candidate/usr/bin/$executable" "${runtime_args[@]}" >/dev/null 2>&1 ||
    failures=$((failures + 1))
done
printf 'lifecycles=200\nfailures=%s\n' "$failures" >"$attempt/receipts/runtime-lifecycles.txt"
(( failures == 0 ))
printf 'completed_utc=%s\npost_build_verification_exit=0\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$receipt"
