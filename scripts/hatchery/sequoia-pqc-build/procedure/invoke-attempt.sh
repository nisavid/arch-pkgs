#!/usr/bin/bash
set -Eeuo pipefail

host_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
package=${1-}
attempt_id=${2-}
test_mode=${HATCHERY_PROCEDURE_TEST_MODE-0}
test_runner=${HATCHERY_TEST_PHASE_RUNNER-}
test_require_lifecycle=${HATCHERY_TEST_REQUIRE_LIFECYCLE-0}

case "$package" in
  sequoia-sq-pqc)
    version=1.4.0 repo=sequoia-sq tag=v1.4.0
    expected_tag_object=122f3b8ff3b120013d8d96a962df333e7b114fa0
    expected_commit=558e1461d4f277924b0710f17a5bb56469f74ff2
    ;;
  sequoia-sqv-pqc)
    version=1.5.0 repo=sequoia-sqv tag=v1.5.0
    expected_tag_object=e45dd76915c6f661c8f8f371de9218f59f788b9a
    expected_commit=e0dbf9133a1bf605eb2ead3869d9722d8dfc8252
    ;;
  synthetic-procedure-test)
    [[ $test_mode == 1 && -x $test_runner ]] || {
      printf 'synthetic package is available only to the procedure test harness\n' >&2
      exit 2
    }
    version=0
    ;;
  *)
    printf 'usage: %s {sequoia-sq-pqc|sequoia-sqv-pqc} ATTEMPT_ID\n' "$0" >&2
    exit 2
    ;;
esac
[[ $attempt_id =~ ^[0-9]{3}$ ]] || { printf 'attempt id must be three digits\n' >&2; exit 2; }
if [[ $package != synthetic-procedure-test ]] && {
   [[ $test_mode != 0 ]] ||
   [[ -n ${HATCHERY_TEST_PHASE_RUNNER-}${HATCHERY_TEST_FAIL_PHASE-}${HATCHERY_TEST_FAIL_EXIT-}${HATCHERY_TEST_USE_REAL_BOUNDARY-} ]];
}; then
  printf 'test hooks are forbidden for real package attempts\n' >&2
  exit 2
fi

require_prior_lifecycle_bindings() {
  local prior_attempt launcher canonical prior_sha
  local -a prior_attempts=()
  shopt -s nullglob
  prior_attempts=("$host_root"/attempts/*-attempt-*)
  shopt -u nullglob
  for prior_attempt in "${prior_attempts[@]}"; do
    [[ -d $prior_attempt && ! -L $prior_attempt ]]
    canonical=$(realpath -e -- "$prior_attempt")
    [[ $canonical == "$prior_attempt" && $canonical == "$host_root/attempts/"* ]]
    launcher="$prior_attempt/receipts/outer-launcher.txt"
    [[ -f $launcher && ! -L $launcher ]]
    [[ $(realpath -e -- "$launcher") == "$launcher" ]]
    prior_sha=$(awk -F= '
      $1 == "lifecycle_admission_sha256" { count++; value=$2 }
      END { if (count != 1) exit 1; print value }
    ' "$launcher")
    [[ $prior_sha == "$lifecycle_admission_sha256" ]] || {
      printf 'lifecycle admission changed after an earlier attempt: %s\n' "$prior_attempt" >&2
      return 1
    }
  done
}

lifecycle_admission_sha256=
if [[ $package != synthetic-procedure-test ]]; then
  /usr/bin/bash "$host_root/procedure/verify-reviewed-source.sh"
  lifecycle_admission_sha256=$(
    /usr/bin/bash "$host_root/procedure/lifecycle-admission.sh" verify
  )
  [[ ! -e $host_root/output/receipts/final-public-cache-cleanup.txt && \
     ! -L $host_root/output/receipts/final-public-cache-cleanup.txt ]] || {
    printf 'finalization has started; no later real attempt is allowed\n' >&2
    exit 2
  }
elif [[ $test_require_lifecycle == 1 ]]; then
  [[ $test_mode == 1 ]] || {
    printf 'test lifecycle admission is available only to the procedure test harness\n' >&2
    exit 2
  }
  lifecycle_admission_sha256=$(
    /usr/bin/bash "$host_root/procedure/lifecycle-admission.sh" verify
  )
fi
if [[ -n $lifecycle_admission_sha256 ]]; then
  require_prior_lifecycle_bindings
fi

attempt="$host_root/attempts/${package}-attempt-${attempt_id}"
work="$attempt/work"
receipts="$attempt/receipts"
logs="$attempt/logs"
output_dir="$host_root/output/archives"
launcher_receipt="$receipts/outer-launcher.txt"
archive_name="${package}-${version}-4-x86_64.pkg.tar.zst"
source_archive="$work/pkgdest/$archive_name"
output_archive="$output_dir/$archive_name"
output_temp="$output_dir/.${archive_name}.${attempt_id}.partial"
output_created=false
finished=false

[[ ! -e $attempt ]] || { printf 'attempt path already exists: %s\n' "$attempt" >&2; exit 2; }
[[ ! -e $output_archive && ! -e $output_temp ]] || {
  printf 'accepted or partial output already exists for this package release\n' >&2
  exit 2
}
mkdir -p "$receipts" "$logs" "$attempt/extracted" "$attempt/procedure-snapshot" "$output_dir"
for name in home cargo srcdest builddir pkgdest logdest tmp runtime-home gnupg-runtime xdg-cache xdg-config xdg-data; do
  mkdir -p "$work/$name"
done
chmod 700 "$work/home" "$work/tmp" "$work/runtime-home"

printf 'schema=arch-pq-outer-launcher-v2\npackage=%s\nattempt=%s\nstarted_utc=%s\naccepted=false\n' \
  "$package" "$attempt_id" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$launcher_receipt"
if [[ -n $lifecycle_admission_sha256 ]]; then
  printf 'lifecycle_admission_sha256=%s\n' "$lifecycle_admission_sha256" >>"$launcher_receipt"
fi

cleanup_secrets() {
  local name status=0
  for name in home tmp runtime-home gnupg-runtime builddir xdg-cache xdg-config xdg-data; do
    chmod -R u+rwX "$work/$name" 2>/dev/null || true
    find "$work/$name" -mindepth 1 -depth -delete >/dev/null 2>&1 || status=1
    [[ -z $(find "$work/$name" -mindepth 1 -print -quit) ]] || status=1
  done
  return "$status"
}

# shellcheck disable=SC2329 # The EXIT trap invokes this function indirectly.
finish() {
  local status=$?
  trap - EXIT
  if [[ $finished != true ]]; then
    cleanup_secrets || status=90
    rm -f -- "$output_temp" "$receipts/ACCEPTED"
    if [[ $output_created == true ]]; then rm -f -- "$output_archive"; fi
    printf 'completed_utc=%s\nouter_exit=%s\naccepted=false\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$status" >>"$launcher_receipt"
  fi
  exit "$status"
}
trap finish EXIT

verify_frozen_inputs() {
  [[ $test_mode == 1 ]] && return 0
  /usr/bin/bash "$host_root/procedure/verify-reviewed-source.sh"
  /usr/bin/bash "$host_root/procedure/verify-frozen-boundary.sh"
  /usr/bin/bash "$host_root/procedure/verify-toolchain.sh"
}

if [[ $test_mode == 1 ]]; then
  printf 'boundary_verification=test-fixture\n' >>"$launcher_receipt"
else
  verify_frozen_inputs >"$receipts/frozen-input-verification.txt" 2>&1
  cp -a "$host_root/inputs/gnupg-public/." "$work/gnupg-runtime/"
  chmod -R u+rwX "$work/gnupg-runtime"
  cp -a "$host_root/procedure/." "$attempt/procedure-snapshot/"
  find "$attempt/procedure-snapshot" -type f -print0 | LC_ALL=C sort -z |
    xargs -0 sha256sum >"$receipts/procedure-snapshot.sha256"
fi

run_real_phase() {
  local phase=$1
  local -a network=()
  local -a resolver=()
  if [[ $phase == verifysource || $phase == prefetch ]]; then
    network=(--share-net)
    resolver=(--dir /run/systemd --ro-bind /run/systemd/resolve /run/systemd/resolve)
  fi
  local -a command=(
    /usr/bin/bwrap --unshare-all "${network[@]}" --die-with-parent --new-session --clearenv
    --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/bin /sbin
    --symlink usr/lib /lib --symlink usr/lib /lib64
    --ro-bind /etc /etc --ro-bind /sys /sys --ro-bind /var/lib/pacman /var/lib/pacman
    --proc /proc --tmpfs /run "${resolver[@]}" --tmpfs /tmp
    --tmpfs /dev --dev-bind /dev/null /dev/null --dev-bind /dev/zero /dev/zero
    --dev-bind /dev/random /dev/random --dev-bind /dev/urandom /dev/urandom
    --dir /dev/shm --symlink /proc/self/fd /dev/fd --symlink /proc/self/fd/0 /dev/stdin
    --symlink /proc/self/fd/1 /dev/stdout --symlink /proc/self/fd/2 /dev/stderr --chmod 0555 /dev
    --dir /work --dir /work/inputs --dir /work/work
    --ro-bind "$host_root/procedure" /work/procedure
    --ro-bind "$host_root/recipes/$package" /work/recipe
    --ro-bind "$host_root/inputs/rustup" /work/inputs/rustup
    --ro-bind "$host_root/inputs/gnupg-public" /work/inputs/gnupg-public
  )
  local name
  for name in home cargo srcdest builddir pkgdest logdest tmp runtime-home gnupg-runtime xdg-cache xdg-config xdg-data; do
    command+=(--bind "$work/$name" "/work/work/$name")
  done
  command+=(
    --chdir /work/recipe --setenv PATH /usr/bin:/bin --setenv LC_ALL C.UTF-8 --setenv LANG C.UTF-8
    --setenv HOME /work/work/home --setenv GNUPGHOME /work/work/gnupg-runtime
    --setenv CARGO_HOME /work/work/cargo --setenv RUSTUP_HOME /work/inputs/rustup
    --setenv RUSTUP_TOOLCHAIN 1.98.0 --setenv TMPDIR /work/work/tmp
    --setenv SRCDEST /work/work/srcdest --setenv BUILDDIR /work/work/builddir
    --setenv PKGDEST /work/work/pkgdest --setenv LOGDEST /work/work/logdest
    --setenv XDG_CACHE_HOME /work/work/xdg-cache --setenv XDG_CONFIG_HOME /work/work/xdg-config
    --setenv XDG_DATA_HOME /work/work/xdg-data --setenv MAKEFLAGS -j4 --setenv CARGO_BUILD_JOBS 4
    --setenv GIT_CONFIG_GLOBAL /dev/null --setenv GIT_CONFIG_NOSYSTEM 1 --setenv GIT_TERMINAL_PROMPT 0
    /usr/bin/bash /work/procedure/attempt-body.sh "$phase" "$package"
  )
  printf '%q ' "${command[@]}" >"$receipts/${phase}.command"
  printf '\n' >>"$receipts/${phase}.command"
  "${command[@]}"
}

run_phase() {
  local phase=$1 status start end
  start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  set +e
  if [[ $test_mode == 1 && ${HATCHERY_TEST_USE_REAL_BOUNDARY-0} == 1 && $phase == boundary ]]; then
    run_real_phase "$phase" >"$logs/${phase}.log" 2>&1
  elif [[ $test_mode == 1 ]]; then
    "$test_runner" "$phase" "$package" "$attempt" >"$logs/${phase}.log" 2>&1
  elif [[ $phase == capture-source-view ]]; then
    /usr/bin/bash "$host_root/procedure/capture-source-view.sh" "$attempt" \
      "$work/srcdest/$repo" "$attempt/controller-source/$repo.git" "$tag" \
      "$expected_tag_object" "$expected_commit" \
      "$receipts/controller-source-view.txt" "$receipts/controller-source-view.sha256" \
      >"$logs/${phase}.log" 2>&1
  elif [[ $phase == post-build-verify ]]; then
    /usr/bin/bash "$host_root/procedure/post-build-verify.sh" "$package" "$attempt_id" >"$logs/${phase}.log" 2>&1
  else
    run_real_phase "$phase" >"$logs/${phase}.log" 2>&1
  fi
  status=$?
  set -e
  end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf '%s\t%s\t%s\t%s\n' "$phase" "$start" "$end" "$status" >>"$receipts/phase-exits.tsv"
  (( status == 0 )) || return "$status"
  verify_frozen_inputs >>"$receipts/frozen-input-verification.txt" 2>&1
}

printf 'phase\tstarted_utc\tcompleted_utc\texit\n' >"$receipts/phase-exits.tsv"
for phase in boundary verifysource prefetch capture-source-view checked-build post-build-verify; do
  run_phase "$phase"
done

[[ -f $source_archive ]] || { printf 'same-attempt archive missing: %s\n' "$source_archive" >&2; exit 80; }
cleanup_secrets || exit 81
verify_frozen_inputs >>"$receipts/frozen-input-verification.txt" 2>&1
verified_archive_sha=$(cut -d' ' -f1 "$receipts/archive-immediate.sha256")
[[ $(sha256sum "$source_archive" | cut -d' ' -f1) == "$verified_archive_sha" ]]
[[ ! -e $output_archive ]] || { printf 'accepted output already exists: %s\n' "$output_archive" >&2; exit 82; }
cp --reflink=auto "$source_archive" "$output_temp"
cmp -s "$source_archive" "$output_temp"
mv -n "$output_temp" "$output_archive"
[[ ! -e $output_temp ]]
output_created=true
sha256sum "$output_archive" >"$receipts/output-archive.sha256"
[[ $(cut -d' ' -f1 "$receipts/output-archive.sha256") == "$verified_archive_sha" ]]
printf 'completed_utc=%s\nouter_exit=0\naccepted=true\noutput_archive=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$output_archive" >>"$launcher_receipt"
touch "$receipts/ACCEPTED"
finished=true
exit 0
