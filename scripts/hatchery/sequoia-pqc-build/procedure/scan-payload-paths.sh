#!/usr/bin/bash
set -Eeuo pipefail

payload=${1-}
package=${2-}
[[ -d $payload ]] || { printf 'usage: %s PAYLOAD_ROOT PACKAGE\n' "$0" >&2; exit 2; }

status=0
forbidden_pattern='/work/|/attempts/|attempt-[0-9]{3}|next-review-execution|/home/[^/[:space:]]+([/[:space:]]|$)'
while IFS= read -r -d '' file; do
  if LC_ALL=C grep -aEn "$forbidden_pattern" "$file"; then
    status=1
  fi
  if [[ $file == *.gz ]]; then
    set +e
    gzip -cd -- "$file" | LC_ALL=C grep -En "$forbidden_pattern"
    pipeline_status=("${PIPESTATUS[@]}")
    set -e
    if (( pipeline_status[0] != 0 )); then
      printf 'invalid gzip payload: %s\n' "${file#"$payload"/}" >&2
      status=1
    fi
    if (( pipeline_status[1] == 0 )); then
      status=1
    elif (( pipeline_status[1] != 1 )); then
      printf 'gzip payload scan failed: %s\n' "${file#"$payload"/}" >&2
      status=1
    fi
  fi
done < <(find "$payload" -type f -print0)

if [[ $package == sequoia-sq-pqc ]]; then
  for page in sq-config.1.gz sq-key-generate.1.gz sq-key-rotate.1.gz sq.1.gz; do
    path="$payload/usr/share/man/man1/$page"
    [[ -f $path ]] || { printf 'required manpage missing: %s\n' "$page" >&2; status=1; continue; }
  done
  assert_default() {
    local page=$1 expected=$2
    if ! gzip -cd -- "$payload/usr/share/man/man1/$page" | sed 's/\\-/-/g' | grep -F "$expected" >/dev/null; then
      printf 'expected default missing from %s: %s\n' "$page" "$expected" >&2
      status=1
    fi
  }
  # shellcheck disable=SC2016 # These are literal defaults in the packaged manpages.
  assert_default sq-config.1.gz '$HOME/.config/sequoia/sq/config.toml'
  # shellcheck disable=SC2016 # These are literal defaults in the packaged manpages.
  assert_default sq-key-generate.1.gz '$HOME/.local/share/sequoia/revocation-certificates'
  # shellcheck disable=SC2016 # These are literal defaults in the packaged manpages.
  assert_default sq-key-rotate.1.gz '$HOME/.local/share/sequoia/revocation-certificates'
  # shellcheck disable=SC2016 # These are literal defaults in the packaged manpages.
  assert_default sq.1.gz '$HOME/.config/sequoia/sq/config.toml'
  # shellcheck disable=SC2016 # These are literal defaults in the packaged manpages.
  assert_default sq.1.gz '$HOME/.local/share/pgp.cert.d'
  # shellcheck disable=SC2016 # These are literal defaults in the packaged manpages.
  assert_default sq.1.gz '$HOME/.local/share/sequoia/keystore'
fi
exit "$status"
