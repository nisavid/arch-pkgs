#!/usr/bin/bash
set -Eeuo pipefail

output=
while (( $# > 0 )); do
  if [[ $1 == --output ]]; then
    output=$2
    shift 2
  else
    shift
  fi
done
[[ -n $output ]]
printf 'synthetic public key\n' >"$output"
