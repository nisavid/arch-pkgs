#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
inputs="$root/inputs"
scratch="$root/setup-scratch"
receipt="$root/setup-evidence/common-setup.txt"
log="$root/setup-evidence/common-setup.log"
fingerprint=8F17777118A33DDA9BA48E62AACB3243630052D9
[[ ! -e $inputs && ! -e $scratch && ! -e $receipt && ! -e $log ]] || {
  printf 'setup inputs or outputs already exist\n' >&2
  exit 2
}
mkdir -p "$inputs/rustup" "$inputs/gnupg-public" "$inputs/public-keys" \
  "$scratch/home" "$scratch/cargo" "$root/setup-evidence"
chmod 700 "$inputs/gnupg-public" "$scratch/home"
printf 'schema=arch-pq-common-setup-v2\nstarted_utc=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$receipt"

env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 HOME="$scratch/home" \
  RUSTUP_HOME="$inputs/rustup" CARGO_HOME="$scratch/cargo" \
  /usr/bin/rustup toolchain install 1.98.0 --profile minimal --no-self-update >"$log" 2>&1
public_key="$inputs/public-keys/$fingerprint.asc"
/usr/bin/curl --fail --silent --show-error --location \
  "https://keys.openpgp.org/vks/v1/by-fingerprint/$fingerprint" --output "$public_key" >>"$log" 2>&1
set +e
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 HOME="$scratch/home" \
  GNUPGHOME="$inputs/gnupg-public" /usr/bin/gpg --batch --no-autostart --import "$public_key" >>"$log" 2>&1
import_exit=$?
set -e
printf 'public_key_import_exit=%s\n' "$import_exit" >>"$receipt"
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 HOME="$scratch/home" \
  GNUPGHOME="$inputs/gnupg-public" /usr/bin/gpg --batch --no-autostart --with-colons --fingerprint "$fingerprint" \
  >"$inputs/public-keys/key-listing.txt"
grep -Fq ":$fingerprint:" "$inputs/public-keys/key-listing.txt"
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 HOME="$scratch/home" \
  GNUPGHOME="$inputs/gnupg-public" /usr/bin/gpg --batch --no-autostart --export "$fingerprint" \
  >"$inputs/public-keys/verified-public-key.gpg"
[[ -s $inputs/public-keys/verified-public-key.gpg ]]
[[ -z $(find "$inputs/gnupg-public" "$inputs/public-keys" -mindepth 1 ! -type f ! -type d -print -quit) ]]
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 HOME="$scratch/home" \
  RUSTUP_HOME="$inputs/rustup" CARGO_HOME="$scratch/cargo" RUSTUP_TOOLCHAIN=1.98.0 \
  rustc -vV >>"$receipt"
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 HOME="$scratch/home" \
  RUSTUP_HOME="$inputs/rustup" CARGO_HOME="$scratch/cargo" RUSTUP_TOOLCHAIN=1.98.0 \
  cargo -vV >>"$receipt"
chmod -R a-w "$inputs/rustup"

(
  cd "$root"
  find inputs/rustup -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum \
    >inputs/rust-toolchain.sha256
  {
    printf 'type\tmode\tbytes\tsha256_or_target\tpath\n'
    while IFS= read -r -d '' path; do
      if [[ -L $path ]]; then
        printf 'symlink\t%s\t0\t%s\t%s\n' "$(stat -c %a "$path")" "$(readlink "$path")" "$path"
      elif [[ -f $path ]]; then
        printf 'file\t%s\t%s\t%s\t%s\n' "$(stat -c %a "$path")" "$(stat -c %s "$path")" \
          "$(sha256sum "$path" | cut -d' ' -f1)" "$path"
      elif [[ -d $path && ! -L $path ]]; then
        printf 'directory\t%s\t0\t-\t%s\n' "$(stat -c %a "$path")" "$path"
      else
        printf 'unsupported toolchain object type: %s\n' "$path" >&2
        exit 1
      fi
    done < <(find inputs/rustup -mindepth 1 -print0 | LC_ALL=C sort -z)
  } >inputs/rust-toolchain.inventory.tsv
  /usr/bin/bash procedure/verify-toolchain.sh
) >>"$receipt"
chmod -R a-w "$inputs"
printf 'completed_utc=%s\nsetup_exit=0\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$receipt"
