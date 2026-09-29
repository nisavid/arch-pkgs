#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
root=${tests_dir%/*}
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT
payload="$scratch/payload"
scanner="$root/procedure/scan-payload-paths.sh"

reset_payload() {
  if [[ -d $payload ]]; then
    find "$payload" -mindepth 1 -depth -delete
  else
    mkdir "$payload"
  fi
}

expect_success() {
  local label=$1 package=${2-generic-package}
  /usr/bin/bash "$scanner" "$payload" "$package" >/dev/null 2>&1 || {
    printf '%s: expected success\n' "$label" >&2
    exit 1
  }
}

expect_failure() {
  local label=$1 package=${2-generic-package}
  if /usr/bin/bash "$scanner" "$payload" "$package" >/dev/null 2>&1; then
    printf '%s: expected failure\n' "$label" >&2
    exit 1
  fi
}

write_portable_manpages() {
  local man="$payload/usr/share/man/man1"
  mkdir -p "$man"
  printf 'default: $HOME/.config/sequoia/sq/config.toml\n' | gzip -n >"$man/sq-config.1.gz"
  printf 'default: $HOME/.local/share/sequoia/revocation-certificates\n' | gzip -n >"$man/sq-key-generate.1.gz"
  printf 'default: $HOME/.local/share/sequoia/revocation-certificates\n' | gzip -n >"$man/sq-key-rotate.1.gz"
  printf 'defaults: $HOME/.config/sequoia/sq/config.toml $HOME/.local/share/pgp.cert.d $HOME/.local/share/sequoia/keystore\n' | gzip -n >"$man/sq.1.gz"
}

reset_payload
printf 'ordinary payload with literal $HOME/.config/tool/config.toml\n' >"$payload/ordinary.txt"
expect_success 'ordinary payload and portable literal'

for home_path in \
  '/home/alex-build' \
  '/home/qa.user'
do
  reset_payload
  printf 'forbidden %s\n' "$home_path" >"$payload/plain.txt"
  expect_failure "plain exact home root: $home_path"
done

for home_path in \
  '/home/reviewer-two' \
  '/home/release_03'
do
  reset_payload
  printf 'forbidden %s\n' "$home_path" | gzip -n >"$payload/compressed.txt.gz"
  expect_failure "gzip exact home root: $home_path"
done

for home_path in \
  '/home/alex-build/workspace/item' \
  '/home/qa.user/cache/item'
do
  reset_payload
  printf 'forbidden %s\n' "$home_path" >"$payload/plain.txt"
  expect_failure "plain generic home path: $home_path"
done

for home_path in \
  '/home/reviewer-two/workspace/item' \
  '/home/release_03/cache/item'
do
  reset_payload
  printf 'forbidden %s\n' "$home_path" | gzip -n >"$payload/compressed.txt.gz"
  expect_failure "gzip generic home path: $home_path"
done

reset_payload
printf 'forbidden /home/corrupt-user/workspace/item\n' |
  gzip -n >"$payload/corrupt-forbidden.txt.gz"
truncate -s -8 "$payload/corrupt-forbidden.txt.gz"
expect_failure 'corrupt gzip that emits a forbidden path'

reset_payload
printf '\x1f\x8bcorrupt ordinary gzip\n' >"$payload/corrupt-ordinary.txt.gz"
expect_failure 'corrupt ordinary gzip'

reset_payload
printf 'ordinary compressed payload\n' | gzip -n >"$payload/permitted.txt.gz"
expect_success 'valid permitted gzip'

for plain_violation in \
  '/work/work/src' \
  'attempt-007'
do
  reset_payload
  printf 'forbidden %s\n' "$plain_violation" >"$payload/plain.txt"
  expect_failure "plain build path: $plain_violation"
done

for gzip_violation in \
  '/attempts/attempt-008' \
  'next-review-execution'
do
  reset_payload
  printf 'forbidden %s\n' "$gzip_violation" | gzip -n >"$payload/compressed.txt.gz"
  expect_failure "gzip build path: $gzip_violation"
done

reset_payload
write_portable_manpages
expect_success 'required manpages and portable defaults' sequoia-sq-pqc

printf 'wrong default: /opt/sequoia/config.toml; unrelated: $HOME/.local/share/pgp.cert.d $HOME/.local/share/sequoia/keystore\n' |
  gzip -n >"$payload/usr/share/man/man1/sq.1.gz"
expect_failure 'wrong required default' sequoia-sq-pqc

reset_payload
write_portable_manpages
rm "$payload/usr/share/man/man1/sq-key-rotate.1.gz"
expect_failure 'missing required manpage' sequoia-sq-pqc

printf 'payload path scan ordinary, generic-home, build-path, and portable-default cases: PASS\n'
