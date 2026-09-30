#!/usr/bin/bash
set -Eeuo pipefail

host_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
action=${1-}
test_mode=${HATCHERY_PROCEDURE_TEST_MODE-0}
fail_step=${HATCHERY_TEST_INITIALIZE_FAIL_STEP-}
signal_step=${HATCHERY_TEST_INITIALIZE_SIGNAL_STEP-}
interrupt_step=${HATCHERY_TEST_INITIALIZE_INTERRUPT_STEP-}

initialization_exit() {
  local exit_status=$?
  trap - EXIT
  exit "$exit_status"
}
trap initialization_exit EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

field() {
  local record=$1 key=$2
  awk -F= -v key="$key" '
    $1 == key { count++; value=substr($0, length(key) + 2) }
    END { if (count != 1) exit 1; print value }
  ' "$record"
}

checkpoint() {
  local step=$1
  [[ $fail_step != "$step" ]] || return 86
  if [[ $signal_step == "$step" ]]; then
    kill -TERM "$$"
  fi
  if [[ $interrupt_step == "$step" ]]; then
    kill -KILL "$$"
  fi
}

validate_launcher() {
  local attempt_root=$1 expected_package=$2 expected_attempt=$3 expected_lifecycle=$4
  local launcher="$attempt_root/receipts/outer-launcher.txt" canonical started claim_sha
  [[ -d $attempt_root && ! -L $attempt_root ]]
  [[ -f $launcher && ! -L $launcher ]]
  canonical=$(realpath -e -- "$launcher")
  [[ $canonical == "$launcher" && $canonical == "$attempt_root/receipts/outer-launcher.txt" ]]
  [[ $(field "$launcher" schema) == arch-pq-outer-launcher-v3 ]]
  [[ $(field "$launcher" package) == "$expected_package" ]]
  [[ $(field "$launcher" attempt) == "$expected_attempt" ]]
  started=$(field "$launcher" started_utc)
  [[ $started =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
  claim_sha=$(field "$launcher" initialization_claim_sha256)
  [[ $claim_sha =~ ^[0-9a-f]{64}$ ]]
  [[ $(awk -F= '$1 == "accepted" { count++; if (count == 1) first=$2 }
      END { if (count == 0) exit 1; print first }' "$launcher") == false ]]
  if [[ -n $expected_lifecycle ]]; then
    [[ $(field "$launcher" lifecycle_admission_sha256) == "$expected_lifecycle" ]]
  else
    [[ $(awk -F= '$1 == "lifecycle_admission_sha256" { count++ }
        END { print count+0 }' "$launcher") == 0 ]]
  fi
}

verify_canonical() {
  local attempt_root=$1 expected_lifecycle=$2 canonical package attempt_id
  [[ -d $attempt_root && ! -L $attempt_root ]]
  canonical=$(realpath -e -- "$attempt_root")
  [[ $canonical == "$attempt_root" && $canonical == "$host_root/attempts/"* ]]
  package=$(field "$attempt_root/receipts/outer-launcher.txt" package)
  attempt_id=$(field "$attempt_root/receipts/outer-launcher.txt" attempt)
  [[ $attempt_id =~ ^[0-9]{3}$ ]]
  [[ $attempt_root == "$host_root/attempts/${package}-attempt-${attempt_id}" ]]
  validate_launcher "$attempt_root" "$package" "$attempt_id" "$expected_lifecycle"
}

case "$action" in
  create)
    (( $# == 4 )) || {
      printf 'usage: %s create PACKAGE ATTEMPT_ID LIFECYCLE_SHA256\n' "$0" >&2
      exit 2
    }
    package=$2
    attempt_id=$3
    lifecycle_admission_sha256=$4
    case "$package" in
      sequoia-sq-pqc|sequoia-sqv-pqc) ;;
      synthetic-procedure-test)
        [[ $test_mode == 1 ]] || exit 2
        ;;
      *) exit 2 ;;
    esac
    [[ $attempt_id =~ ^[0-9]{3}$ ]]
    [[ -z $lifecycle_admission_sha256 || $lifecycle_admission_sha256 =~ ^[0-9a-f]{64}$ ]]
    if [[ -n ${fail_step}${signal_step}${interrupt_step} ]]; then
      [[ $package == synthetic-procedure-test && $test_mode == 1 ]] || {
        printf 'initialization test hooks are forbidden for real package attempts\n' >&2
        exit 2
      }
    fi

    attempts_root="$host_root/attempts"
    output_root="$host_root/output/archives"
    staging="$attempts_root/.initializing-${package}-attempt-${attempt_id}"
    canonical="$attempts_root/${package}-attempt-${attempt_id}"
    [[ ! -e $canonical && ! -L $canonical ]] || {
      printf 'attempt path already exists: %s\n' "$canonical" >&2
      exit 2
    }
    [[ ! -e $staging && ! -L $staging ]] || {
      printf 'attempt initialization claim already exists: %s\n' "$staging" >&2
      exit 2
    }

    mkdir -p "$attempts_root"
    checkpoint after-attempts-root
    [[ -d $attempts_root && ! -L $attempts_root ]]
    mkdir -p "$output_root"
    checkpoint after-output-archives
    [[ -d $output_root && ! -L $output_root ]]
    checkpoint before-staging
    mkdir "$staging"
    checkpoint after-staging

    claim_temp="$staging/.initialization-claim.txt.partial"
    claim="$staging/initialization-claim.txt"
    printf 'schema=arch-pq-attempt-initialization-v1\npackage=%s\nattempt=%s\nlifecycle_admission_sha256=%s\n' \
      "$package" "$attempt_id" "${lifecycle_admission_sha256:-none}" >"$claim_temp"
    checkpoint after-claim-write
    chmod 444 "$claim_temp"
    checkpoint after-claim-chmod
    mv -- "$claim_temp" "$claim"
    checkpoint after-claim-publish
    [[ -f $claim && ! -L $claim ]]

    directories=(receipts logs extracted procedure-snapshot work)
    work_directories=(home cargo srcdest builddir pkgdest logdest tmp runtime-home gnupg-runtime xdg-cache xdg-config xdg-data)
    for name in "${directories[@]}"; do
      mkdir "$staging/$name"
      checkpoint "after-directory-$name"
    done
    for name in "${work_directories[@]}"; do
      mkdir "$staging/work/$name"
      checkpoint "after-directory-work-$name"
    done
    for name in home tmp runtime-home; do
      chmod 700 "$staging/work/$name"
      checkpoint "after-chmod-work-$name"
    done

    launcher_temp="$staging/receipts/.outer-launcher.txt.partial"
    launcher="$staging/receipts/outer-launcher.txt"
    claim_sha=$(sha256sum "$claim" | cut -d' ' -f1)
    printf 'schema=arch-pq-outer-launcher-v3\npackage=%s\nattempt=%s\nstarted_utc=%s\ninitialization_claim_sha256=%s\naccepted=false\n' \
      "$package" "$attempt_id" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$claim_sha" >"$launcher_temp"
    if [[ -n $lifecycle_admission_sha256 ]]; then
      printf 'lifecycle_admission_sha256=%s\n' "$lifecycle_admission_sha256" >>"$launcher_temp"
    fi
    checkpoint after-launcher-write
    chmod 600 "$launcher_temp"
    checkpoint after-launcher-chmod
    mv -- "$launcher_temp" "$launcher"
    checkpoint after-launcher-publish
    validate_launcher "$staging" "$package" "$attempt_id" "$lifecycle_admission_sha256"
    checkpoint after-launcher-validation
    checkpoint before-canonical-rename
    mv -T -- "$staging" "$canonical"
    checkpoint after-canonical-rename
    validate_launcher "$canonical" "$package" "$attempt_id" "$lifecycle_admission_sha256"
    ;;
  verify)
    (( $# == 3 )) || {
      printf 'usage: %s verify ATTEMPT_PATH LIFECYCLE_SHA256\n' "$0" >&2
      exit 2
    }
    verify_canonical "$2" "$3"
    ;;
  *)
    printf 'usage: %s {create|verify} ...\n' "$0" >&2
    exit 2
    ;;
esac

trap - EXIT HUP INT TERM
