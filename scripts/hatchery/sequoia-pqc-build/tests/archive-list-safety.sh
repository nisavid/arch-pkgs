#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
validator="${tests_dir%/*}/procedure/validate-archive-list.sh"
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT
printf '.BUILDINFO\nusr/\nusr/bin/\nusr/bin/sq\n' >"$scratch/safe"
/usr/bin/bash "$validator" "$scratch/safe"
printf 'usr/bin/sq\n./usr/bin/sq\n' >"$scratch/collision"
if /usr/bin/bash "$validator" "$scratch/collision" >/dev/null 2>&1; then exit 1; fi
printf 'usr/share/doc\nusr/share/doc/\n' >"$scratch/type-collision"
if /usr/bin/bash "$validator" "$scratch/type-collision" >/dev/null 2>&1; then exit 1; fi
printf 'usr/bin/sq\nusr/../etc/shadow\n' >"$scratch/traversal"
if /usr/bin/bash "$validator" "$scratch/traversal" >/dev/null 2>&1; then exit 1; fi
printf 'archive path normalization and traversal rejection: PASS\n'
