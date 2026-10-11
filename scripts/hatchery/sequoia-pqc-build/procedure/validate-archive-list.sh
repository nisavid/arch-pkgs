#!/usr/bin/bash
set -Eeuo pipefail

listing=${1-}
[[ -f $listing ]] || { printf 'usage: %s ARCHIVE_CONTENTS_LIST\n' "$0" >&2; exit 2; }
awk '
  function normalize(name) {
    gsub(/\/+/, "/", name)
    while (substr(name, 1, 2) == "./") name=substr(name, 3)
    while (name ~ /\/\.\//) gsub(/\/\.\//, "/", name)
    sub(/\/\.$/, "", name)
    sub(/\/+$/, "", name)
    return name
  }
  /^\// || /(^|\/)\.\.($|\/)/ {
    bad=1
    print "unsafe member path: " $0 > "/dev/stderr"
  }
  {
    normalized=normalize($0)
    if (normalized == "" || normalized == ".") next
    count[normalized]++
  }
  END {
    for (name in count) if (count[name] > 1) {
      bad=1
      print "colliding member path: " name > "/dev/stderr"
    }
    exit bad
  }
' "$listing"
