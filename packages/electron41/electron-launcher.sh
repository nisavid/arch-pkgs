#!/usr/bin/bash

set -euo pipefail

name=@ELECTRON@
if [[ -n "${XDG_CONFIG_HOME:-}" ]]; then
    config_home="${XDG_CONFIG_HOME}"
elif [[ -n "${HOME:-}" ]]; then
    config_home="${HOME}/.config"
else
    echo "error: XDG_CONFIG_HOME and HOME are both unset; cannot determine config directory" >&2
    exit 1
fi
flags_file="${config_home}/${name}-flags.conf"
fallback_file="${config_home}/electron-flags.conf"

lines=()
if [[ -f "${flags_file}" ]]; then
    mapfile -t lines < "${flags_file}"
elif [[ -f "${fallback_file}" ]]; then
    mapfile -t lines < "${fallback_file}"
fi

flags=()
for line in "${lines[@]}"; do
    trimmed_line="${line#"${line%%[![:space:]]*}"}"
    trimmed_line="${trimmed_line%"${trimmed_line##*[![:space:]]}"}"
    if [[ ! "${trimmed_line}" =~ ^#.* ]] && [[ "${trimmed_line}" =~ [^[:space:]] ]]; then
        flags+=("${trimmed_line}")
    fi
done

: "${ELECTRON_IS_DEV:=0}"
export ELECTRON_IS_DEV
: "${ELECTRON_FORCE_IS_PACKAGED:=true}"
export ELECTRON_FORCE_IS_PACKAGED

exec /usr/lib/"${name}"/electron "${flags[@]}" "$@"
