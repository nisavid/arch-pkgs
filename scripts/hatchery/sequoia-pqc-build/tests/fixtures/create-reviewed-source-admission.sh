#!/usr/bin/bash
set -Eeuo pipefail

root=${1-}
revision=${2-0000000000000000000000000000000000000001}
[[ -d $root && $revision =~ ^[0-9a-f]{40}$ ]]
admission="$root/review-admission"
[[ ! -e $admission ]] || { printf 'review admission already exists\n' >&2; exit 2; }
mkdir "$admission"
printf '%s\n' "$revision" >"$admission/source-revision.txt"
(
  cd "$root"
  printf 'type\tmode\tbytes\tsha256\trepository_path\tstaged_path\n'
  while IFS= read -r -d '' staged_path; do
    case $staged_path in
      procedure/*)
        repository_path="scripts/hatchery/sequoia-pqc-build/$staged_path"
        ;;
      tests/*)
        repository_path="scripts/hatchery/sequoia-pqc-build/$staged_path"
        ;;
      recipes/*)
        repository_path="packages/${staged_path#recipes/}"
        ;;
      *)
        printf 'unsupported staged path: %s\n' "$staged_path" >&2
        exit 2
        ;;
    esac
    printf 'file\t%s\t%s\t%s\t%s\t%s\n' \
      "$(stat -c %a "$staged_path")" "$(stat -c %s "$staged_path")" \
      "$(sha256sum "$staged_path" | cut -d' ' -f1)" \
      "$repository_path" "$staged_path"
  done < <(find procedure recipes tests -type f -print0 | LC_ALL=C sort -z)
) >"$admission/maintained-source.inventory.tsv"
