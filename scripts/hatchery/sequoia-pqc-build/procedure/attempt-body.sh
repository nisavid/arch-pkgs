#!/usr/bin/bash
set -Eeuo pipefail

phase=${1-}
package=${2-}
config=/work/procedure/makepkg.conf
case "$package" in
  sequoia-sq-pqc|sequoia-sqv-pqc) ;;
  synthetic-procedure-test) [[ $phase == boundary ]] || exit 2 ;;
  *) exit 2 ;;
esac

case "$phase" in
  boundary)
    [[ ! -e /work/receipts && ! -e /work/attempts && ! -e /work/output && ! -e /work/control ]]
    [[ ! -e /work/controller-source ]]
    for path in /work/procedure /work/recipe /work/inputs/rustup /work/inputs/gnupg-public; do
      [[ -r $path && ! -w $path ]]
    done
    for name in home cargo srcdest builddir pkgdest logdest tmp runtime-home gnupg-runtime xdg-cache xdg-config xdg-data; do
      [[ -d /work/work/$name && -w /work/work/$name ]]
      probe="/work/work/$name/.boundary-write-probe"
      : >"$probe"
      rm "$probe"
    done
    for path in /work/procedure /work/recipe /work/inputs/rustup /work/inputs/gnupg-public; do
      if : >"$path/.forbidden-write-probe" 2>/dev/null; then
        printf 'forbidden write succeeded: %s\n' "$path" >&2
        exit 30
      fi
    done
    ;;
  verifysource)
    /usr/bin/makepkg --config "$config" --verifysource -f
    ;;
  prefetch)
    /usr/bin/makepkg --config "$config" --nobuild -f
    ;;
  checked-build)
    CARGO_NET_OFFLINE=true /usr/bin/makepkg --config "$config" --noextract --holdver -f --log
    ;;
  *) exit 2 ;;
esac
