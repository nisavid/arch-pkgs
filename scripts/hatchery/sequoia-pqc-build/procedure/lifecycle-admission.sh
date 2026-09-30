#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
action=${1-verify}
admission="$root/control/lifecycle-admission.txt"
zero_sha=0000000000000000000000000000000000000000000000000000000000000000

names=(prebuild-environment common-setup frozen-boundary failure-boundary-self-test)
paths=(
  output/receipts/prebuild-environment.txt
  setup-evidence/common-setup.txt
  control/frozen-boundary.txt
  review/failure-boundary-self-test.txt
)
schemas=(
  arch-pq-prebuild-environment-v1
  arch-pq-common-setup-v2
  arch-pq-frozen-boundary-v1
  arch-pq-failure-boundary-self-test-v1
)
terminal_keys=(prebuild_capture_exit setup_exit frozen_boundary_exit self_test_exit)

record_field() {
  local record=$1 key=$2
  awk -F= -v key="$key" '
    $1 == key { count++; value=substr($0, length(key) + 2) }
    END { if (count != 1) exit 1; print value }
  ' "$record"
}

require_regular_record() {
  local relative=$1 record="$root/$1" canonical
  [[ -f $record && ! -L $record ]] || {
    printf 'lifecycle prerequisite is not a regular file: %s\n' "$relative" >&2
    return 1
  }
  canonical=$(realpath -e -- "$record")
  [[ $canonical == "$record" && $canonical == "$root/"* ]] || {
    printf 'lifecycle prerequisite is outside its fixed canonical path: %s\n' "$relative" >&2
    return 1
  }
}

declare -a entry_lines=()
predecessor=$zero_sha
for index in 0 1 2 3; do
  relative=${paths[$index]}
  record="$root/$relative"
  require_regular_record "$relative"
  [[ $(record_field "$record" schema) == "${schemas[$index]}" ]]
  [[ $(record_field "$record" "${terminal_keys[$index]}") == 0 ]]
  if [[ ${names[$index]} == frozen-boundary ]]; then
    [[ $(record_field "$record" manifest_path) == control/frozen-boundary.sha256 ]]
    [[ $(record_field "$record" inventory_path) == control/frozen-boundary.inventory.tsv ]]
    [[ $(record_field "$record" manifest_sha256) == \
      "$(sha256sum "$root/control/frozen-boundary.sha256" | cut -d' ' -f1)" ]]
    [[ $(record_field "$record" inventory_sha256) == \
      "$(sha256sum "$root/control/frozen-boundary.inventory.tsv" | cut -d' ' -f1)" ]]
    /usr/bin/bash "$root/procedure/verify-frozen-boundary.sh" >/dev/null
  fi
  record_bytes=$(stat -c %s -- "$record")
  record_sha=$(sha256sum -- "$record" | cut -d' ' -f1)
  chain_sha=$(printf 'step=%s\nname=%s\npath=%s\nbytes=%s\nsha256=%s\npredecessor_sha256=%s\n' \
    "$((index + 1))" "${names[$index]}" "$relative" "$record_bytes" "$record_sha" "$predecessor" |
    sha256sum | cut -d' ' -f1)
  entry_lines+=("entry"$'\t'"$((index + 1))"$'\t'"${names[$index]}"$'\t'"$relative"$'\t'"$record_bytes"$'\t'"$record_sha"$'\t'"$predecessor"$'\t'"$chain_sha")
  predecessor=$chain_sha
done

case "$action" in
  create)
    [[ ! -e $admission && ! -L $admission ]] || {
      printf 'lifecycle admission already exists\n' >&2
      exit 2
    }
    mkdir -p "$root/control"
    {
      printf 'schema=arch-pq-lifecycle-admission-v1\nentry_count=4\n'
      printf '%s\n' "${entry_lines[@]}"
      printf 'terminal_chain_sha256=%s\nlifecycle_admission_exit=0\n' "$predecessor"
    } >"$admission"
    chmod 444 "$admission"
    ;;
  verify)
    require_regular_record control/lifecycle-admission.txt
    mapfile -t actual_lines <"$admission"
    [[ ${#actual_lines[@]} == 8 ]]
    [[ ${actual_lines[0]} == schema=arch-pq-lifecycle-admission-v1 ]]
    [[ ${actual_lines[1]} == entry_count=4 ]]
    for index in 0 1 2 3; do
      [[ ${actual_lines[$((index + 2))]} == "${entry_lines[$index]}" ]]
    done
    [[ ${actual_lines[6]} == "terminal_chain_sha256=$predecessor" ]]
    [[ ${actual_lines[7]} == lifecycle_admission_exit=0 ]]
    ;;
  *)
    printf 'usage: %s {create|verify}\n' "$0" >&2
    exit 2
    ;;
esac

sha256sum -- "$admission" | cut -d' ' -f1
