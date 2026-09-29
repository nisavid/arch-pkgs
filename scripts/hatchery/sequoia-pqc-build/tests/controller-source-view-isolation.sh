#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
root=${tests_dir%/*}
capture="$root/procedure/capture-source-view.sh"
verify="$root/procedure/verify-source-tag.sh"
invoke="$root/procedure/invoke-attempt.sh"
post_build="$root/procedure/post-build-verify.sh"
scratch=$(mktemp -d)
cleanup() {
  chmod -R u+rwX "$scratch" 2>/dev/null || true
  find "$scratch" -depth -delete
}
trap cleanup EXIT

[[ -x $capture && -x $verify ]]
grep -Fq 'capture-source-view.sh' "$invoke"
grep -Fq 'verify-source-tag.sh' "$post_build"
! grep -Fq 'git -C "$work/srcdest/$repo" verify-tag' "$post_build"

source_repo="$scratch/source"
mkdir "$source_repo"
git -C "$source_repo" init -q
git -C "$source_repo" config user.name 'Inert Fixture'
git -C "$source_repo" config user.email fixture@example.invalid
printf 'first\n' >"$source_repo/payload"
git -C "$source_repo" add payload
git -C "$source_repo" commit -qm first
commit=$(git -C "$source_repo" rev-parse HEAD)
tag_payload=$(printf 'object %s\ntype commit\ntag v1.0.0\ntagger Inert Fixture <fixture@example.invalid> 0 +0000\n\ninert tag\n-----BEGIN PGP SIGNATURE-----\n\nZmFrZQ==\n-----END PGP SIGNATURE-----\n' "$commit")
tag_object=$(printf '%s' "$tag_payload" | git -C "$source_repo" hash-object -t tag -w --stdin)
git -C "$source_repo" update-ref refs/tags/v1.0.0 "$tag_object"

sentinel="$scratch/sentinel-verifier"
sentinel_log="$scratch/sentinel-executed"
printf '%s\n' '#!/usr/bin/bash' "printf 'executed\\n' >>'$sentinel_log'" \
  'printf "[GNUPG:] VALIDSIG 8F17777118A33DDA9BA48E62AACB3243630052D9 0 0 0 0 0 0 0 0 8F17777118A33DDA9BA48E62AACB3243630052D9\\n" >&2' \
  'exit 0' >"$sentinel"
chmod 755 "$sentinel"
git -C "$source_repo" config gpg.program "$sentinel"
uploadpack_sentinel="$scratch/uploadpack-sentinel"
uploadpack_log="$scratch/uploadpack-executed"
printf '%s\n' '#!/usr/bin/bash' "printf 'executed\\n' >>'$uploadpack_log'" 'exit 1' \
  >"$uploadpack_sentinel"
chmod 755 "$uploadpack_sentinel"
git -C "$source_repo" config uploadpack.packObjectsHook "$uploadpack_sentinel"

view="$scratch/controller-source.git"
capture_receipt="$scratch/capture.txt"
view_manifest="$scratch/controller-source.sha256"
/usr/bin/bash "$capture" "$scratch" "$source_repo" "$view" v1.0.0 "$tag_object" "$commit" \
  "$capture_receipt" "$view_manifest"
[[ ! -e $uploadpack_log ]]
[[ ! -e $view/config && ! -e $view/objects/info/alternates ]]
grep -Fxq "tag_object=$tag_object" "$capture_receipt"
grep -Fxq "source_commit=$commit" "$capture_receipt"
(cd "$scratch" && sha256sum -c "${view_manifest#"$scratch/"}") >/dev/null

printf 'second\n' >"$source_repo/payload"
git -C "$source_repo" add payload
git -C "$source_repo" commit -qm second
second_commit=$(git -C "$source_repo" rev-parse HEAD)
git -C "$source_repo" tag -f v1.0.0 "$second_commit" >/dev/null
git -C "$source_repo" replace "$commit" "$second_commit"
printf '%s\n' "$scratch/nonexistent-object-store" >"$source_repo/.git/objects/info/alternates"
[[ $(env -i PATH=/usr/bin:/bin GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
  GIT_NO_REPLACE_OBJECTS=1 git --git-dir="$view" rev-parse 'v1.0.0^{tag}') == "$tag_object" ]]
[[ $(env -i PATH=/usr/bin:/bin GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
  GIT_NO_REPLACE_OBJECTS=1 git --git-dir="$view" rev-parse 'v1.0.0^{commit}') == "$commit" ]]

keyring="$scratch/keyring"
mkdir "$keyring"
for config_case in generic_program openpgp_program included_program; do
  case_view="$scratch/$config_case.git"
  cp -a "$view" "$case_view"
  chmod u+w "$case_view"
  case "$config_case" in
    generic_program)
      git --git-dir="$case_view" config gpg.program "$sentinel"
      ;;
    openpgp_program)
      git --git-dir="$case_view" config gpg.openpgp.program "$sentinel"
      ;;
    included_program)
      included="$scratch/$config_case.config"
      printf '[gpg "openpgp"]\n\tprogram = %s\n' "$sentinel" >"$included"
      git --git-dir="$case_view" config include.path "$included"
      ;;
  esac
  rm -f -- "$sentinel_log"
  set +e
  env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 HOME="$scratch" \
    GNUPGHOME="$keyring" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
    GIT_NO_REPLACE_OBJECTS=1 /usr/bin/git --git-dir="$case_view" \
    verify-tag --raw v1.0.0 >/dev/null 2>&1
  set -e
  [[ -s $sentinel_log ]]
  rm -f -- "$sentinel_log"
  case_manifest="$scratch/$config_case.sha256"
  relative_case_view=${case_view#"$scratch/"}
  (cd "$scratch" && find "$relative_case_view" -type f -print0 | LC_ALL=C sort -z | \
    xargs -0 sha256sum >"${case_manifest#"$scratch/"}")
  receipt="$scratch/$config_case.receipt"
  set +e
  /usr/bin/bash "$verify" "$scratch" "$case_view" "$case_manifest" v1.0.0 \
    "$tag_object" "$commit" "$keyring" "$receipt" >/dev/null 2>&1
  status=$?
  set -e
  (( status != 0 ))
  [[ ! -e $sentinel_log ]]
done

grep -Fq -- '-c gpg.format=openpgp' "$verify"
grep -Fq -- '-c gpg.program=/usr/bin/gpg' "$verify"
grep -Fq -- '-c gpg.openpgp.program=/usr/bin/gpg' "$verify"
grep -Fq 'GIT_NO_REPLACE_OBJECTS=1' "$verify"
grep -Fq -- '--no-replace-objects' "$verify"
printf 'controller source view and verifier isolation: PASS\n'
