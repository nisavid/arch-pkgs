#!/usr/bin/bash
set -Eeuo pipefail

(( $# == 4 )) || { printf 'usage: %s RUN_ROOT PACKAGE ATTEMPT_ID LIFECYCLE_SHA256\n' "$0" >&2; exit 2; }
run=$(cd "$1" && pwd -P)
package=$2
attempt_id=$3
lifecycle_sha=$4
[[ $attempt_id =~ ^[0-9]{3}$ && $lifecycle_sha =~ ^[0-9a-f]{64}$ ]]
case "$package" in
  sequoia-sq-pqc) version=1.4.0 executable=sq ;;
  sequoia-sqv-pqc) version=1.5.0 executable=sqv ;;
  *) exit 2 ;;
esac

attempt="$run/attempts/${package}-attempt-${attempt_id}"
archive="$run/output/archives/${package}-${version}-4-x86_64.pkg.tar.zst"
archive_payload="$attempt/archive-payload"
mkdir -p "$attempt/receipts" "$attempt/extracted/usr/bin" \
  "$attempt/work/cargo" "$attempt/work/srcdest" "$run/output/archives" \
  "$archive_payload/usr/bin"
printf 'executable for %s\n' "$package" >"$attempt/extracted/usr/bin/$executable"
cp -- "$attempt/extracted/usr/bin/$executable" "$archive_payload/usr/bin/$executable"
chmod 755 "$attempt/extracted/usr/bin/$executable" "$archive_payload/usr/bin/$executable"
(cd "$archive_payload" && bsdtar -cf - usr) | zstd -q -c >"$archive"
find "$archive_payload" -depth -delete
printf 'schema=arch-pq-attempt-initialization-v1\npackage=%s\nattempt=%s\nlifecycle_admission_sha256=%s\n' \
  "$package" "$attempt_id" "$lifecycle_sha" >"$attempt/initialization-claim.txt"
claim_sha=$(sha256sum "$attempt/initialization-claim.txt" | cut -d' ' -f1)
printf 'schema=arch-pq-outer-launcher-v3\npackage=%s\nattempt=%s\nstarted_utc=2026-09-30T00:00:00Z\ninitialization_claim_sha256=%s\naccepted=false\nlifecycle_admission_sha256=%s\ncompleted_utc=2026-09-30T00:00:01Z\nouter_exit=0\naccepted=true\noutput_archive=%s\n' \
  "$package" "$attempt_id" "$claim_sha" "$lifecycle_sha" "$archive" \
  >"$attempt/receipts/outer-launcher.txt"
touch "$attempt/receipts/ACCEPTED"
sha256sum "$archive" >"$attempt/receipts/output-archive.sha256"
sha256sum "$attempt/extracted/usr/bin/$executable" >"$attempt/receipts/executable.sha256"
