#!/usr/bin/env zsh

set -euo pipefail

readonly DEFAULT_HTTP_PORT=16333
readonly DEFAULT_GRPC_PORT=16334
readonly MIGRATION_SCRIPT_PATH=${0:A}
readonly FIXTURE_COLLECTION='migration-fixture'
readonly FIXTURE_ALIAS='migration-current'
readonly FIXTURE_PRIMARY_ID='00000000-0000-4000-8000-000000000001'
readonly FIXTURE_SECONDARY_ID='00000000-0000-4000-8000-000000000002'
readonly FIXTURE_POINT_COUNT=1001
readonly FIXTURE_SCROLL_PAGE_SIZE=128
readonly FIXTURE_SCROLL_PAGE_COUNT=8
readonly FIXTURE_MAX_QUERY_LIMIT=1000
readonly EVIDENCE_SCHEMA='qdrant-migration-evidence/v1'
readonly INTERRUPT_RECEIPT_SCHEMA='qdrant-migration-interrupt-receipt/v1'
readonly INTERRUPT_READINESS_SCHEMA='qdrant-migration-interrupt-readiness/v1'
readonly QDRANT_1_17_PACKAGE_NAME='qdrant-1.17.1-1-x86_64.pkg.tar.zst'
readonly QDRANT_1_17_PACKAGE_SHA256='d237ac6b804c7b4ec3f73f8ef57340ebaba62abff7853636286f140c8affd5cb'
readonly QDRANT_1_17_PACKAGE_SIZE=25531392
readonly QDRANT_1_17_BINARY_SHA256='1d9e300802fe1588c6b6aef5167c32f8d215b5d79c07eaf6699ea1a80d92bf72'
readonly QDRANT_1_17_CONFIG_SHA256='23f9b7628f8886edf1d6dbd45216a3755eb28bcf00c1e38d391087de58c81bde'
readonly QDRANT_1_18_BINARY_SHA256='97c16f4582cc0b9f86c7b451d88f7ea8ca56a1e45582168241de7487d31546a7'
readonly QDRANT_1_19_BINARY_SHA256='bf24efd92208fab1a8f4769a56158280b458b7a42850095ac875824571005f8c'
readonly ISOLATED_MEMORY_MAX_BYTES=536870912
readonly ISOLATED_MEMORY_HIGH_BYTES=503316480
readonly TRANSIENT_RUNTIME_MAX_SEC=900
readonly TRANSIENT_TIMEOUT_STOP_SEC=30
readonly SUPERVISED_INTERRUPT_WAIT_STATUS=143

readonly -a required_g3_obligations=(
  isolation_boundary
  fixture_schema_verified
  fixture_filters_verified
  fixture_pagination_verified
  fixture_query_limit_verified
  fixture_queries_captured
  empty_1_17_anchor_sealed
  empty_1_18_start_stop
  empty_1_19_fixture_verified
  snapshot_collection_1_17
  snapshot_full_1_17
  snapshot_collection_1_18
  snapshot_full_1_18
  snapshot_collection_1_19
  cold_copy_1_17_sealed
  cold_copy_1_18_sealed
  cold_migration_1_17_to_1_18_verified
  cold_migration_1_18_to_1_19_verified
  restore_1_17_same_1_17
  restore_1_17_next_1_18
  restore_1_18_same_1_18
  restore_1_18_next_1_19
  restore_1_19_same_1_19
  restore_full_1_17_next_1_18
  restore_full_1_18_next_1_19
  reject_1_17_to_1_18_truncated
  retry_1_17_to_1_18_truncated
  reject_1_17_to_1_18_checksum
  retry_1_17_to_1_18_checksum
  reject_1_18_to_1_19_truncated
  retry_1_18_to_1_19_truncated
  reject_1_18_to_1_19_checksum
  retry_1_18_to_1_19_checksum
  disk_below_threshold_write
  disk_above_threshold_rejection
  disk_release_margin_recovery
  memory_below_threshold_write
  memory_above_threshold_rejection
  memory_release_margin_recovery
  disk_integrity_after_pressure
  memory_integrity_after_pressure
  final_cleanup_verified
)

typeset -g MIGRATION_WORK_ROOT=''
typeset -g MIGRATION_API_KEY=''
typeset -g MIGRATION_ACTIVE_PID=''
typeset -g MIGRATION_ACTIVE_START=''
typeset -g MIGRATION_ACTIVE_EXE=''
typeset -g MIGRATION_ACTIVE_LOG=''
typeset -g MIGRATION_HTTP_PORT=$DEFAULT_HTTP_PORT
typeset -g MIGRATION_GRPC_PORT=$DEFAULT_GRPC_PORT
typeset -g MIGRATION_BASE_URL=''
typeset -g MIGRATION_DENSE_FINGERPRINT=''
typeset -g MIGRATION_SPARSE_FINGERPRINT=''
typeset -g MIGRATION_HYBRID_FINGERPRINT=''
typeset -g MIGRATION_QUERY_SET_SHA256=''
typeset -g MIGRATION_FIXTURE_SPEC_SHA256=''
typeset -g MIGRATION_FIXTURE_POINTS_SHA256=''
typeset -g MIGRATION_FIXTURE_IDS_SHA256=''
typeset -g MIGRATION_FIXTURE_SCHEMA_SHA256=''
typeset -g MIGRATION_FIXTURE_INDEXED_FILTER_SHA256=''
typeset -g MIGRATION_FIXTURE_UNINDEXED_FILTER_SHA256=''
typeset -g MIGRATION_FIXTURE_PAGINATION_SHA256=''
typeset -g MIGRATION_FIXTURE_LIMIT_SHA256=''
typeset -g MIGRATION_EVENTS_FILE=''
typeset -g MIGRATION_PARENT_NETNS=''
typeset -g MIGRATION_CURRENT_NETNS=''
typeset -g MIGRATION_CGROUP_PATH=''
typeset -g MIGRATION_CGROUP_MEMORY_MAX=''
typeset -g MIGRATION_CGROUP_MEMORY_HIGH=''
typeset -g MIGRATION_LAST_HTTP_CODE=''
typeset -g MIGRATION_LAST_HTTP_BODY=''
typeset -g MIGRATION_LAST_PROCESS_EXIT=''
typeset -g MIGRATION_LAST_REJECTION_LOG_SHA256=''
typeset -g MIGRATION_TRANSIENT_UNIT=''
typeset -g MIGRATION_TRANSIENT_CLIENT_PID=''
typeset -g MIGRATION_TRANSIENT_CLIENT_START=''
typeset -g MIGRATION_TRANSIENT_CLIENT_EXE=''
typeset -g MIGRATION_TRANSIENT_KEEPALIVE_FD=''
typeset -g MIGRATION_TRANSIENT_WAIT_COMPLETED=0
typeset -g MIGRATION_TRANSIENT_WAIT_UNIT=''
typeset -g MIGRATION_TRANSIENT_WAIT_STATUS=''
typeset -g MIGRATION_SUPERVISOR_MODE=0
typeset -g MIGRATION_SUPERVISOR_CHILD_PID=''
typeset -g MIGRATION_SUPERVISOR_CHILD_START=''
typeset -g MIGRATION_SUPERVISOR_CHILD_EXE=''
typeset -g MIGRATION_SUPERVISOR_WATCHER_PID=''
typeset -g MIGRATION_FINAL_MANIFEST_TMP=''
typeset -g MIGRATION_QDRANT_1_17_PACKAGE_SHA256=''
typeset -g MIGRATION_QDRANT_1_17_PACKAGE_SIZE=''
typeset -g MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256=''
typeset -g MIGRATION_QDRANT_1_17_CONFIG_SHA256=''
typeset -g MIGRATION_QDRANT_1_18_BINARY_SHA256=''
typeset -g MIGRATION_QDRANT_1_19_BINARY_SHA256=''
typeset -g MIGRATION_TOOL_SHA256=''
typeset -g MIGRATION_PROBE_SIGNAL=''
typeset -g MIGRATION_PROBE_RECEIPT=''
typeset -g MIGRATION_PROBE_TARGET_IDENTITY_SHA256=''
typeset -g MIGRATION_PROBE_TARGET_EXE_SHA256=''
typeset -g MIGRATION_PROBE_SENDER_PID=''
typeset -g MIGRATION_TRANSIENT_CGROUP=''
typeset -g MIGRATION_PROBE_READINESS_MARKER=''
typeset -g MIGRATION_PROBE_READINESS_SHA256=''
typeset -g MIGRATION_PROBE_OWNED_PROCESS_OBSERVED=0
typeset -g MIGRATION_PROBE_HTTP_LISTENER_OBSERVED=0
typeset -g MIGRATION_PROBE_GRPC_LISTENER_OBSERVED=0
typeset -g MIGRATION_PROBE_ISOLATED_NETNS_OBSERVED=0
typeset -g MIGRATION_HANDLING_SIGNAL=0
typeset -g MIGRATION_INT_RECEIPT=''
typeset -g MIGRATION_TERM_RECEIPT=''
typeset -g MIGRATION_INT_RECEIPT_SHA256=''
typeset -g MIGRATION_TERM_RECEIPT_SHA256=''

usage() {
  print -r -- 'Usage:
  validate_qdrant_migration.zsh --plan \
    --qdrant-1.17.1-package PATH \
    --qdrant-1.17.1 PATH \
    --qdrant-1.18.3 PATH \
    --qdrant-1.19.0 PATH

  validate_qdrant_migration.zsh --execute \
    --work-root /tmp/FRESH-DIRECTORY \
    [--http-port 16333] \
    [--grpc-port 16334] \
    --int-receipt PATH \
    --term-receipt PATH \
    --qdrant-1.17.1-package PATH \
    --qdrant-1.17.1 PATH \
    --qdrant-1.18.3 PATH \
    --qdrant-1.19.0 PATH

  validate_qdrant_migration.zsh --probe-interrupt INT|TERM \
    --receipt /tmp/qdrant-migration-interrupt-INT-or-TERM.json \
    --work-root /tmp/FRESH-DIRECTORY \
    --qdrant-1.17.1-package PATH \
    --qdrant-1.17.1 PATH \
    --qdrant-1.18.3 PATH \
    --qdrant-1.19.0 PATH

Modes:
  --plan                 Validate the three binary inputs and print the
                         disposable acceptance sequence without starting a
                         process, opening a socket, or changing storage.
  --execute              Run the acceptance sequence in a fresh, explicitly
                         supplied work root under /tmp. Execution enters a
                         transient cgroup and a Bubblewrap user, mount, PID,
                         and loopback-only network namespace. The root is
                         retained as evidence; only owned child processes and
                         ephemeral authentication material are cleaned up.
  --probe-interrupt SIG  Launch the same isolation boundary, deliver INT or
                         TERM to the exact outer process, and write a public-safe
                         fail-closed cleanup receipt.

Execute inputs:
  --work-root PATH       Required, absolute, canonical, nonexistent path below
                         /tmp. Existing paths are rejected rather than reused.
  --http-port PORT       High loopback HTTP port (default: 16333).
  --grpc-port PORT       Distinct high loopback gRPC port (default: 16334).
  --receipt PATH         Required, new /tmp JSON path for an interrupt probe.
  --int-receipt PATH     Accepted exact-head INT receipt required by --execute.
  --term-receipt PATH    Accepted exact-head TERM receipt required by --execute.

Artifact inputs:
  --qdrant-1.17.1-package PATH
                         Exact retained qdrant 1.17.1-1 x86_64 package archive.
  --qdrant-1.17.1 PATH   Installed baseline binary.
  --qdrant-1.18.3 PATH   Retained consecutive-minor migration binary.
  --qdrant-1.19.0 PATH   Final candidate binary.

Execution never opens the system service, configuration, or storage. It does
not install packages and never uses --force_snapshot, priority=no_sync, or a
compatibility-suppression option.'
}

fail() {
  print -ru2 -- "qdrant migration validation: $*"
  return 2
}

print_plan() {
  print -r -- 'Qdrant disposable acceptance plan

empty-state route
  1. Preserve a pristine 1.17.1 rollback anchor and prove 1.18.3 starts and
     stops against its own matching empty state.
  2. Start qdrant 1.19.0 against fresh empty storage with loopback-only HTTP
     and gRPC plus fail-closed authentication.
  3. Prove stable ID writes, dense/sparse/hybrid query equivalence, restart
     persistence, snapshot creation, and restore into a separate target.

retained-data route
  1. Create the deterministic 1001-point fixture with qdrant 1.17.1, stable IDs,
     an alias, indexed and unindexed filters, eight-page traversal, query limit 1000
     acceptance, and query limit 1001 rejection while the server stays ready.
  2. Stop every writer and preserve an immutable cold copy and snapshot.
  3. Restore the preserved 1.17.1 collection snapshot with 1.17.1 and 1.18.3,
     including alias replay, stable IDs, and equivalent query results.
  4. Restore the 1.17.1 full-storage snapshot into a separate 1.18.3 target.
  5. Prove truncated and checksum-mismatched recovery rejection at the
     1.17.1 -> 1.18.3 boundary, followed by valid same-target retries.
  6. Open only a copied 1.17.1 tree with qdrant 1.18.3, verify it, and preserve
     a new immutable cold copy plus collection and full-storage snapshots.
  7. Restore the 1.18.3 collection snapshot with both 1.18.3 and 1.19.0, then
     repeat both corruption rejections and recoverable retries.
  8. Restore the 1.18.3 full-storage snapshot into a separate 1.19.0 target.
  9. Open only the 1.18.3 cold copy with qdrant 1.19.0; verify restart persistence,
     four-stage disk and memory fingerprints, rejected-write absence, and cleanup.

Each full-storage restore verifies the complete fixture and a clean restart.

No older binary may open storage migrated by a newer minor. Every rollback
uses the matching binary, configuration, and untouched state or compatible
snapshot.'
}

record_event() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local event_id=$1
  local category=$2
  local details=${3:-{}}
  [[ -n $MIGRATION_EVENTS_FILE && -f $MIGRATION_EVENTS_FILE ]] ||
    fail 'internal error: evidence event ledger is unavailable'
  print -r -- "$details" | jq -e 'type == "object"' >/dev/null ||
    fail "internal error: invalid event details for $event_id"
  if jq -e --arg id "$event_id" 'select(.id == $id)' "$MIGRATION_EVENTS_FILE" >/dev/null; then
    fail "duplicate evidence event: $event_id"
  fi
  jq -nc --arg id "$event_id" --arg category "$category" \
    --argjson details "$details" \
    '{id:$id, category:$category, status:"pass", details:$details}' \
    >> "$MIGRATION_EVENTS_FILE"
}

file_sha256() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local artifact=$1
  local digest=''
  [[ -f $artifact ]] || fail "cannot hash missing regular file: $artifact"
  digest=$(sha256sum -- "$artifact")
  print -r -- ${digest%% *}
}

text_sha256() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local value=$1
  local digest=''
  digest=$(print -rn -- "$value" | sha256sum)
  print -r -- ${digest%% *}
}

json_boolean_from_integer() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local value=$1
  case $value in
    0) print -r -- false ;;
    1) print -r -- true ;;
    *) fail "cannot serialize non-boolean integer as JSON: $value" ;;
  esac
}

record_snapshot() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local event_id=$1
  local source_version=$2
  local kind=$3
  local artifact=$4
  [[ -s $artifact ]] || fail "snapshot evidence is missing or empty: $artifact"
  record_event "$event_id" snapshot "$(jq -nc \
    --arg source_version "$source_version" --arg kind "$kind" \
    --arg name "${artifact:t}" --arg snapshot_sha256 "$(file_sha256 "$artifact")" \
    --argjson size "$(stat -c '%s' -- "$artifact")" \
    '{source_version:$source_version,kind:$kind,name:$name,snapshot_sha256:$snapshot_sha256,size:$size}')"
}

record_cold_copy() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local event_id=$1
  local source_version=$2
  local cold_root=$3
  local manifest=$MIGRATION_WORK_ROOT/evidence/$event_id.files
  local entry=''
  local relative=''
  local mode=''
  local digest=''
  local -a entries=()

  [[ -d $cold_root ]] || fail "cold copy is missing: $cold_root"
  entries=("$cold_root"/**/*(N-.D))
  (( ${#entries} )) || fail "cold copy has no regular files: $cold_root"
  : >| "$manifest"
  for entry in ${(o)entries}; do
    relative=${entry#$cold_root/}
    mode=$(stat -c '%a' -- "$entry")
    digest=$(file_sha256 "$entry")
    print -r -- "$mode $digest $relative" >> "$manifest"
  done
  chmod 600 -- "$manifest"
  record_event "$event_id" cold_copy "$(jq -nc \
    --arg source_version "$source_version" --arg name "${cold_root:t}" \
    --arg cold_copy_manifest "${manifest:t}" \
    --arg cold_copy_manifest_sha256 "$(file_sha256 "$manifest")" \
    --argjson files "${#entries}" \
    '{source_version:$source_version,name:$name,cold_copy_manifest:$cold_copy_manifest,cold_copy_manifest_sha256:$cold_copy_manifest_sha256,files:$files,sealed_read_only:true}')"
}

verify_isolation_boundary() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local links=''
  local cgroup_line=''
  local sensitive_root=''
  local non_loopback_status=0

  [[ ${QDRANT_MIGRATION_ISOLATED:-} == 1 ]] ||
    fail 'execute isolation marker is absent; refusing unisolated execution'
  MIGRATION_PARENT_NETNS=${QDRANT_MIGRATION_PARENT_NETNS:-}
  [[ -n $MIGRATION_PARENT_NETNS ]] || fail 'execute isolation parent namespace identity is absent'
  MIGRATION_CURRENT_NETNS=$(readlink -- /proc/self/ns/net)
  [[ $MIGRATION_CURRENT_NETNS != $MIGRATION_PARENT_NETNS ]] ||
    fail 'execute isolation did not create a distinct network namespace'

  links=$(ip -j link show)
  print -r -- "$links" | jq -e \
    'length == 1 and .[0].ifname == "lo" and (.[0].flags | index("UP")) != null' >/dev/null ||
    fail 'execute isolation must expose only an enabled loopback interface'
  python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); s.close()' ||
    fail 'execute isolation loopback bind probe failed'
  if curl -q --noproxy '*' --silent --show-error --connect-timeout 1 --max-time 2 \
    http://1.1.1.1/ >/dev/null 2>&1; then
    fail 'execute isolation allowed non-loopback egress'
  else
    non_loopback_status=$?
  fi
  (( non_loopback_status != 0 )) || fail 'execute isolation egress probe was inconclusive'

  cgroup_line=$(</proc/self/cgroup)
  [[ $cgroup_line == 0::* ]] || fail 'execute isolation requires a unified cgroup v2 membership'
  MIGRATION_CGROUP_PATH=${cgroup_line#0::}
  [[ -r /sys/fs/cgroup$MIGRATION_CGROUP_PATH/memory.max ]] ||
    fail 'execute isolation cgroup memory.max is unreadable'
  MIGRATION_CGROUP_MEMORY_MAX=$(</sys/fs/cgroup$MIGRATION_CGROUP_PATH/memory.max)
  MIGRATION_CGROUP_MEMORY_HIGH=$(</sys/fs/cgroup$MIGRATION_CGROUP_PATH/memory.high)
  [[ $MIGRATION_CGROUP_MEMORY_MAX == $ISOLATED_MEMORY_MAX_BYTES ]] ||
    fail "execute isolation memory ceiling mismatch: $MIGRATION_CGROUP_MEMORY_MAX"
  [[ $MIGRATION_CGROUP_MEMORY_HIGH == $ISOLATED_MEMORY_HIGH_BYTES ]] ||
    fail "execute isolation memory-high mismatch: $MIGRATION_CGROUP_MEMORY_HIGH"

  for sensitive_root in /home /root /etc/qdrant /var/lib/qdrant; do
    [[ ! -e $sensitive_root ]] ||
      fail "execute isolation exposed a host-sensitive root: $sensitive_root"
  done
  [[ -d /usr && -L /bin && -L /sbin && -L /lib && -L /lib64 ]] ||
    fail 'execute isolation did not establish the minimal usr-merged runtime view'
}

require_command() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  command -v -- $1 >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

validate_binary_inputs() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local qdrant_1_17=$1
  local qdrant_1_18=$2
  local qdrant_1_19=$3
  local -a invalid_inputs=()

  [[ -n $qdrant_1_17 && -f $qdrant_1_17 && -x $qdrant_1_17 ]] ||
    invalid_inputs+=("qdrant 1.17.1 binary is not an executable regular file: ${qdrant_1_17:-<missing>}")
  [[ -n $qdrant_1_18 && -f $qdrant_1_18 && -x $qdrant_1_18 ]] ||
    invalid_inputs+=("qdrant 1.18.3 binary is not an executable regular file: ${qdrant_1_18:-<missing>}")
  [[ -n $qdrant_1_19 && -f $qdrant_1_19 && -x $qdrant_1_19 ]] ||
    invalid_inputs+=("qdrant 1.19.0 binary is not an executable regular file: ${qdrant_1_19:-<missing>}")

  if (( ${#invalid_inputs} )); then
    local diagnostic
    for diagnostic in $invalid_inputs; do
      print -ru2 -- "qdrant migration validation: $diagnostic"
    done
    return 2
  fi
}

validate_qdrant_1_17_package() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local package=$1
  local supplied_binary=$2
  local package_sha=''
  local package_size=''
  local package_binary_sha=''
  local package_config_sha=''
  local supplied_binary_sha=''
  local pkginfo=''

  [[ -n $package && -f $package && ! -L $package ]] ||
    fail "qdrant 1.17.1 package is not a regular non-symlink archive: ${package:-<missing>}"
  [[ ${package:t} == $QDRANT_1_17_PACKAGE_NAME ]] ||
    fail "qdrant 1.17.1 package filename is not exact: ${package:t}"
  package_sha=$(file_sha256 "$package")
  [[ $package_sha == $QDRANT_1_17_PACKAGE_SHA256 ]] ||
    fail "qdrant 1.17.1 package archive digest mismatch: $package_sha"
  package_size=$(stat -c '%s' -- "$package")
  [[ $package_size == $QDRANT_1_17_PACKAGE_SIZE ]] ||
    fail "qdrant 1.17.1 package archive size mismatch: $package_size"

  pkginfo=$(bsdtar -xOf "$package" .PKGINFO) ||
    fail 'qdrant 1.17.1 package metadata could not be read'
  [[ $(print -r -- "$pkginfo" | grep -Fxc 'pkgname = qdrant') == 1 ]] ||
    fail 'qdrant 1.17.1 package name metadata is not exact'
  [[ $(print -r -- "$pkginfo" | grep -Fxc 'pkgver = 1.17.1-1') == 1 ]] ||
    fail 'qdrant 1.17.1 package version metadata is not exact'
  [[ $(print -r -- "$pkginfo" | grep -Fxc 'arch = x86_64') == 1 ]] ||
    fail 'qdrant 1.17.1 package architecture metadata is not exact'

  package_binary_sha=$(bsdtar -xOf "$package" usr/bin/qdrant | sha256sum)
  package_binary_sha=${package_binary_sha%% *}
  supplied_binary_sha=$(file_sha256 "$supplied_binary")
  [[ $package_binary_sha == $QDRANT_1_17_BINARY_SHA256 ]] ||
    fail "qdrant 1.17.1 package binary digest mismatch: $package_binary_sha"
  [[ $supplied_binary_sha == $package_binary_sha ]] ||
    fail 'supplied qdrant 1.17.1 binary is not byte-identical to the retained package payload'

  package_config_sha=$(bsdtar -xOf "$package" etc/qdrant/config.yaml | sha256sum)
  package_config_sha=${package_config_sha%% *}
  [[ $package_config_sha == $QDRANT_1_17_CONFIG_SHA256 ]] ||
    fail "qdrant 1.17.1 package configuration digest mismatch: $package_config_sha"

  MIGRATION_QDRANT_1_17_PACKAGE_SHA256=$package_sha
  MIGRATION_QDRANT_1_17_PACKAGE_SIZE=$package_size
  MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256=$package_binary_sha
  MIGRATION_QDRANT_1_17_CONFIG_SHA256=$package_config_sha
}

validate_exact_candidate_binary() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local binary=$1
  local version=$2
  local expected_sha256=$3
  local actual_sha256=''

  actual_sha256=$(file_sha256 "$binary")
  [[ $actual_sha256 == $expected_sha256 ]] ||
    fail "qdrant $version binary digest mismatch: $actual_sha256 (expected $expected_sha256)"
  REPLY=$actual_sha256
}

validate_port() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local label=$1
  local value=$2
  [[ $value == <-> ]] || fail "$label must be an integer from 1024 through 65535: $value"
  (( value >= 1024 && value <= 65535 )) ||
    fail "$label must be in the high, unprivileged range 1024 through 65535: $value"
}

validate_work_root() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local requested=$1
  local canonical=''

  [[ -n $requested ]] || fail '--execute requires --work-root under /tmp'
  [[ $requested == /tmp/* ]] || fail "--work-root must be an absolute path under /tmp: $requested"
  [[ $requested != *[$'\n\r\t:']* ]] ||
    fail '--work-root must not contain whitespace controls or a colon'
  canonical=$(realpath -m -- "$requested") || fail "cannot canonicalize --work-root: $requested"
  [[ $canonical == $requested && $canonical == /tmp/* ]] ||
    fail "--work-root must be a canonical path under /tmp: $requested"
  [[ ! -e $requested && ! -L $requested ]] || fail "--work-root already exists: $requested"
}

port_is_listening() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local port=$1
  local listeners=''
  listeners=$(ss -H -ltn "sport = :$port" 2>/dev/null) ||
    fail "could not inspect listener state for port $port"
  [[ -n $listeners ]]
}

validate_ports_available() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  (( MIGRATION_HTTP_PORT != MIGRATION_GRPC_PORT )) ||
    fail '--http-port and --grpc-port must be distinct'
  port_is_listening $MIGRATION_HTTP_PORT &&
    fail "--http-port is already listening: $MIGRATION_HTTP_PORT"
  port_is_listening $MIGRATION_GRPC_PORT &&
    fail "--grpc-port is already listening: $MIGRATION_GRPC_PORT"
  return 0
}

process_start_token() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local pid=$1
  local stat_line=''
  local remainder=''
  local -a fields=()
  [[ -r /proc/$pid/stat ]] || return 1
  stat_line=$(</proc/$pid/stat) || return 1
  remainder=${stat_line##*) }
  fields=(${=remainder})
  (( ${#fields} >= 20 )) || return 1
  print -r -- $fields[20]
}

process_state_token() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local pid=$1
  local stat_line=''
  local remainder=''
  local -a fields=()
  [[ -r /proc/$pid/stat ]] || return 1
  stat_line=$(</proc/$pid/stat) || return 1
  remainder=${stat_line##*) }
  fields=(${=remainder})
  (( ${#fields} >= 1 )) || return 1
  print -r -- $fields[1]
}

sample_owned_process_state() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local pid=$1
  local expected_start=$2
  local expected_exe=$3
  local stat_line=''
  local remainder=''
  local current_exe=''
  local -a fields=()

  REPLY=indeterminate
  kill -0 $pid 2>/dev/null || {
    REPLY=stopped
    return 0
  }
  { IFS= read -r stat_line < /proc/$pid/stat } 2>/dev/null || return 0
  remainder=${stat_line##*) }
  fields=(${=remainder})
  (( ${#fields} >= 20 )) || return 0
  if [[ $fields[20] != $expected_start ]]; then
    REPLY=mismatch
    return 0
  fi
  if [[ $fields[1] == Z ]]; then
    REPLY=stopped
    return 0
  fi
  current_exe=$(readlink -f -- /proc/$pid/exe 2>/dev/null) || return 0
  if [[ $current_exe != $expected_exe ]]; then
    REPLY=mismatch
    return 0
  fi
  REPLY=running
}

wait_for_owned_process_stop() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local pid=$1
  local expected_start=$2
  local expected_exe=$3
  integer max_attempts=$4
  integer attempt=0

  for (( attempt = 1; attempt <= max_attempts; attempt += 1 )); do
    sample_owned_process_state $pid "$expected_start" "$expected_exe"
    case $REPLY in
      stopped)
        return 0
        ;;
      running|indeterminate|mismatch)
        sleep 0.1
        ;;
    esac
  done
  sample_owned_process_state $pid "$expected_start" "$expected_exe"
}

capture_process_exec_identity() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local pid=$1
  local expected_exe=$2
  local current_exe=''
  local start_token=''
  integer attempt=0

  for attempt in {1..300}; do
    kill -0 $pid 2>/dev/null || return 1
    [[ -n $start_token ]] || start_token=$(process_start_token $pid 2>/dev/null) || true
    current_exe=$(readlink -f -- /proc/$pid/exe 2>/dev/null) || current_exe=''
    if [[ -n $start_token && $current_exe == $expected_exe ]]; then
      REPLY=$start_token
      return 0
    fi
    sleep 0.01
  done
  return 2
}

capture_active_process_identity() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local binary=$1
  local expected_exe=''
  integer capture_status=0

  expected_exe=$(readlink -f -- "$binary") || return 2
  capture_process_exec_identity $MIGRATION_ACTIVE_PID "$expected_exe" || capture_status=$?
  (( capture_status == 0 )) || return $capture_status
  MIGRATION_ACTIVE_START=$REPLY
  MIGRATION_ACTIVE_EXE=$expected_exe
}

require_active_process_running() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local context=$1
  integer attempt=0

  for attempt in {1..30}; do
    sample_owned_process_state $MIGRATION_ACTIVE_PID "$MIGRATION_ACTIVE_START" "$MIGRATION_ACTIVE_EXE"
    case $REPLY in
      running)
        return 0
        ;;
      stopped)
        fail "Qdrant stopped unexpectedly $context"
        ;;
      mismatch)
        fail "Qdrant ownership changed $context; refusing to signal PID $MIGRATION_ACTIVE_PID"
        ;;
      indeterminate)
        sleep 0.1
        ;;
    esac
  done
  fail "Qdrant ownership remained indeterminate $context"
}

stop_server() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local mode=${1:-strict}
  local pid=$MIGRATION_ACTIVE_PID
  integer attempt=0
  integer wait_status=0
  integer forced_kill=0
  local process_state=indeterminate

  [[ -n $pid ]] || return 0
  for attempt in {1..30}; do
    sample_owned_process_state $pid "$MIGRATION_ACTIVE_START" "$MIGRATION_ACTIVE_EXE"
    process_state=$REPLY
    [[ $process_state != indeterminate ]] && break
    sleep 0.1
  done
  case $process_state in
    running)
      kill -TERM $pid 2>/dev/null || true
      wait_for_owned_process_stop $pid "$MIGRATION_ACTIVE_START" "$MIGRATION_ACTIVE_EXE" 600
      process_state=$REPLY
      if [[ $process_state == running ]]; then
        sample_owned_process_state $pid "$MIGRATION_ACTIVE_START" "$MIGRATION_ACTIVE_EXE"
        [[ $REPLY == running ]] || process_state=$REPLY
      fi
      if [[ $process_state == running ]]; then
        print -ru2 -- "qdrant migration validation: child $pid did not stop after SIGTERM; sending SIGKILL"
        kill -KILL $pid 2>/dev/null || true
        forced_kill=1
      elif [[ $process_state == mismatch ]]; then
        fail "refusing to signal PID $pid because its ownership token or executable changed"
        return 2
      elif [[ $process_state == indeterminate ]]; then
        fail "refusing to signal PID $pid because its ownership remained indeterminate"
        return 2
      fi
      ;;
    stopped)
      ;;
    mismatch)
      fail "refusing to signal PID $pid because its ownership token or executable changed"
      return 2
      ;;
    indeterminate)
      fail "refusing to signal PID $pid because its ownership remained indeterminate"
      return 2
      ;;
  esac
  wait $pid 2>/dev/null || wait_status=$?
  MIGRATION_ACTIVE_PID=''
  MIGRATION_ACTIVE_START=''
  MIGRATION_ACTIVE_EXE=''
  MIGRATION_ACTIVE_LOG=''
  if (( forced_kill )) && [[ $mode == strict ]]; then
    fail "qdrant child $pid required SIGKILL instead of a clean stop"
    return 2
  fi
  return 0
}

cleanup() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  stop_server best_effort
  MIGRATION_API_KEY=''
  if [[ -n $MIGRATION_FINAL_MANIFEST_TMP && -f $MIGRATION_FINAL_MANIFEST_TMP ]]; then
    rm -f -- "$MIGRATION_FINAL_MANIFEST_TMP"
  fi
  MIGRATION_FINAL_MANIFEST_TMP=''
}

terminate_supervised_child() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local child_pid=$MIGRATION_SUPERVISOR_CHILD_PID
  local process_state=indeterminate
  integer attempt=0

  [[ -n $child_pid ]] || return 0
  for attempt in {1..30}; do
    sample_owned_process_state $child_pid "$MIGRATION_SUPERVISOR_CHILD_START" \
      "$MIGRATION_SUPERVISOR_CHILD_EXE"
    process_state=$REPLY
    [[ $process_state != indeterminate ]] && break
    sleep 0.1
  done
  case $process_state in
    stopped)
      return 0
      ;;
    mismatch|indeterminate)
      print -ru2 -- 'qdrant migration validation: refusing to signal the supervised payload because its identity is not exact'
      return 2
      ;;
  esac

  kill -TERM $child_pid 2>/dev/null || true
  wait_for_owned_process_stop $child_pid "$MIGRATION_SUPERVISOR_CHILD_START" \
    "$MIGRATION_SUPERVISOR_CHILD_EXE" 300
  process_state=$REPLY
  if [[ $process_state == running ]]; then
    sample_owned_process_state $child_pid "$MIGRATION_SUPERVISOR_CHILD_START" \
      "$MIGRATION_SUPERVISOR_CHILD_EXE"
    [[ $REPLY == running ]] && kill -KILL $child_pid 2>/dev/null || true
  elif [[ $process_state == mismatch || $process_state == indeterminate ]]; then
    print -ru2 -- 'qdrant migration validation: refusing a final supervised-payload signal because its identity is not exact'
    return 2
  fi
}

stop_supervised_payload() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local child_pid=$MIGRATION_SUPERVISOR_CHILD_PID
  local watcher_pid=$MIGRATION_SUPERVISOR_WATCHER_PID

  [[ -n $watcher_pid ]] && kill -TERM $watcher_pid 2>/dev/null || true
  terminate_supervised_child || true
  [[ -n $child_pid ]] && wait $child_pid 2>/dev/null || true
  [[ -n $watcher_pid ]] && wait $watcher_pid 2>/dev/null || true
  MIGRATION_SUPERVISOR_CHILD_PID=''
  MIGRATION_SUPERVISOR_CHILD_START=''
  MIGRATION_SUPERVISOR_CHILD_EXE=''
  MIGRATION_SUPERVISOR_WATCHER_PID=''
}

supervise_isolated_payload() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  integer child_status=0
  integer receipt_attempt=0

  (( $# > 0 )) || fail 'unit supervisor requires an isolated payload command'
  MIGRATION_SUPERVISOR_MODE=1
  if [[ -n ${QDRANT_MIGRATION_CGROUP_RECEIPT:-} ]]; then
    [[ $QDRANT_MIGRATION_CGROUP_RECEIPT == /tmp/* &&
      -d ${QDRANT_MIGRATION_CGROUP_RECEIPT:h} &&
      ! -L ${QDRANT_MIGRATION_CGROUP_RECEIPT:h} &&
      ! -e $QDRANT_MIGRATION_CGROUP_RECEIPT ]] ||
      fail 'unit supervisor cgroup receipt path is unsafe'
    print -r -- "$(</proc/self/cgroup)" > "$QDRANT_MIGRATION_CGROUP_RECEIPT"
    chmod 600 -- "$QDRANT_MIGRATION_CGROUP_RECEIPT"
    for receipt_attempt in {1..100}; do
      [[ ! -e $QDRANT_MIGRATION_CGROUP_RECEIPT ]] && break
      sleep 0.05
    done
    [[ ! -e $QDRANT_MIGRATION_CGROUP_RECEIPT ]] ||
      fail 'outer process did not acknowledge the exact cgroup receipt'
  fi
  "$@" </dev/null &
  MIGRATION_SUPERVISOR_CHILD_PID=$!
  MIGRATION_SUPERVISOR_CHILD_EXE=/usr/bin/bwrap
  capture_process_exec_identity $MIGRATION_SUPERVISOR_CHILD_PID \
    "$MIGRATION_SUPERVISOR_CHILD_EXE" || {
    stop_supervised_payload
    fail 'unit supervisor could not establish its child ownership token'
  }
  MIGRATION_SUPERVISOR_CHILD_START=$REPLY
  {
    emulate -L zsh
    setopt NO_UNSET PIPE_FAIL
    IFS= read -r _ || true
    terminate_supervised_child || true
  } &
  MIGRATION_SUPERVISOR_WATCHER_PID=$!

  if wait $MIGRATION_SUPERVISOR_CHILD_PID; then
    child_status=0
  else
    child_status=$?
  fi
  kill -TERM $MIGRATION_SUPERVISOR_WATCHER_PID 2>/dev/null || true
  wait $MIGRATION_SUPERVISOR_WATCHER_PID 2>/dev/null || true
  MIGRATION_SUPERVISOR_CHILD_PID=''
  MIGRATION_SUPERVISOR_CHILD_START=''
  MIGRATION_SUPERVISOR_CHILD_EXE=''
  MIGRATION_SUPERVISOR_WATCHER_PID=''
  return $child_status
}

close_transient_keepalive() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  [[ -n $MIGRATION_TRANSIENT_KEEPALIVE_FD ]] || return 0
  exec {MIGRATION_TRANSIENT_KEEPALIVE_FD}>&-
  MIGRATION_TRANSIENT_KEEPALIVE_FD=''
}

transient_collection_receipt_is_exact() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local unit_name=$1
  local cgroup=$2
  local expected_wait_status=$3

  [[ $MIGRATION_TRANSIENT_WAIT_COMPLETED == 1 ]] || return 1
  [[ $MIGRATION_TRANSIENT_WAIT_UNIT == $unit_name ]] || return 1
  [[ $expected_wait_status == <-> &&
    $MIGRATION_TRANSIENT_WAIT_STATUS == $expected_wait_status ]] || return 1
  [[ -z $MIGRATION_TRANSIENT_CLIENT_PID && -z $MIGRATION_TRANSIENT_CLIENT_START &&
    -z $MIGRATION_TRANSIENT_CLIENT_EXE ]] || return 1
  [[ -n $unit_name && $cgroup == /*/$unit_name ]] || return 1
  [[ ! -e /sys/fs/cgroup$cgroup ]]
}

verify_transient_unit_collected() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local unit_name=$1
  integer attempt=0
  [[ -n $MIGRATION_TRANSIENT_CGROUP ]] ||
    fail "transient isolation cgroup identity was not captured: $unit_name"
  for attempt in {1..100}; do
    if transient_collection_receipt_is_exact "$unit_name" "$MIGRATION_TRANSIENT_CGROUP" 0; then
      return 0
    fi
    sleep 0.05
  done
  fail "transient isolation wait/reap receipt or cgroup collection was incomplete: $unit_name"
}

stop_transient_unit() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local mode=${1:-strict}
  local unit_name=$MIGRATION_TRANSIENT_UNIT
  local client_pid=$MIGRATION_TRANSIENT_CLIENT_PID
  local client_start=$MIGRATION_TRANSIENT_CLIENT_START
  integer attempt=0
  integer wait_status=0
  [[ -n $unit_name ]] || return 0
  close_transient_keepalive
  if [[ -n $client_pid ]]; then
    for attempt in {1..400}; do
      transient_client_is_owned || break
      sleep 0.1
    done
    if transient_client_is_owned; then
      if [[ $mode == strict ]]; then
        fail "transient isolation client did not finish after keepalive closure: $unit_name"
        return 2
      fi
      print -ru2 -- "qdrant migration validation: transient client cleanup remained incomplete: $unit_name"
      return 0
    fi
    if kill -0 $client_pid 2>/dev/null &&
      [[ $(process_start_token $client_pid 2>/dev/null) != $client_start ]]; then
      if [[ $mode == strict ]]; then
        fail "refusing to reap a transient client whose ownership token changed: $unit_name"
        return 2
      fi
      print -ru2 -- "qdrant migration validation: transient client ownership changed before cleanup: $unit_name"
      return 0
    fi
    wait $client_pid 2>/dev/null || wait_status=$?
  fi
  MIGRATION_TRANSIENT_WAIT_COMPLETED=1
  MIGRATION_TRANSIENT_WAIT_UNIT=$unit_name
  MIGRATION_TRANSIENT_WAIT_STATUS=$wait_status
  MIGRATION_TRANSIENT_UNIT=''
  MIGRATION_TRANSIENT_CLIENT_PID=''
  MIGRATION_TRANSIENT_CLIENT_START=''
  MIGRATION_TRANSIENT_CLIENT_EXE=''
  return 0
}

transient_client_is_owned() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  [[ -n $MIGRATION_TRANSIENT_CLIENT_PID && -n $MIGRATION_TRANSIENT_CLIENT_START &&
    -n $MIGRATION_TRANSIENT_CLIENT_EXE ]] || return 1
  sample_owned_process_state $MIGRATION_TRANSIENT_CLIENT_PID \
    "$MIGRATION_TRANSIENT_CLIENT_START" "$MIGRATION_TRANSIENT_CLIENT_EXE"
  [[ $REPLY == running ]]
}

validate_receipt_destination() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local requested=$1
  local canonical=''
  local parent=''
  [[ -n $requested && $requested == /tmp/* ]] ||
    fail '--receipt must be an absolute path under /tmp'
  canonical=$(realpath -m -- "$requested") || fail "cannot canonicalize --receipt: $requested"
  [[ $canonical == $requested ]] || fail "--receipt must be canonical: $requested"
  [[ ! -e $requested && ! -L $requested ]] || fail "--receipt already exists: $requested"
  parent=${requested:h}
  [[ -d $parent && ! -L $parent ]] || fail "--receipt parent is not a real directory: $parent"
}

validate_interrupt_receipt() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local receipt=$1
  local expected_signal=$2
  local expected_status=$3
  local fixture_spec_sha256=''
  local target_executable=''
  local target_executable_sha256=''
  [[ -f $receipt && ! -L $receipt ]] ||
    fail "$expected_signal interrupt receipt is not a regular non-symlink file"
  fixture_spec_sha256=$(text_sha256 "$(fixture_spec_json)")
  target_executable=$(readlink -f -- /proc/$$/exe) ||
    fail 'could not resolve the current validation executable'
  target_executable_sha256=$(file_sha256 "$target_executable")
  jq -e --arg schema "$INTERRUPT_RECEIPT_SCHEMA" \
    --arg signal "$expected_signal" --argjson status "$expected_status" \
    --arg tool_sha256 "$MIGRATION_TOOL_SHA256" \
    --arg target_executable_sha256 "$target_executable_sha256" \
    --arg fixture_spec_sha256 "$fixture_spec_sha256" \
    --arg package_archive_sha256 "$MIGRATION_QDRANT_1_17_PACKAGE_SHA256" \
    --arg q17 "$MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256" \
    --arg q18 "$MIGRATION_QDRANT_1_18_BINARY_SHA256" \
    --arg q19 "$MIGRATION_QDRANT_1_19_BINARY_SHA256" '
      .schema == $schema
      and .disposition == "accepted"
      and .signal == $signal
      and .conventional_exit_status == $status
      and .target.kind == "outer-validation-process"
      and .target.tool_sha256 == $tool_sha256
      and (.target.target_identity_sha256 | test("^[0-9a-f]{64}$"))
      and .target.target_executable_sha256 == $target_executable_sha256
      and .inputs.fixture_spec_sha256 == $fixture_spec_sha256
      and .inputs.package_archive_sha256 == $package_archive_sha256
      and .inputs.binary_sha256 == [$q17,$q18,$q19]
      and .pre_interrupt.synchronized_ready_marker
      and (.pre_interrupt.readiness_marker_sha256 | test("^[0-9a-f]{64}$"))
      and .pre_interrupt.owned_process_observed
      and .pre_interrupt.isolated_http_listener_observed
      and .pre_interrupt.isolated_grpc_listener_observed
      and .pre_interrupt.isolated_network_namespace_observed
      and .candidate_absent
      and .accepted_manifest_absent
      and .cleanup.status == "passed"
      and .cleanup.failure == "none"
      and .cleanup.owned_processes_absent
      and .cleanup.owned_listeners_absent
      and .cleanup.owned_unit_absent
      and .cleanup.owned_cgroup_absent
      and .cleanup.collection_wait_completed
      and .cleanup.collection_wait_status == 143
      and .cleanup.collection_wait_status_expected == 143
      and .cleanup.collection_wait_unit_matched
      and .cleanup.collection_client_reaped
      and .cleanup.collection_cgroup_identity_matched
      and .cleanup.collection_receipt_exact
      and all(.. | strings;
        (contains("/home/") | not)
        and (contains("/root/") | not)
        and (contains("/etc/qdrant") | not)
        and (contains("/var/lib/qdrant") | not)
        and (test("user-[0-9]+|@[0-9]+\\.service|net:\\[[0-9]+\\]|qdrant-migration-[0-9]+") | not)
        and (contains("/tmp/") | not))
    ' "$receipt" >/dev/null || fail "$expected_signal interrupt receipt failed its binding and cleanup gate"
  REPLY=$(file_sha256 "$receipt")
}

capture_transient_cgroup() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local unit_name=$1
  local receipt=$MIGRATION_WORK_ROOT/control/unit-cgroup
  local cgroup=''
  integer attempt=0
  for attempt in {1..100}; do
    if [[ -f $receipt && ! -L $receipt && $(stat -c '%a' -- "$receipt") == 600 ]]; then
      cgroup=$(<"$receipt")
      cgroup=${cgroup#0::}
    fi
    if [[ $cgroup == /* && $cgroup == */$unit_name ]]; then
      MIGRATION_TRANSIENT_CGROUP=$cgroup
      rm -f -- "$receipt"
      return 0
    fi
    sleep 0.05
  done
  fail 'could not capture the exact transient-unit cgroup identity'
}

validate_interrupt_readiness_marker() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local marker=$1
  [[ -f $marker && ! -L $marker && $(stat -c '%a' -- "$marker") == 600 ]] ||
    fail 'interrupt readiness marker is not an exact mode-0600 regular file'
  jq -e --arg schema "$INTERRUPT_READINESS_SCHEMA" \
    --argjson http_port "$MIGRATION_HTTP_PORT" \
    --argjson grpc_port "$MIGRATION_GRPC_PORT" \
    --arg binary_sha256 "$MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256" '
      .schema == $schema
      and .ready
      and .owned_process_observed
      and .isolated_http_listener_observed
      and .isolated_grpc_listener_observed
      and .isolated_network_namespace_observed
      and (.process_identity_sha256 | test("^[0-9a-f]{64}$"))
      and (.network_namespace_sha256 | test("^[0-9a-f]{64}$"))
      and .binary_sha256 == $binary_sha256
      and .ports == {http:$http_port,grpc:$grpc_port}
    ' "$marker" >/dev/null || fail 'interrupt readiness marker is incomplete or incoherent'
  MIGRATION_PROBE_READINESS_MARKER=$marker
  MIGRATION_PROBE_READINESS_SHA256=$(file_sha256 "$marker")
  MIGRATION_PROBE_OWNED_PROCESS_OBSERVED=1
  MIGRATION_PROBE_HTTP_LISTENER_OBSERVED=1
  MIGRATION_PROBE_GRPC_LISTENER_OBSERVED=1
  MIGRATION_PROBE_ISOLATED_NETNS_OBSERVED=1
}

await_interrupt_probe_readiness() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local marker=$1
  integer attempt=0
  for attempt in {1..3000}; do
    if [[ -e $marker || -L $marker ]]; then
      validate_interrupt_readiness_marker "$marker"
      transient_client_is_owned ||
        fail 'transient client stopped before interrupt readiness was consumed'
      return 0
    fi
    transient_client_is_owned ||
      fail 'transient client stopped before publishing interrupt readiness'
    sleep 0.1
  done
  fail 'timed out waiting for synchronized interrupt readiness'
}

publish_interrupt_probe_readiness_and_wait() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL NO_CLOBBER
  local marker=${QDRANT_MIGRATION_INTERRUPT_READY_MARKER:-}
  local partial=''
  local process_identity_sha256=''
  local network_namespace=''
  local network_namespace_sha256=''
  local binary_sha256=''

  [[ ${QDRANT_MIGRATION_INTERRUPT_PROBE:-} == 1 ]] || return 0
  [[ -n $marker && $marker == "$MIGRATION_WORK_ROOT/control/interrupt-ready.json" ]] ||
    fail 'interrupt readiness marker destination is not the exact private control path'
  [[ -d ${marker:h} && ! -L ${marker:h} && $(stat -c '%a' -- "${marker:h}") == 700 ]] ||
    fail 'interrupt readiness control directory is unsafe'
  [[ ! -e $marker && ! -L $marker ]] || fail 'interrupt readiness marker already exists'
  require_active_process_running 'before publishing interrupt readiness'
  port_is_listening "$MIGRATION_HTTP_PORT" ||
    fail 'interrupt probe HTTP listener was not active in the isolated namespace'
  port_is_listening "$MIGRATION_GRPC_PORT" ||
    fail 'interrupt probe gRPC listener was not active in the isolated namespace'
  process_identity_sha256=$(text_sha256 \
    "$MIGRATION_ACTIVE_PID:$MIGRATION_ACTIVE_START:$MIGRATION_ACTIVE_EXE")
  network_namespace=$(readlink -- /proc/self/ns/net) ||
    fail 'interrupt probe could not capture its isolated network namespace'
  network_namespace_sha256=$(text_sha256 "$network_namespace")
  binary_sha256=$(file_sha256 "$MIGRATION_ACTIVE_EXE")
  [[ $binary_sha256 == $MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256 ]] ||
    fail 'interrupt readiness process is not the exact retained 1.17.1 binary'
  partial=$marker.partial.$$
  jq -nc --arg schema "$INTERRUPT_READINESS_SCHEMA" \
    --arg process_identity_sha256 "$process_identity_sha256" \
    --arg network_namespace_sha256 "$network_namespace_sha256" \
    --arg binary_sha256 "$binary_sha256" \
    --argjson http_port "$MIGRATION_HTTP_PORT" \
    --argjson grpc_port "$MIGRATION_GRPC_PORT" '
      {schema:$schema,ready:true,owned_process_observed:true,
        isolated_http_listener_observed:true,isolated_grpc_listener_observed:true,
        isolated_network_namespace_observed:true,
        process_identity_sha256:$process_identity_sha256,
        network_namespace_sha256:$network_namespace_sha256,
        binary_sha256:$binary_sha256,ports:{http:$http_port,grpc:$grpc_port}}
    ' > "$partial"
  chmod 600 -- "$partial"
  ln -- "$partial" "$marker" || {
    rm -f -- "$partial"
    fail 'interrupt readiness marker destination changed before publication'
  }
  rm -f -- "$partial"

  while true; do
    require_active_process_running 'while awaiting the synchronized interrupt'
    port_is_listening "$MIGRATION_HTTP_PORT" ||
      fail 'interrupt probe HTTP listener stopped before interruption'
    port_is_listening "$MIGRATION_GRPC_PORT" ||
      fail 'interrupt probe gRPC listener stopped before interruption'
    sleep 0.1
  done
}

schedule_probe_interrupt() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local signal=$1
  local target_pid=$$
  local target_start=''
  local target_exe=''

  target_start=$(process_start_token $target_pid) ||
    fail 'could not capture the interrupt target start token'
  target_exe=$(readlink -f -- /proc/$target_pid/exe) ||
    fail 'could not capture the interrupt target executable'
  MIGRATION_PROBE_TARGET_EXE_SHA256=$(file_sha256 "$target_exe")
  MIGRATION_PROBE_TARGET_IDENTITY_SHA256=$(text_sha256 \
    "$target_pid:$target_start:$target_exe:$MIGRATION_TOOL_SHA256:$signal")
  (
    emulate -L zsh
    setopt NO_UNSET PIPE_FAIL
    close_transient_keepalive
    sleep 0.1
    sample_owned_process_state $target_pid "$target_start" "$target_exe"
    [[ $REPLY == running ]] || exit 2
    kill -$signal $target_pid
  ) &
  MIGRATION_PROBE_SENDER_PID=$!
}

interruption_cleanup_observation() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local unit_name=$1
  local cgroup=$2
  local expected_wait_status=$3
  integer owned_processes_absent=0
  integer owned_listeners_absent=0
  integer owned_unit_absent=0
  integer owned_cgroup_absent=0
  integer candidate_absent=0
  integer accepted_manifest_absent=0
  integer collection_wait_completed=0
  integer collection_wait_status=-1
  integer collection_wait_unit_matched=0
  integer collection_client_reaped=0
  integer collection_cgroup_identity_matched=0
  integer collection_receipt_exact=0
  integer attempt=0

  [[ $MIGRATION_TRANSIENT_WAIT_COMPLETED == 1 ]] && collection_wait_completed=1
  [[ $MIGRATION_TRANSIENT_WAIT_STATUS == <-> ]] &&
    collection_wait_status=$MIGRATION_TRANSIENT_WAIT_STATUS
  [[ $MIGRATION_TRANSIENT_WAIT_UNIT == $unit_name ]] && collection_wait_unit_matched=1
  [[ -z $MIGRATION_TRANSIENT_CLIENT_PID && -z $MIGRATION_TRANSIENT_CLIENT_START &&
    -z $MIGRATION_TRANSIENT_CLIENT_EXE ]] && collection_client_reaped=1
  [[ -n $unit_name && $cgroup == /*/$unit_name ]] && collection_cgroup_identity_matched=1

  for attempt in {1..100}; do
    [[ -n $cgroup && ! -e /sys/fs/cgroup$cgroup ]] && owned_cgroup_absent=1
    if (( owned_cgroup_absent )) &&
      transient_collection_receipt_is_exact "$unit_name" "$cgroup" "$expected_wait_status"; then
      owned_unit_absent=1
      collection_receipt_exact=1
      break
    fi
    sleep 0.05
  done
  [[ -z $MIGRATION_TRANSIENT_CLIENT_PID && -z $MIGRATION_TRANSIENT_CLIENT_START &&
    -z $MIGRATION_TRANSIENT_CLIENT_EXE && $owned_cgroup_absent == 1 ]] && owned_processes_absent=1
  if (( owned_processes_absent && owned_cgroup_absent &&
    MIGRATION_PROBE_HTTP_LISTENER_OBSERVED && MIGRATION_PROBE_GRPC_LISTENER_OBSERVED &&
    MIGRATION_PROBE_ISOLATED_NETNS_OBSERVED )); then
    owned_listeners_absent=1
  fi
  [[ ! -e $MIGRATION_WORK_ROOT/evidence/manifest.runtime-validated.json ]] && candidate_absent=1
  [[ ! -e $MIGRATION_WORK_ROOT/evidence/manifest.json ]] && accepted_manifest_absent=1
  jq -nc \
    --argjson owned_processes_absent $owned_processes_absent \
    --argjson owned_listeners_absent $owned_listeners_absent \
    --argjson owned_unit_absent $owned_unit_absent \
    --argjson owned_cgroup_absent $owned_cgroup_absent \
    --argjson candidate_absent $candidate_absent \
    --argjson accepted_manifest_absent $accepted_manifest_absent \
    --argjson collection_wait_completed $collection_wait_completed \
    --argjson collection_wait_status $collection_wait_status \
    --argjson collection_wait_status_expected $expected_wait_status \
    --argjson collection_wait_unit_matched $collection_wait_unit_matched \
    --argjson collection_client_reaped $collection_client_reaped \
    --argjson collection_cgroup_identity_matched $collection_cgroup_identity_matched \
    --argjson collection_receipt_exact $collection_receipt_exact \
    '{owned_processes_absent:($owned_processes_absent == 1),
      owned_listeners_absent:($owned_listeners_absent == 1),
      owned_unit_absent:($owned_unit_absent == 1),owned_cgroup_absent:($owned_cgroup_absent == 1),
      candidate_absent:($candidate_absent == 1),accepted_manifest_absent:($accepted_manifest_absent == 1),
      collection_wait_completed:($collection_wait_completed == 1),
      collection_wait_status:$collection_wait_status,
      collection_wait_status_expected:$collection_wait_status_expected,
      collection_wait_unit_matched:($collection_wait_unit_matched == 1),
      collection_client_reaped:($collection_client_reaped == 1),
      collection_cgroup_identity_matched:($collection_cgroup_identity_matched == 1),
      collection_receipt_exact:($collection_receipt_exact == 1)}'
}

write_interruption_receipt() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL NO_CLOBBER
  local signal=$1
  local conventional_status=$2
  local disposition=$3
  local observation=$4
  local cleanup_failure=$5
  local fixture_spec_sha256=''
  local receipt_json=''
  local partial=$MIGRATION_PROBE_RECEIPT.partial.$$
  fixture_spec_sha256=$(text_sha256 "$(fixture_spec_json)")
  receipt_json=$(jq -nc \
    --arg schema "$INTERRUPT_RECEIPT_SCHEMA" --arg disposition "$disposition" \
    --arg signal "$signal" --argjson conventional_status "$conventional_status" \
    --arg target_identity_sha256 "$MIGRATION_PROBE_TARGET_IDENTITY_SHA256" \
    --arg target_executable_sha256 "$MIGRATION_PROBE_TARGET_EXE_SHA256" \
    --arg tool_sha256 "$MIGRATION_TOOL_SHA256" \
    --arg fixture_spec_sha256 "$fixture_spec_sha256" \
    --arg package_archive_sha256 "$MIGRATION_QDRANT_1_17_PACKAGE_SHA256" \
    --arg q17 "$MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256" \
    --arg q18 "$MIGRATION_QDRANT_1_18_BINARY_SHA256" --arg q19 "$MIGRATION_QDRANT_1_19_BINARY_SHA256" \
    --arg readiness_marker_sha256 "$MIGRATION_PROBE_READINESS_SHA256" \
    --argjson owned_process_observed "$MIGRATION_PROBE_OWNED_PROCESS_OBSERVED" \
    --argjson http_listener_observed "$MIGRATION_PROBE_HTTP_LISTENER_OBSERVED" \
    --argjson grpc_listener_observed "$MIGRATION_PROBE_GRPC_LISTENER_OBSERVED" \
    --argjson isolated_netns_observed "$MIGRATION_PROBE_ISOLATED_NETNS_OBSERVED" \
    --arg cleanup_failure "$cleanup_failure" --argjson observation "$observation" '
      {schema:$schema,disposition:$disposition,signal:$signal,
        conventional_exit_status:$conventional_status,
        target:{kind:"outer-validation-process",target_identity_sha256:$target_identity_sha256,
          target_executable_sha256:$target_executable_sha256,tool_sha256:$tool_sha256},
        inputs:{fixture_spec:"qdrant-migration-fixture/v2",fixture_spec_sha256:$fixture_spec_sha256,
          package_archive_sha256:$package_archive_sha256,binary_sha256:[$q17,$q18,$q19]},
        pre_interrupt:{synchronized_ready_marker:
          ($owned_process_observed == 1 and $http_listener_observed == 1
            and $grpc_listener_observed == 1 and $isolated_netns_observed == 1
            and ($readiness_marker_sha256 | test("^[0-9a-f]{64}$"))),
          readiness_marker_sha256:$readiness_marker_sha256,
          owned_process_observed:($owned_process_observed == 1),
          isolated_http_listener_observed:($http_listener_observed == 1),
          isolated_grpc_listener_observed:($grpc_listener_observed == 1),
          isolated_network_namespace_observed:($isolated_netns_observed == 1)},
        candidate_absent:$observation.candidate_absent,
        accepted_manifest_absent:$observation.accepted_manifest_absent,
        cleanup:{status:(if $disposition == "accepted" then "passed" else "failed" end),
          failure:$cleanup_failure,owned_processes_absent:$observation.owned_processes_absent,
          owned_listeners_absent:$observation.owned_listeners_absent,
          owned_unit_absent:$observation.owned_unit_absent,
          owned_cgroup_absent:$observation.owned_cgroup_absent,
          collection_wait_completed:$observation.collection_wait_completed,
          collection_wait_status:$observation.collection_wait_status,
          collection_wait_status_expected:$observation.collection_wait_status_expected,
          collection_wait_unit_matched:$observation.collection_wait_unit_matched,
          collection_client_reaped:$observation.collection_client_reaped,
          collection_cgroup_identity_matched:$observation.collection_cgroup_identity_matched,
          collection_receipt_exact:$observation.collection_receipt_exact}}')
  print -r -- "$receipt_json" > "$partial"
  chmod 600 -- "$partial"
  ln -- "$partial" "$MIGRATION_PROBE_RECEIPT" || {
    rm -f -- "$partial"
    fail 'interrupt receipt destination changed before publication'
  }
  rm -f -- "$partial"
}

handle_interruption() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local signal=$1
  integer conventional_status=$2
  local unit_name=$MIGRATION_TRANSIENT_UNIT
  local cgroup=$MIGRATION_TRANSIENT_CGROUP
  local observation=''
  local disposition=rejected
  local cleanup_failure=none
  integer cleanup_status=0

  MIGRATION_HANDLING_SIGNAL=1
  if stop_transient_unit strict; then
    cleanup_status=0
  else
    cleanup_status=$?
    cleanup_failure=transient_cleanup_failed
  fi
  cleanup
  if [[ -n $MIGRATION_PROBE_SENDER_PID ]]; then
    wait $MIGRATION_PROBE_SENDER_PID 2>/dev/null || true
    MIGRATION_PROBE_SENDER_PID=''
  fi
  observation=$(interruption_cleanup_observation "$unit_name" "$cgroup" \
    $SUPERVISED_INTERRUPT_WAIT_STATUS)
  if (( cleanup_status == 0 && MIGRATION_PROBE_OWNED_PROCESS_OBSERVED &&
    MIGRATION_PROBE_HTTP_LISTENER_OBSERVED && MIGRATION_PROBE_GRPC_LISTENER_OBSERVED &&
    MIGRATION_PROBE_ISOLATED_NETNS_OBSERVED )) &&
    (( ${#MIGRATION_PROBE_READINESS_SHA256} == 64 )) &&
    [[ -z ${MIGRATION_PROBE_READINESS_SHA256//[0-9a-f]/} ]] &&
    print -r -- "$observation" | jq -e \
    '.owned_processes_absent and .owned_listeners_absent and .owned_unit_absent
      and .owned_cgroup_absent and .candidate_absent and .accepted_manifest_absent
      and .collection_wait_completed and .collection_wait_status == 143
      and .collection_wait_status_expected == 143 and .collection_wait_unit_matched
      and .collection_client_reaped and .collection_cgroup_identity_matched
      and .collection_receipt_exact' >/dev/null; then
    disposition=accepted
  elif [[ $cleanup_failure == none ]]; then
    cleanup_failure=residue_or_candidate_detected
  fi
  if [[ -n $MIGRATION_PROBE_RECEIPT ]]; then
    write_interruption_receipt "$signal" $conventional_status "$disposition" \
      "$observation" "$cleanup_failure" || exit 125
  fi
  [[ $disposition == accepted ]] || exit 125
  exit $conventional_status
}

TRAPEXIT() {
  (( MIGRATION_HANDLING_SIGNAL )) && return
  if (( MIGRATION_SUPERVISOR_MODE )); then
    stop_supervised_payload
    return
  fi
  stop_transient_unit best_effort
  cleanup
}

TRAPINT() {
  if (( MIGRATION_SUPERVISOR_MODE )); then
    stop_supervised_payload
    exit 130
  fi
  handle_interruption INT 130
}

TRAPTERM() {
  if (( MIGRATION_SUPERVISOR_MODE )); then
    stop_supervised_payload
    exit 143
  fi
  handle_interruption TERM 143
}

TRAPHUP() {
  if (( MIGRATION_SUPERVISOR_MODE )); then
    stop_supervised_payload
    exit 129
  fi
  handle_interruption HUP 129
}

write_config() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local instance=$1
  local config=$instance/qdrant.yaml
  mkdir -p -- "$instance/storage" "$instance/snapshots"
  print -r -- "storage:
  storage_path: $instance/storage
  snapshots_path: $instance/snapshots
  collection:
    strict_mode:
      enabled: true
      max_query_limit: $FIXTURE_MAX_QUERY_LIMIT
      max_timeout: 120
      unindexed_filtering_retrieve: true
      unindexed_filtering_update: true
service:
  host: 127.0.0.1
  http_port: $MIGRATION_HTTP_PORT
  grpc_port: $MIGRATION_GRPC_PORT
  enable_cors: false
cluster:
  enabled: false
telemetry_disabled: true" >| "$config"
  chmod 600 -- "$config"
  print -r -- "$config"
}

authenticated_curl() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local curl_config="silent
show-error
fail-with-body
connect-timeout = 2
max-time = 120
header = \"api-key: $MIGRATION_API_KEY\""
  curl -q --config - "$@" <<< "$curl_config"
}

wait_for_ready() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local auth_code=''
  local unauth_code=''
  integer attempt=0
  integer child_status=0

  for attempt in {1..300}; do
    sample_owned_process_state $MIGRATION_ACTIVE_PID "$MIGRATION_ACTIVE_START" "$MIGRATION_ACTIVE_EXE"
    if [[ $REPLY == mismatch ]]; then
      fail "qdrant child ownership changed before readiness; refusing to wait or signal PID $MIGRATION_ACTIVE_PID"
    elif [[ $REPLY == stopped ]]; then
      wait $MIGRATION_ACTIVE_PID 2>/dev/null || child_status=$?
      print -ru2 -- "qdrant migration validation: qdrant exited before readiness (status $child_status); log: $MIGRATION_ACTIVE_LOG"
      [[ -f $MIGRATION_ACTIVE_LOG ]] && tail -n 40 -- "$MIGRATION_ACTIVE_LOG" >&2
      MIGRATION_ACTIVE_PID=''
      MIGRATION_ACTIVE_START=''
      MIGRATION_ACTIVE_EXE=''
      MIGRATION_ACTIVE_LOG=''
      return 2
    elif [[ $REPLY == indeterminate ]]; then
      sleep 0.1
      continue
    fi
    unauth_code=$(curl -q --silent --output /dev/null --write-out '%{http_code}' \
      --connect-timeout 1 --max-time 2 "$MIGRATION_BASE_URL/collections" 2>/dev/null) || unauth_code='000'
    auth_code=$(authenticated_curl --output /dev/null \
      --write-out '%{http_code}' "$MIGRATION_BASE_URL/collections" 2>/dev/null) || auth_code='000'
    if [[ $auth_code == 200 && ( $unauth_code == 401 || $unauth_code == 403 ) ]]; then
      port_is_listening $MIGRATION_GRPC_PORT ||
        fail "qdrant became HTTP-ready without listening on gRPC port $MIGRATION_GRPC_PORT"
      return 0
    fi
    sleep 0.1
  done
  fail "qdrant did not become authenticated-only on $MIGRATION_BASE_URL; log: $MIGRATION_ACTIVE_LOG"
}

start_server() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local binary=$1
  local expected_version=$2
  local instance=$3
  local config=$4
  integer capture_status=0
  shift 4

  [[ -z $MIGRATION_ACTIVE_PID ]] || fail 'internal error: a qdrant child is already registered'
  validate_ports_available
  MIGRATION_ACTIVE_LOG=$instance/qdrant-$expected_version.log
  (
    cd -- "$instance"
    export QDRANT__SERVICE__API_KEY=$MIGRATION_API_KEY
    exec setpriv --no-new-privs --bounding-set=-all --inh-caps=-all \
      --ambient-caps=-all -- "$binary" --config-path "$config" \
      --disable-telemetry "$@"
  ) >| "$MIGRATION_ACTIVE_LOG" 2>&1 &
  MIGRATION_ACTIVE_PID=$!
  capture_active_process_identity "$binary" || capture_status=$?
  if (( capture_status != 0 )); then
    wait $MIGRATION_ACTIVE_PID 2>/dev/null || true
    MIGRATION_ACTIVE_PID=''
    MIGRATION_ACTIVE_START=''
    MIGRATION_ACTIVE_EXE=''
    if (( capture_status == 1 )); then
      fail "qdrant $expected_version exited before its exact process identity was captured"
      return 2
    fi
    fail "qdrant $expected_version process identity remained indeterminate"
    return 2
  fi
  wait_for_ready
}

api_json() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local method=$1
  local endpoint=$2
  local body=${3-}
  local response=''
  local -a args=(--request "$method" --header 'Content-Type: application/json')
  [[ -n $body ]] && args+=(--data-binary "$body")
  if ! response=$(authenticated_curl $args "$MIGRATION_BASE_URL$endpoint"); then
    print -ru2 -- "qdrant migration validation: REST $method $endpoint failed"
    [[ -n $response ]] && print -ru2 -- "$response"
    return 2
  fi
  if ! print -r -- "$response" | jq -e '.status == "ok"' >/dev/null; then
    print -ru2 -- "qdrant migration validation: REST $method $endpoint returned a non-ok response"
    print -ru2 -- "$response"
    return 2
  fi
  print -r -- "$response"
}

verify_authenticated_readiness() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local context=$1
  local response=''
  response=$(api_json GET '/collections')
  print -r -- "$response" | jq -e '
    .status == "ok" and (.result.collections | type) == "array"' >/dev/null ||
    fail "authenticated readiness failed $context"
}

download_snapshot() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local endpoint=$1
  local destination=$2
  local expected_checksum=$3
  local actual_checksum=''
  authenticated_curl --fail-with-body --output "$destination" "$MIGRATION_BASE_URL$endpoint"
  [[ -s $destination ]] || fail "downloaded snapshot is empty: $destination"
  actual_checksum=$(sha256sum -- "$destination")
  actual_checksum=${actual_checksum%% *}
  [[ $actual_checksum == $expected_checksum ]] ||
    fail "snapshot checksum mismatch for $destination: expected $expected_checksum, got $actual_checksum"
}

api_json_file() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local method=$1
  local endpoint=$2
  local request_file=$3
  local response=''
  [[ -s $request_file ]] || fail "JSON request file is missing or empty: $request_file"
  response=$(authenticated_curl --request "$method" \
    --header 'Content-Type: application/json' --data-binary "@$request_file" \
    "$MIGRATION_BASE_URL$endpoint") || {
      print -ru2 -- "qdrant migration validation: REST $method $endpoint failed"
      return 2
    }
  print -r -- "$response" | jq -e '.status == "ok"' >/dev/null || {
    print -ru2 -- "qdrant migration validation: REST $method $endpoint returned a non-ok response"
    print -ru2 -- "$response"
    return 2
  }
  print -r -- "$response"
}

attempt_json_file() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local method=$1
  local endpoint=$2
  local request_file=$3
  local response_file=$MIGRATION_WORK_ROOT/.last-response
  integer curl_status=0
  MIGRATION_LAST_HTTP_CODE=''
  MIGRATION_LAST_HTTP_BODY=''
  MIGRATION_LAST_HTTP_CODE=$(authenticated_curl --request "$method" \
    --header 'Content-Type: application/json' --data-binary "@$request_file" \
    --output "$response_file" --write-out '%{http_code}' \
    "$MIGRATION_BASE_URL$endpoint") || curl_status=$?
  [[ -f $response_file ]] && MIGRATION_LAST_HTTP_BODY=$(<"$response_file")
  : >| "$response_file"
  (( curl_status == 0 )) || return $curl_status
}

upload_snapshot_attempt() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local snapshot=$1
  local collection=$2
  local checksum=$3
  local response_file=$MIGRATION_WORK_ROOT/.last-response
  integer curl_status=0
  MIGRATION_LAST_HTTP_CODE=''
  MIGRATION_LAST_HTTP_BODY=''
  MIGRATION_LAST_HTTP_CODE=$(authenticated_curl --request POST \
    --form "snapshot=@$snapshot;type=application/octet-stream" \
    --output "$response_file" --write-out '%{http_code}' \
    "$MIGRATION_BASE_URL/collections/$collection/snapshots/upload?wait=true&checksum=$checksum") ||
    curl_status=$?
  [[ -f $response_file ]] && MIGRATION_LAST_HTTP_BODY=$(<"$response_file")
  : >| "$response_file"
  (( curl_status == 0 )) || return $curl_status
}

fixture_collection_body() {
  print -r -- '{"vectors":{"dense":{"size":4,"distance":"Cosine"}},"sparse_vectors":{"sparse":{}}}'
}

fixture_point_id() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local ordinal=$1
  printf '00000000-0000-4000-8000-%012d' $ordinal
}

fixture_points_body() {
  jq -nc --argjson count $FIXTURE_POINT_COUNT '
    def point_id($ordinal):
      "000000000000" + ($ordinal | tostring)
      | "00000000-0000-4000-8000-" + .[-12:];
    {points:[range(1; $count + 1) as $ordinal | {
      id:point_id($ordinal),
      vector:(if $ordinal == 1 then
          {dense:[1.0,0.0,0.0,0.0],sparse:{indices:[1,3],values:[1.0,0.5]}}
        elif $ordinal == 2 then
          {dense:[0.8,0.6,0.0,0.0],sparse:{indices:[1,3],values:[0.8,0.4]}}
        else
          {dense:[0.0,0.0,1.0,0.0],sparse:{indices:[10000 + $ordinal],values:[1.0]}}
        end),
      payload:{
        label:(if $ordinal == 1 then "alpha" elif $ordinal == 2 then "beta" else "background" end),
        generation:17,
        ordinal:$ordinal,
        indexed_group:(if $ordinal <= 2 then "target" else "background" end),
        unindexed_group:(if $ordinal <= 2 then "target" else "background" end),
        limit_bucket:(if $ordinal >= 2 then "bulk" else "excluded" end)
      }
    }]}'
}

fixture_expected_query_ids_json() {
  jq -nc --arg primary "$FIXTURE_PRIMARY_ID" --arg secondary "$FIXTURE_SECONDARY_ID" \
    '[$primary,$secondary]'
}

fixture_expected_query_points_json() {
  jq -nc --arg primary "$FIXTURE_PRIMARY_ID" --arg secondary "$FIXTURE_SECONDARY_ID" '
    [
      {id:$primary,payload:{label:"alpha",generation:17,ordinal:1,
        indexed_group:"target",unindexed_group:"target",limit_bucket:"excluded"}},
      {id:$secondary,payload:{label:"beta",generation:17,ordinal:2,
        indexed_group:"target",unindexed_group:"target",limit_bucket:"bulk"}}
    ]'
}

fixture_expected_all_ids_json() {
  jq -nc --argjson count $FIXTURE_POINT_COUNT '
    def point_id($ordinal):
      "000000000000" + ($ordinal | tostring)
      | "00000000-0000-4000-8000-" + .[-12:];
    [range(1; $count + 1) | point_id(.)]'
}

fixture_expected_limit_ids_json() {
  fixture_expected_all_ids_json | jq -c '.[1:]'
}

fixture_spec_json() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local points=''
  points=$(fixture_points_body)
  jq -nc \
    --argjson collection "$(fixture_collection_body)" \
    --arg points_sha256 "$(text_sha256 "$points")" \
    --argjson expected_query_order "$(fixture_expected_query_ids_json)" \
    --argjson expected_query_points "$(fixture_expected_query_points_json)" \
    --argjson point_count $FIXTURE_POINT_COUNT \
    --argjson scroll_page_size $FIXTURE_SCROLL_PAGE_SIZE \
    --argjson scroll_page_count $FIXTURE_SCROLL_PAGE_COUNT \
    --argjson max_query_limit $FIXTURE_MAX_QUERY_LIMIT \
    '{version:"qdrant-migration-fixture/v2",collection:$collection,
      points_sha256:$points_sha256,point_count:$point_count,
      expected_query_order:$expected_query_order,
      expected_query_points:$expected_query_points,
      indexed_payload_field:"indexed_group",unindexed_payload_field:"unindexed_group",
      limit_payload_field:"limit_bucket",scroll_page_size:$scroll_page_size,
      expected_scroll_pages:$scroll_page_count,max_query_limit:$max_query_limit}'
}

query_body() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  case $1 in
    dense)
      print -r -- '{"query":[1.0,0.0,0.0,0.0],"using":"dense","limit":2,"with_payload":true,"filter":{"must":[{"key":"indexed_group","match":{"value":"target"}}]}}'
      ;;
    sparse)
      print -r -- '{"query":{"indices":[1,3],"values":[1.0,0.5]},"using":"sparse","limit":2,"with_payload":true,"filter":{"must":[{"key":"indexed_group","match":{"value":"target"}}]}}'
      ;;
    hybrid)
      print -r -- '{"prefetch":[{"query":[1.0,0.0,0.0,0.0],"using":"dense","limit":2},{"query":{"indices":[1,3],"values":[1.0,0.5]},"using":"sparse","limit":2}],"query":{"fusion":"rrf"},"limit":2,"with_payload":true,"filter":{"must":[{"key":"indexed_group","match":{"value":"target"}}]}}'
      ;;
    *) fail "internal error: unknown query kind: $1" ;;
  esac
}

create_alias() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local collection=$1
  local alias=$2
  api_json POST '/collections/aliases' \
    "{\"actions\":[{\"create_alias\":{\"collection_name\":\"$collection\",\"alias_name\":\"$alias\"}}]}" >/dev/null
}

verify_alias() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local collection=$1
  local alias=$2
  local aliases=''
  aliases=$(api_json GET '/aliases')
  print -r -- "$aliases" | jq -e \
    --arg collection "$collection" --arg alias "$alias" \
    '.result.aliases | any(.alias_name == $alias and .collection_name == $collection)' >/dev/null ||
    fail "expected alias $alias -> $collection was not present"
}

query_fingerprint() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local collection=$1
  local kind=$2
  local response=''
  local expected_points=''
  local observed_points=''
  response=$(api_json POST "/collections/$collection/points/query" "$(query_body $kind)")
  expected_points=$(fixture_expected_query_points_json | jq -Sc '.')
  observed_points=$(print -r -- "$response" | jq -Sc \
    '[.result.points[] | {id,payload}]')
  [[ $observed_points == $expected_points ]] ||
    fail "$kind query did not return the predefined stable ordering and payloads"
  print -r -- "$observed_points"
}

capture_or_compare_fixture_schema() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local metadata=$1
  local schema_identity=''
  local schema_sha256=''
  print -r -- "$metadata" | jq -e '
    (.result.payload_schema | keys) == ["indexed_group"]
    and .result.payload_schema.indexed_group.data_type == "keyword"' >/dev/null ||
    fail 'fixture payload schema does not contain exactly the intended indexed field'
  schema_identity=$(print -r -- "$metadata" | jq -c '
    {indexed_payload_fields:(.result.payload_schema | keys),
      indexed_group_data_type:.result.payload_schema.indexed_group.data_type,
      deliberately_unindexed_payload_fields:["unindexed_group","limit_bucket"]}')
  schema_sha256=$(text_sha256 "$schema_identity")
  if [[ -z $MIGRATION_FIXTURE_SCHEMA_SHA256 ]]; then
    MIGRATION_FIXTURE_SCHEMA_SHA256=$schema_sha256
  else
    [[ $schema_sha256 == $MIGRATION_FIXTURE_SCHEMA_SHA256 ]] ||
      fail 'fixture payload schema identity changed across migration verification'
  fi
}

scroll_fixture_ids() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local collection=$1
  local filter_json=${2:-null}
  local offset=null
  local request=''
  local response=''
  local page_ids=''
  local all_ids='[]'
  integer pages=0

  print -r -- "$filter_json" | jq -e 'type == "object" or . == null' >/dev/null ||
    fail 'internal error: scroll filter is not an object or null'
  while true; do
    request=$(jq -nc --argjson limit $FIXTURE_SCROLL_PAGE_SIZE \
      --argjson offset "$offset" --argjson filter "$filter_json" '
        {limit:$limit,with_payload:true,with_vector:false}
        + (if $offset == null then {} else {offset:$offset} end)
        + (if $filter == null then {} else {filter:$filter} end)')
    response=$(api_json POST "/collections/$collection/points/scroll" "$request")
    page_ids=$(print -r -- "$response" | jq -c '[.result.points[].id]')
    (( $(print -r -- "$page_ids" | jq 'length') > 0 )) ||
      fail 'fixture scroll returned an empty intermediate page'
    all_ids=$(jq -nc --argjson accepted "$all_ids" --argjson page "$page_ids" \
      '$accepted + $page')
    (( pages += 1 ))
    offset=$(print -r -- "$response" | jq -c '.result.next_page_offset')
    [[ $offset != null ]] || break
    (( pages <= FIXTURE_POINT_COUNT )) || fail 'fixture scroll did not terminate'
  done
  jq -nc --argjson ids "$all_ids" --argjson pages $pages '{ids:$ids,pages:$pages}'
}

verify_fixture_observable_contracts() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local collection=$1
  local metadata=$2
  local expected_query_ids=''
  local expected_all_ids=''
  local expected_limit_ids=''
  local indexed_filter='{"must":[{"key":"indexed_group","match":{"value":"target"}}]}'
  local unindexed_filter='{"must":[{"key":"unindexed_group","match":{"value":"target"}}]}'
  local indexed_result=''
  local unindexed_result=''
  local pagination=''
  local limit_response=''
  local limit_ids=''
  local limit_request=$MIGRATION_WORK_ROOT/.fixture-limit-request.json
  integer request_status=0

  expected_query_ids=$(fixture_expected_query_ids_json)
  expected_all_ids=$(fixture_expected_all_ids_json)
  expected_limit_ids=$(fixture_expected_limit_ids_json)
  capture_or_compare_fixture_schema "$metadata"

  indexed_result=$(scroll_fixture_ids "$collection" "$indexed_filter")
  unindexed_result=$(scroll_fixture_ids "$collection" "$unindexed_filter")
  print -r -- "$indexed_result" | jq -e --argjson expected "$expected_query_ids" \
    '.pages == 1 and .ids == $expected' >/dev/null ||
    fail 'indexed payload filtering returned an unexpected fixture result'
  print -r -- "$unindexed_result" | jq -e --argjson expected "$expected_query_ids" \
    '.pages == 1 and .ids == $expected' >/dev/null ||
    fail 'deliberately unindexed payload filtering returned an unexpected fixture result'
  MIGRATION_FIXTURE_INDEXED_FILTER_SHA256=$(text_sha256 "$indexed_result")
  MIGRATION_FIXTURE_UNINDEXED_FILTER_SHA256=$(text_sha256 "$unindexed_result")

  pagination=$(scroll_fixture_ids "$collection")
  print -r -- "$pagination" | jq -e --argjson expected "$expected_all_ids" \
    --argjson pages $FIXTURE_SCROLL_PAGE_COUNT \
    '.pages == $pages and .ids == $expected and (.ids | length) == 1001 and (.ids | unique | length) == 1001' >/dev/null ||
    fail 'fixture pagination did not traverse all 1001 stable IDs across exactly eight pages'
  MIGRATION_FIXTURE_PAGINATION_SHA256=$(text_sha256 "$pagination")
  MIGRATION_FIXTURE_IDS_SHA256=$(text_sha256 "$expected_all_ids")

  limit_response=$(api_json POST "/collections/$collection/points/query" "$(jq -nc \
    --argjson limit $FIXTURE_MAX_QUERY_LIMIT \
    '{query:[0.0,0.0,1.0,0.0],using:"dense",limit:$limit,with_payload:true,
      filter:{must:[{key:"limit_bucket",match:{value:"bulk"}}]}}')")
  limit_ids=$(print -r -- "$limit_response" | jq -c '[.result.points[].id] | sort')
  [[ $limit_ids == $expected_limit_ids ]] ||
    fail 'query limit 1000 did not return the exact 1000-point boundary set'
  MIGRATION_FIXTURE_LIMIT_SHA256=$(text_sha256 "$limit_ids")

  jq -nc --argjson limit $(( FIXTURE_MAX_QUERY_LIMIT + 1 )) \
    '{query:[0.0,0.0,1.0,0.0],using:"dense",limit:$limit,with_payload:false,
      filter:{must:[{key:"limit_bucket",match:{value:"bulk"}}]}}' >| "$limit_request"
  attempt_json_file POST "/collections/$collection/points/query" "$limit_request" || request_status=$?
  [[ $MIGRATION_LAST_HTTP_CODE == 4<-> ]] ||
    fail "query limit 1001 was not rejected by the ready server: HTTP ${MIGRATION_LAST_HTTP_CODE:-<none>}"
  print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -e \
    '.status.error | type == "string" and test("limit|1000|max_query_limit"; "i")' >/dev/null ||
    fail 'query limit 1001 rejection did not identify the configured maximum'
  require_active_process_running 'after safely rejecting query limit 1001'
  verify_authenticated_readiness 'after safely rejecting query limit 1001'
}

capture_or_compare_fixture() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local collection=$1
  local mode=$2
  local dense=''
  local sparse=''
  local hybrid=''
  dense=$(query_fingerprint "$collection" dense)
  sparse=$(query_fingerprint "$collection" sparse)
  hybrid=$(query_fingerprint "$collection" hybrid)

  if [[ $mode == capture ]]; then
    MIGRATION_DENSE_FINGERPRINT=$dense
    MIGRATION_SPARSE_FINGERPRINT=$sparse
    MIGRATION_HYBRID_FINGERPRINT=$hybrid
  else
    [[ $dense == $MIGRATION_DENSE_FINGERPRINT ]] || fail 'dense query result changed across the migration'
    [[ $sparse == $MIGRATION_SPARSE_FINGERPRINT ]] || fail 'sparse query result changed across the migration'
    [[ $hybrid == $MIGRATION_HYBRID_FINGERPRINT ]] || fail 'hybrid query result changed across the migration'
  fi
}

create_fixture() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local points_file=$MIGRATION_WORK_ROOT/.fixture-points.json
  local points=''
  api_json PUT "/collections/$FIXTURE_COLLECTION" "$(fixture_collection_body)" >/dev/null
  api_json PUT "/collections/$FIXTURE_COLLECTION/index?wait=true" \
    '{"field_name":"indexed_group","field_schema":"keyword"}' >/dev/null
  points=$(fixture_points_body)
  print -rn -- "$points" >| "$points_file"
  MIGRATION_FIXTURE_POINTS_SHA256=$(file_sha256 "$points_file")
  api_json_file PUT "/collections/$FIXTURE_COLLECTION/points?wait=true" "$points_file" >/dev/null
  create_alias "$FIXTURE_COLLECTION" "$FIXTURE_ALIAS"
  capture_or_compare_fixture "$FIXTURE_COLLECTION" capture
  verify_alias "$FIXTURE_COLLECTION" "$FIXTURE_ALIAS"
  capture_or_compare_fixture "$FIXTURE_ALIAS" compare
}

verify_fixture() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local collection=${1:-$FIXTURE_COLLECTION}
  local alias=${2:-$FIXTURE_ALIAS}
  local metadata=''
  metadata=$(api_json GET "/collections/$collection")
  print -r -- "$metadata" | jq -e \
    --argjson point_count $FIXTURE_POINT_COUNT \
    '.result.points_count == $point_count
     and .result.config.params.vectors.dense.size == 4
     and (.result.config.params.sparse_vectors | has("sparse"))' >/dev/null ||
    fail "fixture metadata or point count changed for $collection"
  verify_fixture_observable_contracts "$collection" "$metadata"
  capture_or_compare_fixture "$collection" compare
  verify_alias "$collection" "$alias"
  capture_or_compare_fixture "$alias" compare
}

record_fixture_queries() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local fingerprints=''
  fingerprints=$(jq -nc \
    --argjson dense "$MIGRATION_DENSE_FINGERPRINT" \
    --argjson sparse "$MIGRATION_SPARSE_FINGERPRINT" \
    --argjson hybrid "$MIGRATION_HYBRID_FINGERPRINT" \
    '{dense:$dense,sparse:$sparse,hybrid:$hybrid}')
  MIGRATION_QUERY_SET_SHA256=$(text_sha256 "$fingerprints")
  MIGRATION_FIXTURE_SPEC_SHA256=$(text_sha256 "$(fixture_spec_json)")
  record_event fixture_schema_verified fixture "$(jq -nc \
    --arg fixture_spec_sha256 "$MIGRATION_FIXTURE_SPEC_SHA256" \
    --arg points_sha256 "$MIGRATION_FIXTURE_POINTS_SHA256" \
    --arg schema_sha256 "$MIGRATION_FIXTURE_SCHEMA_SHA256" \
    --argjson point_count $FIXTURE_POINT_COUNT \
    '{fixture_spec:"qdrant-migration-fixture/v2",fixture_spec_sha256:$fixture_spec_sha256,
      points_sha256:$points_sha256,schema_sha256:$schema_sha256,point_count:$point_count,
      indexed_payload_fields:["indexed_group"],deliberately_unindexed_payload_fields:["unindexed_group","limit_bucket"]}')"
  record_event fixture_filters_verified query "$(jq -nc \
    --arg indexed_result_sha256 "$MIGRATION_FIXTURE_INDEXED_FILTER_SHA256" \
    --arg unindexed_result_sha256 "$MIGRATION_FIXTURE_UNINDEXED_FILTER_SHA256" \
    --argjson expected_ids "$(fixture_expected_query_ids_json)" \
    '{indexed_field:"indexed_group",unindexed_field:"unindexed_group",expected_ids:$expected_ids,
      indexed_result_sha256:$indexed_result_sha256,unindexed_result_sha256:$unindexed_result_sha256,exact_results:true}')"
  record_event fixture_pagination_verified query "$(jq -nc \
    --arg ids_sha256 "$MIGRATION_FIXTURE_IDS_SHA256" \
    --arg pagination_sha256 "$MIGRATION_FIXTURE_PAGINATION_SHA256" \
    --argjson page_size $FIXTURE_SCROLL_PAGE_SIZE --argjson pages $FIXTURE_SCROLL_PAGE_COUNT \
    --argjson point_count $FIXTURE_POINT_COUNT \
    '{page_size:$page_size,pages:$pages,point_count:$point_count,ids_sha256:$ids_sha256,
      pagination_sha256:$pagination_sha256,no_duplicates:true,complete:true}')"
  record_event fixture_query_limit_verified query "$(jq -nc \
    --arg query_limit_1000_result_sha256 "$MIGRATION_FIXTURE_LIMIT_SHA256" \
    --argjson accepted_limit $FIXTURE_MAX_QUERY_LIMIT \
    --argjson rejected_limit $(( FIXTURE_MAX_QUERY_LIMIT + 1 )) \
    '{configured_max_query_limit:$accepted_limit,query_limit_1000_succeeded:true,
      query_limit_1000_result_count:1000,query_limit_1000_result_sha256:$query_limit_1000_result_sha256,
      query_limit_1001_rejected:true,rejected_limit:$rejected_limit,server_remained_ready:true}')"
  record_event fixture_queries_captured query "$(jq -nc \
    --arg collection "$FIXTURE_COLLECTION" --arg alias "$FIXTURE_ALIAS" \
    --argjson query_fingerprints "$fingerprints" \
    --arg query_fingerprint_sha256 "$MIGRATION_QUERY_SET_SHA256" \
    --arg fixture_spec_sha256 "$MIGRATION_FIXTURE_SPEC_SHA256" \
    --argjson point_count $FIXTURE_POINT_COUNT \
    '{collection:$collection,alias:$alias,stable_uuid:"00000000-0000-4000-8000-000000000001",
      point_count:$point_count,fixture_spec_sha256:$fixture_spec_sha256,
      query_fingerprints:$query_fingerprints,query_fingerprint_sha256:$query_fingerprint_sha256}')"
}

create_collection_snapshot() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local collection=$1
  local destination=$2
  local response=''
  local name=''
  local checksum=''
  response=$(api_json POST "/collections/$collection/snapshots?wait=true")
  name=$(print -r -- "$response" | jq -er '.result.name')
  checksum=$(print -r -- "$response" | jq -er '.result.checksum')
  download_snapshot "/collections/$collection/snapshots/$name" "$destination" "$checksum"
}

create_full_snapshot() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local destination=$1
  local response=''
  local name=''
  local checksum=''
  response=$(api_json POST '/snapshots?wait=true')
  name=$(print -r -- "$response" | jq -er '.result.name')
  checksum=$(print -r -- "$response" | jq -er '.result.checksum')
  download_snapshot "/snapshots/$name" "$destination" "$checksum"
}

copy_storage() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local source=$1
  local destination=$2
  [[ -d $source ]] || fail "storage source is missing: $source"
  [[ ! -e $destination ]] || fail "storage destination already exists: $destination"
  mkdir -p -- "$destination"
  cp -a -- "$source/." "$destination/"
}

seal_cold_copy() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local cold_copy=$1
  [[ -d $cold_copy ]] || fail "cold-copy path is missing: $cold_copy"
  chmod -R a-w -- "$cold_copy"
}

make_storage_writable() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local storage_root=$1
  [[ -d $storage_root ]] || fail "migration storage path is missing: $storage_root"
  chmod -R u+w -- "$storage_root"
}

restart_and_verify() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local binary=$1
  local version=$2
  local instance=$3
  local config=$4
  local collection=${5:-$FIXTURE_COLLECTION}
  local alias=${6:-$FIXTURE_ALIAS}
  stop_server
  start_server "$binary" "$version" "$instance" "$config"
  verify_fixture "$collection" "$alias"
}

restore_collection_snapshot() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local binary=$1
  local version=$2
  local snapshot=$3
  local instance=$4
  local restored_collection=$5
  local restored_alias=$6
  local event_id=$7
  local config=''
  local snapshot_before=''
  snapshot_before=$(file_sha256 "$snapshot")
  config=$(write_config "$instance")
  start_server "$binary" "$version" "$instance" "$config" \
    --snapshot "$snapshot:$restored_collection"
  create_alias "$restored_collection" "$restored_alias"
  verify_fixture "$restored_collection" "$restored_alias"
  stop_server
  [[ $(file_sha256 "$snapshot") == $snapshot_before ]] ||
    fail "snapshot changed while proving restore: $snapshot"
  record_event "$event_id" restore "$(jq -nc --arg target_version "$version" \
    --arg snapshot "${snapshot:t}" --arg snapshot_sha256 "$snapshot_before" \
    --arg collection "$restored_collection" --arg alias "$restored_alias" \
    --arg query_fingerprint_sha256 "$MIGRATION_QUERY_SET_SHA256" \
    '{target_version:$target_version,snapshot:$snapshot,snapshot_sha256:$snapshot_sha256,collection:$collection,alias:$alias,query_fingerprint_sha256:$query_fingerprint_sha256,retrieval_equivalent:true}')"
}

expect_corrupt_snapshot_rejected() {
  emulate -L zsh
  setopt NO_UNSET PIPE_FAIL
  local binary=$1
  local version=$2
  local snapshot=$3
  local instance=$4
  local config=''
  local log=''
  integer attempt=0
  integer exit_status=0
  integer capture_status=0

  MIGRATION_LAST_PROCESS_EXIT=''
  MIGRATION_LAST_REJECTION_LOG_SHA256=''
  config=$(write_config "$instance")
  validate_ports_available
  log=$instance/corrupt-rejection.log
  (
    cd -- "$instance"
    export QDRANT__SERVICE__API_KEY=$MIGRATION_API_KEY
    exec setpriv --no-new-privs --bounding-set=-all --inh-caps=-all \
      --ambient-caps=-all -- "$binary" --config-path "$config" \
      --disable-telemetry --snapshot "$snapshot:migration-corrupt"
  ) >| "$log" 2>&1 &
  MIGRATION_ACTIVE_PID=$!
  MIGRATION_ACTIVE_LOG=$log
  capture_active_process_identity "$binary" || capture_status=$?
  if (( capture_status == 1 )); then
    wait $MIGRATION_ACTIVE_PID 2>/dev/null || exit_status=$?
    MIGRATION_ACTIVE_PID=''
    MIGRATION_ACTIVE_START=''
    MIGRATION_ACTIVE_EXE=''
    MIGRATION_ACTIVE_LOG=''
    (( exit_status != 0 )) || fail 'corrupted snapshot process exited successfully'
    MIGRATION_LAST_PROCESS_EXIT=$exit_status
    grep -Fq 'Failed to recover snapshot' "$log" ||
      fail 'corrupted snapshot process failed for a reason unrelated to snapshot recovery'
    MIGRATION_LAST_REJECTION_LOG_SHA256=$(file_sha256 "$log")
    return 0
  elif (( capture_status != 0 )); then
    fail 'corrupted snapshot process identity remained indeterminate'
    return 2
  fi

  for attempt in {1..300}; do
    sample_owned_process_state $MIGRATION_ACTIVE_PID "$MIGRATION_ACTIVE_START" "$MIGRATION_ACTIVE_EXE"
    if [[ $REPLY == mismatch ]]; then
      fail 'corrupted snapshot process ownership changed before rejection'
      return 2
    elif [[ $REPLY == stopped ]]; then
      wait $MIGRATION_ACTIVE_PID 2>/dev/null || exit_status=$?
      MIGRATION_ACTIVE_PID=''
      MIGRATION_ACTIVE_START=''
      MIGRATION_ACTIVE_EXE=''
      MIGRATION_ACTIVE_LOG=''
      (( exit_status != 0 )) || fail 'corrupted snapshot was accepted with a successful exit'
      MIGRATION_LAST_PROCESS_EXIT=$exit_status
      grep -Fq 'Failed to recover snapshot' "$log" ||
        fail 'corrupted snapshot process failed for a reason unrelated to snapshot recovery'
      MIGRATION_LAST_REJECTION_LOG_SHA256=$(file_sha256 "$log")
      print -r -- "corrupted snapshot rejected by qdrant $version (exit status $exit_status)"
      return 0
    elif [[ $REPLY == indeterminate ]]; then
      sleep 0.1
      continue
    fi
    if authenticated_curl --output /dev/null \
      "$MIGRATION_BASE_URL/collections" 2>/dev/null; then
      stop_server
      fail 'corrupted snapshot was accepted and the server became ready'
    fi
    sleep 0.1
  done
  stop_server
  fail "corrupted snapshot neither failed nor became ready; log: $log"
}

prove_truncated_rejection_and_retry() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local binary=$1
  local target_version=$2
  local source_version=$3
  local snapshot=$4
  local instance=$5
  local rejection_event=$6
  local retry_event=$7
  local truncated=$instance.truncated.snapshot
  local config=$instance/qdrant.yaml
  local original_sha=''
  local truncated_sha=''
  local snapshot_size=''
  local retry_collection="migration-retry-${source_version//./-}-to-${target_version//./-}"
  local retry_alias="$retry_collection-current"

  original_sha=$(file_sha256 "$snapshot")
  cp -- "$snapshot" "$truncated"
  snapshot_size=$(stat -c '%s' -- "$truncated")
  (( snapshot_size > 2 )) || fail "snapshot is too small to truncate: $snapshot"
  truncate -s $(( snapshot_size / 2 )) -- "$truncated"
  truncated_sha=$(file_sha256 "$truncated")
  [[ $truncated_sha != $original_sha ]] || fail 'truncated snapshot retained the source digest'

  expect_corrupt_snapshot_rejected "$binary" "$target_version" "$truncated" "$instance"
  [[ -n $MIGRATION_LAST_PROCESS_EXIT ]] || fail 'truncated rejection did not capture a failing process status'
  [[ ${#MIGRATION_LAST_REJECTION_LOG_SHA256} == 64 &&
    -z ${MIGRATION_LAST_REJECTION_LOG_SHA256//[0-9a-f]/} ]] ||
    fail 'truncated rejection did not capture a recovery-failure log digest'
  [[ $(file_sha256 "$snapshot") == $original_sha ]] || fail 'source snapshot changed after truncated rejection'
  record_event "$rejection_event" rejection "$(jq -nc \
    --arg source_version "$source_version" --arg target_version "$target_version" \
    --arg source_snapshot "${snapshot:t}" --arg source_snapshot_sha256 "$original_sha" \
    --arg rejected_snapshot "${truncated:t}" --arg rejected_snapshot_sha256 "$truncated_sha" \
    --arg rejection_log_sha256 "$MIGRATION_LAST_REJECTION_LOG_SHA256" \
    --argjson exit_status "$MIGRATION_LAST_PROCESS_EXIT" \
    '{kind:"truncated",source_version:$source_version,target_version:$target_version,source_snapshot:$source_snapshot,source_snapshot_sha256:$source_snapshot_sha256,rejected_snapshot:$rejected_snapshot,rejected_snapshot_sha256:$rejected_snapshot_sha256,rejection_marker:"Failed to recover snapshot",rejection_log_sha256:$rejection_log_sha256,exit_status:$exit_status,target_was_disposable:true}')"

  start_server "$binary" "$target_version" "$instance" "$config" \
    --snapshot "$snapshot:$retry_collection"
  create_alias "$retry_collection" "$retry_alias"
  verify_fixture "$retry_collection" "$retry_alias"
  stop_server
  [[ $(file_sha256 "$snapshot") == $original_sha ]] || fail 'source snapshot changed after truncated retry'
  record_event "$retry_event" retry "$(jq -nc \
    --arg source_version "$source_version" --arg target_version "$target_version" \
    --arg snapshot "${snapshot:t}" --arg snapshot_sha256 "$original_sha" \
    --arg query_fingerprint_sha256 "$MIGRATION_QUERY_SET_SHA256" \
    '{kind:"truncated_recovery",source_version:$source_version,target_version:$target_version,snapshot:$snapshot,snapshot_sha256:$snapshot_sha256,query_fingerprint_sha256:$query_fingerprint_sha256,same_target_after_failure:true,retrieval_equivalent:true}')"
}

prove_checksum_rejection_and_retry() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local binary=$1
  local target_version=$2
  local source_version=$3
  local snapshot=$4
  local instance=$5
  local rejection_event=$6
  local retry_event=$7
  local collection="checksum-retry-${source_version//./-}-to-${target_version//./-}"
  local alias="$collection-current"
  local config=''
  local correct_checksum=''
  local wrong_checksum=''
  local rejection_error=''
  integer upload_status=0

  correct_checksum=$(file_sha256 "$snapshot")
  wrong_checksum=${correct_checksum/0/1}
  [[ $wrong_checksum != $correct_checksum ]] || wrong_checksum=${correct_checksum/1/0}
  [[ $wrong_checksum != $correct_checksum ]] || fail 'could not construct a mismatched checksum'
  config=$(write_config "$instance")
  start_server "$binary" "$target_version" "$instance" "$config"

  upload_snapshot_attempt "$snapshot" "$collection" "$wrong_checksum" || upload_status=$?
  [[ $MIGRATION_LAST_HTTP_CODE == 4<-> || $MIGRATION_LAST_HTTP_CODE == 5<-> ]] ||
    fail "checksum-mismatched upload was not rejected: HTTP ${MIGRATION_LAST_HTTP_CODE:-<none>}"
  print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -e \
    '.status.error | type == "string" and test("checksum"; "i")' >/dev/null ||
    fail 'checksum-mismatched upload did not return a checksum-specific error'
  rejection_error=$(print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -er '.status.error')
  [[ $(file_sha256 "$snapshot") == $correct_checksum ]] || fail 'source snapshot changed after checksum rejection'
  record_event "$rejection_event" rejection "$(jq -nc \
    --arg source_version "$source_version" --arg target_version "$target_version" \
    --arg snapshot "${snapshot:t}" --arg snapshot_sha256 "$correct_checksum" \
    --arg supplied_checksum "$wrong_checksum" --arg http_code "$MIGRATION_LAST_HTTP_CODE" \
    --arg error "$rejection_error" \
    '{kind:"checksum_mismatch",source_version:$source_version,target_version:$target_version,snapshot:$snapshot,snapshot_sha256:$snapshot_sha256,supplied_checksum:$supplied_checksum,http_code:$http_code,error:$error,target_was_disposable:true}')"

  upload_status=0
  upload_snapshot_attempt "$snapshot" "$collection" "$correct_checksum" || upload_status=$?
  (( upload_status == 0 )) || fail "valid checksum retry failed at the transport layer: $upload_status"
  [[ $MIGRATION_LAST_HTTP_CODE == 200 ]] ||
    fail "valid checksum retry returned HTTP $MIGRATION_LAST_HTTP_CODE"
  print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -e '.status == "ok"' >/dev/null ||
    fail 'valid checksum retry returned a non-ok response'
  create_alias "$collection" "$alias"
  verify_fixture "$collection" "$alias"
  stop_server
  [[ $(file_sha256 "$snapshot") == $correct_checksum ]] || fail 'source snapshot changed after checksum retry'
  record_event "$retry_event" retry "$(jq -nc \
    --arg source_version "$source_version" --arg target_version "$target_version" \
    --arg snapshot "${snapshot:t}" --arg snapshot_sha256 "$correct_checksum" \
    --arg query_fingerprint_sha256 "$MIGRATION_QUERY_SET_SHA256" \
    '{kind:"checksum_recovery",source_version:$source_version,target_version:$target_version,snapshot:$snapshot,snapshot_sha256:$snapshot_sha256,query_fingerprint_sha256:$query_fingerprint_sha256,same_target_after_failure:true,retrieval_equivalent:true}')"
}

write_pressure_config() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local instance=$1
  local storage_root=$2
  local config=$instance/qdrant-pressure.yaml
  mkdir -p -- "$instance" "$storage_root" "$instance/snapshots"
  print -r -- "storage:
  storage_path: $storage_root
  snapshots_path: $instance/snapshots
  quotas:
    enabled: true
    max_resident_memory_percent: 80
    max_disk_usage_percent: 85
    release_margin_percent: 10
service:
  host: 127.0.0.1
  http_port: $MIGRATION_HTTP_PORT
  grpc_port: $MIGRATION_GRPC_PORT
  max_workers: 2
  enable_cors: false
cluster:
  enabled: false
telemetry_disabled: true" >| "$config"
  chmod 600 -- "$config"
  print -r -- "$config"
}

filesystem_used_percent() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local mount_root=$1
  local usage=''
  usage=$(df --output=pcent "$mount_root" | tail -n 1)
  usage=${usage//[ %]/}
  [[ $usage == <-> ]] || fail "could not read filesystem use percentage for $mount_root"
  print -r -- $usage
}

fill_filesystem_to_percent() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local mount_root=$1
  local target_percent=$2
  local filler=$mount_root/.pressure-filler
  local stats=''
  local -a fields=()
  local total=0
  local used=0
  local existing=0
  local other_used=0
  local desired=0
  stats=$(df -B1 --output=size,used "$mount_root" | tail -n 1)
  fields=(${=stats})
  (( ${#fields} == 2 )) || fail "could not read filesystem size for $mount_root"
  total=$fields[1]
  used=$fields[2]
  [[ -f $filler ]] && existing=$(stat -c '%s' -- "$filler")
  other_used=$(( used - existing ))
  desired=$(( (total * target_percent / 100) - other_used ))
  (( desired > 0 )) || fail "filesystem already exceeds requested pressure target: $target_percent%"
  truncate -s 0 -- "$filler"
  fallocate -l $desired -- "$filler"
  sync -f "$filler"
  print -r -- "$(filesystem_used_percent "$mount_root")"
}

process_rss_bytes() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local pid=$1
  local rss_line=''
  local -a fields=()
  rss_line=$(<"/proc/$pid/status")
  rss_line=${${(M)${(f)rss_line}:#VmRSS:*}#VmRSS:}
  fields=(${=rss_line})
  (( ${#fields} >= 1 )) || fail "could not read resident memory for PID $pid"
  print -r -- $(( fields[1] * 1024 ))
}

cgroup_memory_current() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local current_file=/sys/fs/cgroup$MIGRATION_CGROUP_PATH/memory.current
  [[ -r $current_file ]] || fail 'cgroup memory.current is unreadable'
  print -r -- "$(<$current_file)"
}

write_memory_pressure_batch() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local request_file=$1
  local start_id=$2
  local batch_size=100
  local nonzero_values=512
  jq -nc --argjson start "$start_id" --argjson count $batch_size \
    --argjson nonzero_values $nonzero_values \
    '{points:[range(0;$count) as $offset |
      {id:($start + $offset),vector:{sparse:{
        indices:[range(0;$nonzero_values) | (($start + $offset) * $nonzero_values + .)],
        values:[range(0;$nonzero_values) | 0.001]
      }}}]}' \
    >| "$request_file"
  [[ -s $request_file ]] || fail 'memory-pressure request generation produced no data'
}

memory_pressure_batch_ids_json() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local start_id=$1
  local batch_size=${2:-100}
  jq -nc --argjson start_id "$start_id" --argjson batch_size "$batch_size" \
    '[range(0;$batch_size) | $start_id + .]'
}

pressure_collection_fingerprint() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local collection=$1
  local response=''
  local exact_points=''

  response=$(api_json POST "/collections/$collection/points/scroll" \
    '{"limit":1000,"with_payload":true,"with_vector":false}')
  print -r -- "$response" | jq -e '.result.next_page_offset == null' >/dev/null ||
    fail "pressure collection exceeded the single-page fingerprint contract: $collection"
  exact_points=$(print -r -- "$response" | jq -c \
    '[.result.points[] | {id,payload}] | sort_by(.id)')
  jq -nc --argjson exact_points "$exact_points" \
    --arg points_sha256 "$(text_sha256 "$exact_points")" \
    '{point_count:($exact_points | length),exact_points:$exact_points,points_sha256:$points_sha256}'
}

verify_rejected_batch_absent() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local collection=$1
  local ids=$2
  local response=''
  local existing_points=''
  print -r -- "$ids" | jq -e '
    type == "array" and length > 0 and (unique | length) == length
    and all(.[]; type == "number" or type == "string")' >/dev/null ||
    fail 'rejected batch IDs are empty, duplicated, or malformed'
  response=$(api_json POST "/collections/$collection/points" "$(jq -nc \
    --argjson ids "$ids" '{ids:$ids,with_payload:true,with_vector:false}')")
  existing_points=$(print -r -- "$response" | jq -c \
    '[.result[] | {id,payload}] | sort_by(.id)')
  [[ $existing_points == '[]' ]] ||
    fail "rejected batch was partially or fully applied to $collection"
  jq -nc --arg collection "$collection" --argjson ids "$ids" \
    --arg ids_sha256 "$(text_sha256 "$ids")" \
    --argjson existing_points "$existing_points" \
    --arg existing_points_sha256 "$(text_sha256 "$existing_points")" '
      {applicable:true,collection:$collection,ids:$ids,ids_count:($ids | length),
        ids_sha256:$ids_sha256,observed_existing_points:$existing_points,
        observed_existing_points_sha256:$existing_points_sha256,absent:true}'
}

pressure_integrity_details() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local resource=$1
  local rejected_points=$2
  local pre_pressure=$3
  local post_rejection=$4
  local post_release_retry=$5
  local post_restart=$6
  local stage=''
  local rejected_ids=''
  local expected_post_retry=''

  print -r -- "$rejected_points" | jq -e '
    type == "array" and length > 0
    and all(.[]; has("id") and (.payload | type) == "object")
    and (map(.id) | unique | length) == length' >/dev/null ||
    fail "$resource pressure rejected point set is empty, duplicated, or malformed"
  rejected_ids=$(print -r -- "$rejected_points" | jq -c 'map(.id)')
  for stage in "$pre_pressure" "$post_rejection" "$post_release_retry" "$post_restart"; do
    print -r -- "$stage" | jq -e '
      (.point_count | type) == "number"
      and (.points_sha256 | test("^[0-9a-f]{64}$"))
      and (.exact_points | type) == "array"
      and (.exact_points | length) == .point_count' >/dev/null ||
      fail "$resource pressure fingerprint is malformed"
  done
  [[ $pre_pressure == $post_rejection ]] ||
    fail "$resource pressure rejection changed the accepted collection fingerprint"
  [[ $post_release_retry == $post_restart ]] ||
    fail "$resource pressure retry fingerprint changed across restart"
  print -r -- "$post_rejection" | jq -e --argjson rejected_ids "$rejected_ids" '
    all(.exact_points[]; (.id as $id | $rejected_ids | index($id)) == null)' >/dev/null ||
    fail "$resource pressure rejected ID appeared before retry"
  print -r -- "$post_release_retry" | jq -e --argjson rejected_ids "$rejected_ids" '
    (.exact_points | map(.id)) as $accepted_ids
    | all($rejected_ids[]; . as $rejected | $accepted_ids | index($rejected) != null)' \
    >/dev/null ||
    fail "$resource pressure rejected ID remained absent after retry"
  expected_post_retry=$(jq -nc --argjson pre_pressure "$pre_pressure" \
    --argjson rejected_points "$rejected_points" '
      ($pre_pressure.exact_points + $rejected_points) | sort_by(.id)')
  print -r -- "$post_release_retry" | jq -e --argjson expected "$expected_post_retry" '
    .exact_points == $expected and .point_count == ($expected | length)' >/dev/null ||
    fail "$resource pressure retry did not produce the exact expected point and payload set"
  jq -nc --arg resource "$resource" --argjson rejected_ids "$rejected_ids" \
    --arg rejected_ids_sha256 "$(text_sha256 "$rejected_ids")" \
    --argjson retried_points "$rejected_points" \
    --arg retried_points_sha256 "$(text_sha256 "$rejected_points")" \
    --argjson pre_pressure "$pre_pressure" --argjson post_rejection "$post_rejection" \
    --argjson post_release_retry "$post_release_retry" --argjson post_restart "$post_restart" '
      {resource:$resource,rejected_ids:$rejected_ids,rejected_ids_sha256:$rejected_ids_sha256,
        retried_points:$retried_points,retried_points_sha256:$retried_points_sha256,
        rejected_ids_absent:true,rejected_batch_absent:true,exact_points:true,
        stages:{pre_pressure:$pre_pressure,post_rejection:$post_rejection,
          post_release_retry:$post_release_retry,post_restart:$post_restart},
        rejection_preserved_exact_fingerprint:($pre_pressure == $post_rejection),
        restart_preserved_exact_fingerprint:($post_release_retry == $post_restart)}'
}

record_pressure_integrity() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local resource=$1
  local event_id=$2
  local rejected_id=$3
  local pre_pressure=$4
  local post_rejection=$5
  local post_release_retry=$6
  local post_restart=$7

  local details=''
  local rejected_points=''
  rejected_points=$(jq -nc --arg resource "$resource" --argjson rejected_id "$rejected_id" '
    [{id:$rejected_id,payload:{lane:$resource,state:"retried"}}]')
  details=$(pressure_integrity_details "$resource" "$rejected_points" \
    "$pre_pressure" "$post_rejection" "$post_release_retry" "$post_restart")
  record_event "$event_id" resource_pressure "$details"
}

exercise_disk_pressure() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local binary=$1
  local instance=$MIGRATION_WORK_ROOT/pressure-disk-1.19.0
  local mount_root=$instance/limited-filesystem
  local config=''
  local below_percent=''
  local above_percent=''
  local recovered_percent=''
  local request_file=$instance/rejected-write.json
  local pre_pressure=''
  local post_rejection=''
  local post_release_retry=''
  local post_restart=''
  integer attempt=0
  integer request_status=0

  mkdir -p -- "$mount_root"
  mount -t tmpfs -o size=209715200,nosuid,nodev,noexec tmpfs "$mount_root" ||
    fail 'resource-pressure isolation could not mount its size-limited tmpfs'
  config=$(write_pressure_config "$instance" "$mount_root/storage")
  start_server "$binary" 1.19.0 "$instance" "$config"
  api_json PUT '/collections/pressure-disk' \
    '{"vectors":{"size":4,"distance":"Cosine"},"wal_config":{"wal_capacity_mb":1}}' >/dev/null

  below_percent=$(fill_filesystem_to_percent "$mount_root" 70)
  (( below_percent < 85 )) || fail "disk below-threshold fixture reached $below_percent%"
  api_json PUT '/collections/pressure-disk/points?wait=true' \
    '{"points":[{"id":1,"vector":[1,0,0,0],"payload":{"lane":"disk","state":"accepted"}}]}' >/dev/null
  pre_pressure=$(pressure_collection_fingerprint pressure-disk)
  record_event disk_below_threshold_write resource_pressure "$(jq -nc \
    --argjson observed_percent "$below_percent" --argjson fingerprint "$pre_pressure" \
    '{resource:"disk",configured_threshold_percent:85,observed_percent:$observed_percent,
      write_succeeded:true,pre_pressure:$fingerprint}')"

  above_percent=$(fill_filesystem_to_percent "$mount_root" 90)
  (( above_percent >= 85 )) || fail "disk pressure did not cross its threshold: $above_percent%"
  sleep 5.2
  print -r -- '{"points":[{"id":2,"vector":[0,1,0,0],"payload":{"lane":"disk","state":"retried"}}]}' >| "$request_file"
  for attempt in {1..50}; do
    request_status=0
    attempt_json_file PUT '/collections/pressure-disk/points?wait=true' "$request_file" || request_status=$?
    if [[ $MIGRATION_LAST_HTTP_CODE != 200 ]] ||
      ! print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -e '.status == "ok"' >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done
  [[ $MIGRATION_LAST_HTTP_CODE == 4<-> || $MIGRATION_LAST_HTTP_CODE == 5<-> ]] ||
    fail "disk pressure was not rejected above 85%: HTTP ${MIGRATION_LAST_HTTP_CODE:-<none>}"
  print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -e \
    '.status.error | type == "string" and test("disk usage|quota"; "i")' >/dev/null ||
    fail 'disk-pressure rejection did not come from the configured quota gate'
  require_active_process_running 'after safely rejecting disk pressure'
  post_rejection=$(pressure_collection_fingerprint pressure-disk)
  [[ $post_rejection == $pre_pressure ]] ||
    fail 'disk-pressure rejection changed the accepted point set or payload'
  record_event disk_above_threshold_rejection resource_pressure "$(jq -nc \
    --argjson observed_percent "$above_percent" --arg http_code "$MIGRATION_LAST_HTTP_CODE" \
    --arg error "$(print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -r '.status.error')" \
    --argjson fingerprint "$post_rejection" \
    '{resource:"disk",configured_threshold_percent:85,observed_percent:$observed_percent,
      http_code:$http_code,error:$error,rejected:true,rejected_id:2,rejected_ids_absent:true,
      server_remained_ready:true,post_rejection:$fingerprint}')"

  truncate -s 0 -- "$mount_root/.pressure-filler"
  sync -f "$mount_root/.pressure-filler"
  recovered_percent=$(filesystem_used_percent "$mount_root")
  (( recovered_percent < 75 )) ||
    fail "disk pressure did not cross the 75% release margin: $recovered_percent%"
  for attempt in {1..50}; do
    request_status=0
    attempt_json_file PUT '/collections/pressure-disk/points?wait=true' "$request_file" || request_status=$?
    if [[ $MIGRATION_LAST_HTTP_CODE == 200 ]] &&
      print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -e '.status == "ok"' >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done
  [[ $MIGRATION_LAST_HTTP_CODE == 200 ]] || fail 'disk-pressure write did not recover below the release margin'
  post_release_retry=$(pressure_collection_fingerprint pressure-disk)
  record_event disk_release_margin_recovery resource_pressure "$(jq -nc \
    --argjson observed_percent "$recovered_percent" --argjson fingerprint "$post_release_retry" \
    '{resource:"disk",release_below_percent:75,observed_percent:$observed_percent,
      retry_succeeded:true,retried_id:2,post_release_retry:$fingerprint}')"

  stop_server
  start_server "$binary" 1.19.0 "$instance" "$config"
  post_restart=$(pressure_collection_fingerprint pressure-disk)
  record_pressure_integrity disk disk_integrity_after_pressure 2 \
    "$pre_pressure" "$post_rejection" "$post_release_retry" "$post_restart"
  stop_server
  umount -- "$mount_root" || fail 'resource-pressure tmpfs did not unmount cleanly'
}

exercise_memory_pressure() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local binary=$1
  local instance=$MIGRATION_WORK_ROOT/pressure-memory-1.19.0
  local config=''
  local load_request_file=$instance/memory-load-batch.json
  local retry_request_file=$instance/rejected-write.json
  local rss_before=''
  local rss_rejected=''
  local rss_recovered=''
  local cgroup_current=''
  local cgroup_recovered=''
  local quota_response=''
  local quota_percent=''
  local rejection_error=''
  local load_rejection_error=''
  local load_rejection_http_code=''
  local threshold_trigger=''
  local load_batch_ids='[]'
  local rejected_load_batch='{"applicable":false,"ids":[],"ids_count":0,"absent":true}'
  local pre_pressure=''
  local post_rejection=''
  local post_release_retry=''
  local post_restart=''
  integer rss_percent=0
  integer batch=0
  integer request_status=0
  integer start_id=100000
  integer threshold_reached=0
  integer load_batch_rejected=0

  config=$(write_pressure_config "$instance" "$instance/storage")
  start_server "$binary" 1.19.0 "$instance" "$config"
  api_json PUT '/collections/pressure-anchor' \
    '{"vectors":{"size":4,"distance":"Cosine"}}' >/dev/null
  api_json PUT '/collections/pressure-anchor/points?wait=true' \
    '{"points":[{"id":1,"vector":[1,0,0,0],"payload":{"lane":"memory","state":"accepted"}}]}' >/dev/null
  pre_pressure=$(pressure_collection_fingerprint pressure-anchor)
  rss_before=$(process_rss_bytes $MIGRATION_ACTIVE_PID)
  cgroup_current=$(cgroup_memory_current)
  quota_response=$(api_json GET '/quotas')
  quota_percent=$(print -r -- "$quota_response" | jq -er '.result.usage.resident_memory_percent')
  (( quota_percent < 80 )) ||
    fail "memory-pressure server started above its configured product quota: $quota_percent%"
  record_event memory_below_threshold_write resource_pressure "$(jq -nc \
    --argjson observed_percent "$quota_percent" --argjson rss_bytes "$rss_before" \
    --argjson cgroup_current_bytes "$cgroup_current" \
    --argjson cgroup_limit_bytes "$MIGRATION_CGROUP_MEMORY_MAX" \
    --argjson fingerprint "$pre_pressure" \
    '{resource:"memory",configured_threshold_percent:80,observed_percent:$observed_percent,
      rss_bytes:$rss_bytes,cgroup_current_bytes:$cgroup_current_bytes,
      cgroup_limit_bytes:$cgroup_limit_bytes,write_succeeded:true,collection:"pressure-anchor",
      pre_pressure:$fingerprint}')"

  api_json PUT '/collections/pressure-memory-load' \
    '{"vectors":{},"sparse_vectors":{"sparse":{}}}' >/dev/null

  for batch in {0..160}; do
    (( batch > 0 )) && sleep 1.2
    start_id=$(( 100000 + batch * 100 ))
    load_batch_ids=$(memory_pressure_batch_ids_json "$start_id")
    write_memory_pressure_batch "$load_request_file" $start_id
    request_status=0
    attempt_json_file PUT '/collections/pressure-memory-load/points?wait=true' \
      "$load_request_file" || request_status=$?
    rss_rejected=$(process_rss_bytes $MIGRATION_ACTIVE_PID)
    cgroup_current=$(cgroup_memory_current)
    quota_response=$(api_json GET '/quotas')
    quota_percent=$(print -r -- "$quota_response" | jq -er '.result.usage.resident_memory_percent')
    if [[ $MIGRATION_LAST_HTTP_CODE == 200 ]] &&
      print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -e '.status == "ok"' >/dev/null 2>&1; then
      if (( quota_percent >= 80 )); then
        threshold_reached=1
        threshold_trigger=quota_observed_after_accepted_load
        break
      fi
    elif [[ $MIGRATION_LAST_HTTP_CODE == 4<-> || $MIGRATION_LAST_HTTP_CODE == 5<-> ]] &&
      print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -e \
        '.status.error | type == "string" and test("resident memory usage|max_resident_memory_percent|memory quota"; "i")' >/dev/null 2>&1; then
      load_batch_rejected=1
      load_rejection_http_code=$MIGRATION_LAST_HTTP_CODE
      load_rejection_error=$(print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -er '.status.error')
      require_active_process_running 'after safely rejecting a memory load batch'
      rejected_load_batch=$(verify_rejected_batch_absent \
        pressure-memory-load "$load_batch_ids")
      (( quota_percent >= 80 )) ||
        fail "memory load quota rejected before the authoritative usage reached 80%: $quota_percent%"
      threshold_reached=1
      threshold_trigger=quota_observed_after_rejected_load
      break
    else
      fail "memory load generation failed without a quota rejection: HTTP ${MIGRATION_LAST_HTTP_CODE:-<none>}"
    fi
    (( cgroup_current < ISOLATED_MEMORY_HIGH_BYTES )) ||
      fail "memory pressure reached the cgroup high boundary without a Qdrant quota rejection: product quota $quota_percent% (RSS $rss_rejected bytes; cgroup $cgroup_current bytes)"
  done
  (( threshold_reached )) || fail 'memory pressure did not reach the configured product threshold'

  print -r -- '{"points":[{"id":2,"vector":[0,1,0,0],"payload":{"lane":"memory","state":"retried"}}]}' >| "$retry_request_file"
  attempt_json_file PUT '/collections/pressure-anchor/points?wait=true' "$retry_request_file" || request_status=$?
  [[ $MIGRATION_LAST_HTTP_CODE == 4<-> || $MIGRATION_LAST_HTTP_CODE == 5<-> ]] ||
    fail "memory-pressure target write was not rejected at the product threshold: HTTP ${MIGRATION_LAST_HTTP_CODE:-<none>}"
  print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -e \
    '.status.error | type == "string" and test("resident memory usage|max_resident_memory_percent|memory quota"; "i")' >/dev/null ||
    fail 'memory-pressure rejection did not come from the configured quota gate'
  rejection_error=$(print -r -- "$MIGRATION_LAST_HTTP_BODY" | jq -er '.status.error')
  require_active_process_running 'after safely rejecting memory pressure'
  rss_rejected=$(process_rss_bytes $MIGRATION_ACTIVE_PID)
  cgroup_current=$(cgroup_memory_current)
  quota_response=$(api_json GET '/quotas')
  quota_percent=$(print -r -- "$quota_response" | jq -er '.result.usage.resident_memory_percent')
  (( quota_percent >= 80 )) || fail "memory quota rejected below its configured threshold: $quota_percent%"
  post_rejection=$(pressure_collection_fingerprint pressure-anchor)
  [[ $post_rejection == $pre_pressure ]] ||
    fail 'memory-pressure rejection changed the accepted point set or payload'
  record_event memory_above_threshold_rejection resource_pressure "$(jq -nc \
    --argjson rss_bytes "$rss_rejected" --argjson cgroup_limit_bytes "$MIGRATION_CGROUP_MEMORY_MAX" \
    --argjson cgroup_current_bytes "$cgroup_current" \
    --argjson observed_percent "$quota_percent" --arg http_code "$MIGRATION_LAST_HTTP_CODE" \
    --arg error "$rejection_error" --argjson fingerprint "$post_rejection" \
    --argjson load_batch_rejected "$(json_boolean_from_integer "$load_batch_rejected")" \
    --arg load_rejection_http_code "$load_rejection_http_code" \
    --arg load_rejection_error "$load_rejection_error" --arg threshold_trigger "$threshold_trigger" \
    --argjson rejected_load_batch "$rejected_load_batch" \
    '{resource:"memory",configured_threshold_percent:80,observed_percent:$observed_percent,
      rss_bytes:$rss_bytes,cgroup_current_bytes:$cgroup_current_bytes,
      cgroup_limit_bytes:$cgroup_limit_bytes,http_code:$http_code,error:$error,
      rejected:true,rejected_id:2,rejected_ids_absent:true,server_remained_ready:true,
      threshold_trigger:$threshold_trigger,load_batch_rejected:$load_batch_rejected,
      load_rejection_http_code:(if $load_batch_rejected then $load_rejection_http_code else null end),
      load_rejection_error:(if $load_batch_rejected then $load_rejection_error else null end),
      rejected_load_batch:$rejected_load_batch,
      post_rejection:$fingerprint}')"

  api_json DELETE '/collections/pressure-memory-load' >/dev/null
  stop_server
  start_server "$binary" 1.19.0 "$instance" "$config"
  for batch in {1..60}; do
    quota_response=$(api_json GET '/quotas')
    quota_percent=$(print -r -- "$quota_response" | jq -er '.result.usage.resident_memory_percent')
    rss_recovered=$(process_rss_bytes $MIGRATION_ACTIVE_PID)
    cgroup_recovered=$(cgroup_memory_current)
    (( quota_percent < 70 )) && break
    sleep 1.5
  done
  (( quota_percent < 70 )) ||
    fail "memory pressure did not recover below the product quota release margin after restart: $quota_percent% (RSS $rss_recovered bytes; cgroup $cgroup_recovered bytes)"
  api_json_file PUT '/collections/pressure-anchor/points?wait=true' "$retry_request_file" >/dev/null
  post_release_retry=$(pressure_collection_fingerprint pressure-anchor)
  rss_percent=$(( rss_recovered * 100 / MIGRATION_CGROUP_MEMORY_MAX ))
  record_event memory_release_margin_recovery resource_pressure "$(jq -nc \
    --argjson observed_percent "$quota_percent" --argjson rss_bytes "$rss_recovered" \
    --argjson raw_rss_percent_of_cgroup_limit "$rss_percent" \
    --argjson cgroup_current_bytes "$cgroup_recovered" \
    --argjson cgroup_limit_bytes "$MIGRATION_CGROUP_MEMORY_MAX" \
    --argjson fingerprint "$post_release_retry" \
    '{resource:"memory",usage_authority:"GET /quotas result.usage.resident_memory_percent",
      release_below_percent:70,observed_percent:$observed_percent,rss_bytes:$rss_bytes,
      raw_rss_percent_of_cgroup_limit:$raw_rss_percent_of_cgroup_limit,
      raw_rss_below_release_percent:($raw_rss_percent_of_cgroup_limit < 70),
      cgroup_current_bytes:$cgroup_current_bytes,cgroup_limit_bytes:$cgroup_limit_bytes,
      retry_succeeded:true,retried_id:2,post_release_retry:$fingerprint}')"
  stop_server
  start_server "$binary" 1.19.0 "$instance" "$config"
  post_restart=$(pressure_collection_fingerprint pressure-anchor)
  record_pressure_integrity memory memory_integrity_after_pressure 2 \
    "$pre_pressure" "$post_rejection" "$post_release_retry" "$post_restart"
  stop_server
}

record_isolation_event() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  record_event isolation_boundary isolation "$(jq -nc \
    --argjson memory_max "$MIGRATION_CGROUP_MEMORY_MAX" \
    --argjson memory_high "$MIGRATION_CGROUP_MEMORY_HIGH" \
    --argjson runtime_max_sec "$TRANSIENT_RUNTIME_MAX_SEC" \
    --argjson timeout_stop_sec "$TRANSIENT_TIMEOUT_STOP_SEC" \
    '{boundary:"systemd-run+bwrap",environment_cleared:true,user_namespace:true,mount_namespace:true,pid_namespace:true,network_namespace:true,network_namespace_identity_checked:true,network_namespace_distinct:true,loopback_bind_allowed:true,non_loopback_egress_denied:true,host_sensitive_roots_absent:true,host_root_bound:false,runtime_view:["/usr","/proc","/dev","/sys/fs/cgroup","/etc/ssl/certs/ca-certificates.crt","/tmp/<work-root>","/run/qdrant-inputs"],transient_unit_policy:{runtime_max_sec:$runtime_max_sec,timeout_stop_sec:$timeout_stop_sec,kill_mode:"control-group",send_sigkill:true,wait:true,collect:true,outer_keepalive_supervisor:true},cgroup_membership_verified:true,cgroup_path:"<transient-user-unit>",memory_max_bytes:$memory_max,memory_high_bytes:$memory_high}')"
}

record_cold_migration() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local event_id=$1
  local source_version=$2
  local target_version=$3
  local cold_copy=$4
  record_event "$event_id" migration "$(jq -nc \
    --arg source_version "$source_version" --arg target_version "$target_version" \
    --arg cold_copy "${cold_copy:t}" \
    --arg query_fingerprint_sha256 "$MIGRATION_QUERY_SET_SHA256" \
    '{source_version:$source_version,target_version:$target_version,cold_copy:$cold_copy,query_fingerprint_sha256:$query_fingerprint_sha256,metadata_verified:true,point_count_verified:true,alias_verified:true,stable_ids_verified:true,dense_sparse_hybrid_equivalent:true,restart_verified:true}')"
}

restore_full_storage_snapshot() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local binary=$1
  local target_version=$2
  local source_version=$3
  local snapshot=$4
  local instance=$5
  local event_id=$6
  local config=''
  local snapshot_before=''
  snapshot_before=$(file_sha256 "$snapshot")
  config=$(write_config "$instance")
  start_server "$binary" "$target_version" "$instance" "$config" \
    --storage-snapshot "$snapshot"
  verify_fixture
  restart_and_verify "$binary" "$target_version" "$instance" "$config"
  stop_server
  [[ $(file_sha256 "$snapshot") == $snapshot_before ]] ||
    fail 'full-storage snapshot changed during restore verification'
  record_event "$event_id" restore "$(jq -nc \
    --arg source_version "$source_version" --arg target_version "$target_version" \
    --arg snapshot "${snapshot:t}" --arg snapshot_sha256 "$snapshot_before" \
    --arg query_fingerprint_sha256 "$MIGRATION_QUERY_SET_SHA256" \
    '{kind:"full_storage",source_version:$source_version,target_version:$target_version,snapshot:$snapshot,snapshot_sha256:$snapshot_sha256,query_fingerprint_sha256:$query_fingerprint_sha256,retrieval_equivalent:true,restart_verified:true}')"
}

verify_final_cleanup() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local api_key=$1
  local secret_matches=''
  local process_names=''
  integer grep_status=0

  cleanup
  [[ -z $MIGRATION_ACTIVE_PID ]] || fail 'owned Qdrant child remained registered after cleanup'
  validate_ports_available
  process_names=$(ps -e -o comm=)
  print -r -- "$process_names" | grep -qx qdrant &&
    fail 'a Qdrant process remained in the disposable PID namespace after cleanup'
  secret_matches=$(grep -R -I -F -l -- "$api_key" "$MIGRATION_WORK_ROOT" 2>/dev/null) || grep_status=$?
  (( grep_status == 1 )) || {
    (( grep_status == 0 )) && fail "ephemeral API key persisted in: $secret_matches"
    fail 'ephemeral API-key persistence scan failed'
  }
  record_event final_cleanup_verified cleanup \
    '{"owned_processes_stopped":true,"http_listener_absent":true,"grpc_listener_absent":true,"ephemeral_api_key_cleared":true,"persisted_text_secret_matches":0}'
}

command_version_line() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local output=''
  output=$("$@" 2>&1) || fail "could not capture tool version: ${(@q)argv}"
  output=${output%%$'\n'*}
  [[ -n $output ]] || fail "tool returned an empty version string: ${(@q)argv}"
  print -r -- "$output"
}

validate_candidate_artifact_bindings() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local candidate_json=$1
  print -r -- "$candidate_json" | jq -e '
    (.tool.sha256) as $tool_sha256
    | (.binaries | map(.binary_sha256)) as $binary_sha256
    | [.events[] | select(.id == "fixture_schema_verified") | .details.schema_sha256] as $schema_events
    | ($schema_events | length) == 1
      and .inputs.storage_seed.payload_schema_sha256 == $schema_events[0]
      and (.inputs.interrupt_receipts | length) == 2
      and all(.inputs.interrupt_receipts[];
        .target.tool_sha256 == $tool_sha256
        and .inputs.binary_sha256 == $binary_sha256)
    ' >/dev/null || fail 'candidate artifact, receipt, or storage-seed bindings disagree'
}

validate_promotion_delta() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local final_json=$1
  local candidate_sha256=$2
  print -r -- "$final_json" | jq -e --arg candidate_sha256 "$candidate_sha256" '
    .disposition == "accepted"
    and .runtime_candidate_sha256 == $candidate_sha256
    and .promotion_delta == {
      candidate_sha256:$candidate_sha256,
      disposition:{from:"runtime_validated",to:"accepted"},
      added_paths:["cleanup.transient_unit","promotion_delta","runtime_candidate_sha256"],
      removed_paths:[]
    }
  ' >/dev/null || fail 'candidate promotion delta is not exact'
}

write_runtime_evidence_candidate() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local qdrant_1_17=$1
  local qdrant_1_18=$2
  local qdrant_1_19=$3
  local evidence_root=$MIGRATION_WORK_ROOT/evidence
  local config_ledger=$evidence_root/configs.jsonl
  local runtime_candidate=$evidence_root/manifest.runtime-validated.json
  local required_json=''
  local events_json=''
  local configs_json=''
  local event_id=''
  local count=''
  local config=''
  local relative=''
  local runtime_json=''
  local candidate_json=''
  local invocation=''
  local int_receipt_copy=$evidence_root/interrupt-INT.json
  local term_receipt_copy=$evidence_root/interrupt-TERM.json
  local interrupt_receipts=''
  local q17_sha=''
  local q18_sha=''
  local q19_sha=''
  local tool_sha256=''

  q17_sha=$(file_sha256 "$qdrant_1_17")
  q18_sha=$(file_sha256 "$qdrant_1_18")
  q19_sha=$(file_sha256 "$qdrant_1_19")
  tool_sha256=$(file_sha256 "$MIGRATION_SCRIPT_PATH")
  [[ $q17_sha == $MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256 &&
    $q18_sha == $MIGRATION_QDRANT_1_18_BINARY_SHA256 &&
    $q19_sha == $MIGRATION_QDRANT_1_19_BINARY_SHA256 &&
    $tool_sha256 == $MIGRATION_TOOL_SHA256 ]] ||
    fail 'tool or binary bytes changed after prerequisite receipt validation'

  [[ -n $MIGRATION_INT_RECEIPT && -n $MIGRATION_TERM_RECEIPT &&
    -n $MIGRATION_INT_RECEIPT_SHA256 && -n $MIGRATION_TERM_RECEIPT_SHA256 ]] ||
    fail 'accepted INT and TERM receipts are required before runtime evidence'
  cp -- "$MIGRATION_INT_RECEIPT" "$int_receipt_copy"
  cp -- "$MIGRATION_TERM_RECEIPT" "$term_receipt_copy"
  chmod 600 -- "$int_receipt_copy" "$term_receipt_copy"
  [[ $(file_sha256 "$int_receipt_copy") == $MIGRATION_INT_RECEIPT_SHA256 &&
    $(file_sha256 "$term_receipt_copy") == $MIGRATION_TERM_RECEIPT_SHA256 ]] ||
    fail 'retained interrupt receipt bytes changed during evidence capture'
  interrupt_receipts=$(jq -nc \
    --argjson int "$(<"$int_receipt_copy")" --argjson term "$(<"$term_receipt_copy")" \
    --arg int_sha256 "$MIGRATION_INT_RECEIPT_SHA256" \
    --arg term_sha256 "$MIGRATION_TERM_RECEIPT_SHA256" '
      [($int + {receipt_name:"interrupt-INT.json",receipt_sha256:$int_sha256}),
       ($term + {receipt_name:"interrupt-TERM.json",receipt_sha256:$term_sha256})]')

  for event_id in $required_g3_obligations; do
    count=$(jq -s --arg id "$event_id" \
      '[.[] | select(.id == $id and .status == "pass")] | length' \
      "$MIGRATION_EVENTS_FILE")
    [[ $count == 1 ]] || fail "missing required G3 evidence: $event_id"
  done
  jq -s -e 'all(.[]; .status == "pass")' "$MIGRATION_EVENTS_FILE" >/dev/null ||
    fail 'evidence ledger contains a failed or inconclusive result'

  : >| "$config_ledger"
  while IFS= read -r -d '' config; do
    relative=${config#$MIGRATION_WORK_ROOT/}
    jq -nc --arg name "${config:t}" --arg path "$relative" \
      --arg config_sha256 "$(file_sha256 "$config")" \
      '{name:$name,path:$path,config_sha256:$config_sha256}' >> "$config_ledger"
  done < <(find "$MIGRATION_WORK_ROOT" -type f \
    \( -name 'qdrant.yaml' -o -name 'qdrant-pressure.yaml' \) -print0 | sort -z)
  [[ -s $config_ledger ]] || fail 'no configuration evidence was captured'
  chmod 600 -- "$config_ledger"

  required_json=$(printf '%s\n' $required_g3_obligations | jq -Rsc 'split("\n")[:-1]')
  events_json=$(jq -s '.' "$MIGRATION_EVENTS_FILE")
  configs_json=$(jq -s '.' "$config_ledger")
  invocation="tools/validate_qdrant_migration.zsh --execute --work-root /tmp/<fresh-work-root> --http-port $MIGRATION_HTTP_PORT --grpc-port $MIGRATION_GRPC_PORT --qdrant-1.17.1-package /run/qdrant-inputs/qdrant-1.17.1-1-x86_64.pkg.tar.zst --qdrant-1.17.1 /run/qdrant-inputs/qdrant-1.17.1 --qdrant-1.18.3 /run/qdrant-inputs/qdrant-1.18.3 --qdrant-1.19.0 /run/qdrant-inputs/qdrant-1.19.0"
  runtime_json=$(jq -nc --arg kernel "$(uname -srmo)" \
    --arg filesystem "$(findmnt -n -o FSTYPE --target "$MIGRATION_WORK_ROOT")" \
    --arg completed_at "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --arg invocation "$invocation" \
    --arg zsh "$(command_version_line zsh --version)" \
    --arg bwrap "$(command_version_line bwrap --version)" \
    --arg systemd "$(command_version_line systemd-run --version)" \
    --arg curl "$(command_version_line curl --version)" \
    --arg jq "$(command_version_line jq --version)" \
    --arg openssl "$(command_version_line openssl version)" \
    --arg qdrant_1_17 "$(command_version_line "$qdrant_1_17" --version)" \
    --arg qdrant_1_18 "$(command_version_line "$qdrant_1_18" --version)" \
    --arg qdrant_1_19 "$(command_version_line "$qdrant_1_19" --version)" \
    '{kernel:$kernel,work_root_filesystem:$filesystem,completed_at:$completed_at,
      invocation:{mode:"--execute",command:$invocation,work_root:"/tmp/<fresh-work-root>",binary_root:"/run/qdrant-inputs"},
      tool_versions:{zsh:$zsh,bwrap:$bwrap,systemd:$systemd,curl:$curl,jq:$jq,openssl:$openssl,qdrant_1_17_1:$qdrant_1_17,qdrant_1_18_3:$qdrant_1_18,qdrant_1_19_0:$qdrant_1_19}}')

  candidate_json=$(jq -n \
    --arg schema "$EVIDENCE_SCHEMA" \
    --argjson required "$required_json" \
    --argjson events "$events_json" \
    --argjson configs "$configs_json" \
    --argjson runtime "$runtime_json" \
    --argjson interrupt_receipts "$interrupt_receipts" \
    --arg q17_name "${qdrant_1_17:t}" --arg q17_path "$qdrant_1_17" \
    --arg q17_sha "$q17_sha" \
    --arg q18_name "${qdrant_1_18:t}" --arg q18_path "$qdrant_1_18" \
    --arg q18_sha "$q18_sha" \
    --arg q19_name "${qdrant_1_19:t}" --arg q19_path "$qdrant_1_19" \
    --arg q19_sha "$q19_sha" \
    --arg tool_sha256 "$tool_sha256" \
    --arg package_name "$QDRANT_1_17_PACKAGE_NAME" \
    --arg package_sha256 "$MIGRATION_QDRANT_1_17_PACKAGE_SHA256" \
    --argjson package_size "$MIGRATION_QDRANT_1_17_PACKAGE_SIZE" \
    --arg package_binary_sha256 "$MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256" \
    --arg package_config_sha256 "$MIGRATION_QDRANT_1_17_CONFIG_SHA256" \
    --arg fixture_spec_sha256 "$MIGRATION_FIXTURE_SPEC_SHA256" \
    --arg fixture_points_sha256 "$MIGRATION_FIXTURE_POINTS_SHA256" \
    --arg fixture_ids_sha256 "$MIGRATION_FIXTURE_IDS_SHA256" \
    --arg fixture_schema_sha256 "$MIGRATION_FIXTURE_SCHEMA_SHA256" \
    --argjson fixture_point_count $FIXTURE_POINT_COUNT \
    --arg events_sha256 "$(file_sha256 "$MIGRATION_EVENTS_FILE")" \
    --argjson http_port "$MIGRATION_HTTP_PORT" --argjson grpc_port "$MIGRATION_GRPC_PORT" \
    '{
      schema:$schema,
      disposition:"pending_validation",
      tool:{name:"tools/validate_qdrant_migration.zsh",sha256:$tool_sha256},
      binaries:[
        {version:"1.17.1",name:$q17_name,path:$q17_path,binary_sha256:$q17_sha},
        {version:"1.18.3",name:$q18_name,path:$q18_path,binary_sha256:$q18_sha},
        {version:"1.19.0",name:$q19_name,path:$q19_path,binary_sha256:$q19_sha}
      ],
      inputs:{
        retained_baseline:{
          package_name:$package_name,package_name_metadata:"qdrant",package_version:"1.17.1-1",
          package_arch:"x86_64",package_archive_sha256:$package_sha256,package_archive_size:$package_size,
          package_binary_sha256:$package_binary_sha256,package_config_path:"etc/qdrant/config.yaml",
          package_config_sha256:$package_config_sha256,supplied_binary_byte_identical:true
        },
        storage_seed:{
          specification:"qdrant-migration-fixture/v2",fixture_spec_sha256:$fixture_spec_sha256,
          fixture_points_sha256:$fixture_points_sha256,ordered_point_ids_sha256:$fixture_ids_sha256,
          payload_schema_sha256:$fixture_schema_sha256,point_count:$fixture_point_count
        },
        interrupt_receipts:$interrupt_receipts,
        configs:$configs,
        snapshots:[$events[] | select(.category == "snapshot") | .details],
        cold_copies:[$events[] | select(.category == "cold_copy") | .details]
      },
      query_fingerprints:($events[] | select(.id == "fixture_queries_captured") | {results:.details.query_fingerprints,sha256:.details.query_fingerprint_sha256}),
      restore_outcomes:[$events[] | select(.category == "restore" or .category == "retry")],
      rejection_outcomes:[$events[] | select(.category == "rejection")],
      resource_pressure:[$events[] | select(.category == "resource_pressure")],
      ports:{http:$http_port,grpc:$grpc_port,host:"127.0.0.1",loopback_only:true},
      isolation:($events[] | select(.id == "isolation_boundary") | .details),
      cleanup:($events[] | select(.id == "final_cleanup_verified") | .details),
      required_g3_obligations:$required,
      obligation_results:[$events[] | select(.id as $id | $required | index($id))],
      events:$events,
      events_sha256:$events_sha256,
      runtime:$runtime
    }')

  print -r -- "$candidate_json" | jq -e --arg schema "$EVIDENCE_SCHEMA" \
    --argjson required "$required_json" --arg tool_sha "$MIGRATION_TOOL_SHA256" \
    --arg fixture_spec_sha "$MIGRATION_FIXTURE_SPEC_SHA256" '
    def pressure($id):
      [.resource_pressure[] | select(.id == $id)]
      | if length == 1 then .[0].details else null end;
    (.binaries | map(.binary_sha256)) as $binary_sha256
    | .schema == $schema
    and .disposition == "pending_validation"
    and (.tool.sha256 | test("^[0-9a-f]{64}$"))
    and (.binaries | length == 3 and all(.[]; (.binary_sha256 | test("^[0-9a-f]{64}$"))))
    and .inputs.retained_baseline.package_name == "qdrant-1.17.1-1-x86_64.pkg.tar.zst"
    and .inputs.retained_baseline.package_name_metadata == "qdrant"
    and .inputs.retained_baseline.package_version == "1.17.1-1"
    and .inputs.retained_baseline.package_arch == "x86_64"
    and .inputs.retained_baseline.package_archive_sha256 == "d237ac6b804c7b4ec3f73f8ef57340ebaba62abff7853636286f140c8affd5cb"
    and .inputs.retained_baseline.package_archive_size == 25531392
    and .inputs.retained_baseline.package_binary_sha256 == .binaries[0].binary_sha256
    and (.inputs.retained_baseline.package_config_sha256 | test("^[0-9a-f]{64}$"))
    and .inputs.retained_baseline.supplied_binary_byte_identical
    and .inputs.storage_seed.specification == "qdrant-migration-fixture/v2"
    and .inputs.storage_seed.point_count == 1001
    and (all(.inputs.storage_seed[] | select(type == "string" and . != "qdrant-migration-fixture/v2"); test("^[0-9a-f]{64}$")))
    and ([.events[] | select(.id == "fixture_schema_verified") | .details.schema_sha256] as $schemas
      | ($schemas | length) == 1
      and .inputs.storage_seed.payload_schema_sha256 == $schemas[0])
    and (.inputs.interrupt_receipts | length == 2)
    and .inputs.interrupt_receipts[0].signal == "INT"
    and .inputs.interrupt_receipts[0].conventional_exit_status == 130
    and .inputs.interrupt_receipts[1].signal == "TERM"
    and .inputs.interrupt_receipts[1].conventional_exit_status == 143
    and all(.inputs.interrupt_receipts[];
      .disposition == "accepted"
      and (.receipt_sha256 | test("^[0-9a-f]{64}$"))
      and .target.kind == "outer-validation-process"
      and (.target.target_executable_sha256 | test("^[0-9a-f]{64}$"))
      and .target.tool_sha256 == $tool_sha
      and .inputs.fixture_spec_sha256 == $fixture_spec_sha
      and .inputs.binary_sha256 == $binary_sha256
      and .inputs.package_archive_sha256 == "d237ac6b804c7b4ec3f73f8ef57340ebaba62abff7853636286f140c8affd5cb"
      and .pre_interrupt.synchronized_ready_marker
      and (.pre_interrupt.readiness_marker_sha256 | test("^[0-9a-f]{64}$"))
      and .pre_interrupt.owned_process_observed
      and .pre_interrupt.isolated_http_listener_observed
      and .pre_interrupt.isolated_grpc_listener_observed
      and .pre_interrupt.isolated_network_namespace_observed
      and .candidate_absent and .accepted_manifest_absent
      and .cleanup.status == "passed" and .cleanup.failure == "none"
      and .cleanup.owned_processes_absent and .cleanup.owned_listeners_absent
      and .cleanup.owned_unit_absent and .cleanup.owned_cgroup_absent
      and .cleanup.collection_wait_completed
      and .cleanup.collection_wait_status == 143
      and .cleanup.collection_wait_status_expected == 143
      and .cleanup.collection_wait_unit_matched
      and .cleanup.collection_client_reaped
      and .cleanup.collection_cgroup_identity_matched
      and .cleanup.collection_receipt_exact)
    and (.inputs.configs | length > 0 and all(.[]; (.config_sha256 | test("^[0-9a-f]{64}$"))))
    and (.inputs.snapshots | length >= 5 and all(.[]; (.snapshot_sha256 | test("^[0-9a-f]{64}$"))))
    and (.inputs.cold_copies | length >= 3 and all(.[]; (.cold_copy_manifest_sha256 | test("^[0-9a-f]{64}$"))))
    and (.query_fingerprints.results | keys | sort == ["dense","hybrid","sparse"])
    and (.query_fingerprints.sha256 | test("^[0-9a-f]{64}$"))
    and (.restore_outcomes | length >= 10 and all(.[]; (.details.query_fingerprint_sha256 | test("^[0-9a-f]{64}$"))))
    and (.rejection_outcomes | length == 4 and all(.[];
      ((.details.source_snapshot_sha256 // .details.snapshot_sha256) | test("^[0-9a-f]{64}$"))
      and (if .details.kind == "truncated"
        then (.details.rejection_log_sha256 | test("^[0-9a-f]{64}$")) and .details.rejection_marker == "Failed to recover snapshot"
        else (.details.error | test("checksum"; "i"))
      end)))
    and (.resource_pressure | map(.id) | sort == [
      "disk_above_threshold_rejection",
      "disk_below_threshold_write",
      "disk_integrity_after_pressure",
      "disk_release_margin_recovery",
      "memory_above_threshold_rejection",
      "memory_below_threshold_write",
      "memory_integrity_after_pressure",
      "memory_release_margin_recovery"
    ])
    and (pressure("disk_below_threshold_write") as $p
      | $p.resource == "disk"
      and $p.configured_threshold_percent == 85
      and (($p.observed_percent | type) == "number")
      and $p.observed_percent < 85
      and $p.write_succeeded)
    and (pressure("disk_above_threshold_rejection") as $p
      | $p.resource == "disk"
      and $p.configured_threshold_percent == 85
      and (($p.observed_percent | type) == "number")
      and $p.observed_percent >= 85
      and ($p.http_code | test("^[45][0-9]{2}$"))
      and (($p.error | type) == "string" and ($p.error | length) > 0)
      and $p.rejected
      and $p.server_remained_ready)
    and (pressure("disk_release_margin_recovery") as $p
      | $p.resource == "disk"
      and $p.release_below_percent == 75
      and (($p.observed_percent | type) == "number")
      and $p.observed_percent < $p.release_below_percent
      and $p.retry_succeeded)
    and (pressure("memory_below_threshold_write") as $p
      | $p.resource == "memory"
      and $p.configured_threshold_percent == 80
      and (($p.observed_percent | type) == "number")
      and $p.observed_percent < 80
      and (($p.rss_bytes | type) == "number" and $p.rss_bytes > 0)
      and (($p.cgroup_current_bytes | type) == "number" and $p.cgroup_current_bytes > 0)
      and $p.cgroup_limit_bytes == 536870912
      and $p.cgroup_current_bytes <= $p.cgroup_limit_bytes
      and $p.write_succeeded)
    and (pressure("memory_above_threshold_rejection") as $p
      | $p.resource == "memory"
      and $p.configured_threshold_percent == 80
      and (($p.observed_percent | type) == "number")
      and $p.observed_percent >= 80
      and (($p.rss_bytes | type) == "number" and $p.rss_bytes > 0)
      and (($p.cgroup_current_bytes | type) == "number" and $p.cgroup_current_bytes > 0)
      and $p.cgroup_limit_bytes == 536870912
      and $p.cgroup_current_bytes <= $p.cgroup_limit_bytes
      and ($p.http_code | test("^[45][0-9]{2}$"))
      and (($p.error | type) == "string" and ($p.error | length) > 0)
      and ($p.load_batch_rejected | type) == "boolean"
      and ($p.threshold_trigger == "quota_observed_after_accepted_load"
        or $p.threshold_trigger == "quota_observed_after_rejected_load")
      and (if $p.load_batch_rejected then
        ($p.load_rejection_http_code | test("^[45][0-9]{2}$"))
        and (($p.load_rejection_error | type) == "string" and ($p.load_rejection_error | length) > 0)
        and $p.threshold_trigger == "quota_observed_after_rejected_load"
        and $p.rejected_load_batch.applicable
        and $p.rejected_load_batch.collection == "pressure-memory-load"
        and $p.rejected_load_batch.ids_count == 100
        and ($p.rejected_load_batch.ids | length) == 100
        and ($p.rejected_load_batch.ids | unique | length) == 100
        and ($p.rejected_load_batch.ids_sha256 | test("^[0-9a-f]{64}$"))
        and $p.rejected_load_batch.observed_existing_points == []
        and ($p.rejected_load_batch.observed_existing_points_sha256 | test("^[0-9a-f]{64}$"))
        and $p.rejected_load_batch.absent
      else
        $p.load_rejection_http_code == null
        and $p.load_rejection_error == null
        and $p.threshold_trigger == "quota_observed_after_accepted_load"
        and ($p.rejected_load_batch == {applicable:false,ids:[],ids_count:0,absent:true})
      end)
      and $p.rejected
      and $p.server_remained_ready)
    and (pressure("memory_release_margin_recovery") as $p
      | $p.resource == "memory"
      and $p.usage_authority == "GET /quotas result.usage.resident_memory_percent"
      and $p.release_below_percent == 70
      and (($p.observed_percent | type) == "number")
      and $p.observed_percent < $p.release_below_percent
      and (($p.rss_bytes | type) == "number" and $p.rss_bytes > 0)
      and (($p.raw_rss_percent_of_cgroup_limit | type) == "number")
      and $p.raw_rss_below_release_percent == ($p.raw_rss_percent_of_cgroup_limit < $p.release_below_percent)
      and (($p.cgroup_current_bytes | type) == "number" and $p.cgroup_current_bytes > 0)
      and $p.cgroup_limit_bytes == 536870912
      and $p.cgroup_current_bytes <= $p.cgroup_limit_bytes
      and $p.retry_succeeded)
    and (pressure("disk_integrity_after_pressure") as $p
      | $p.resource == "disk"
      and $p.exact_points
      and $p.rejected_ids_absent
      and $p.rejected_batch_absent
      and ($p.rejected_ids_sha256 | test("^[0-9a-f]{64}$"))
      and ($p.retried_points_sha256 | test("^[0-9a-f]{64}$"))
      and ($p.retried_points | map(.id)) == $p.rejected_ids
      and $p.rejection_preserved_exact_fingerprint
      and $p.restart_preserved_exact_fingerprint
      and $p.stages.pre_pressure == $p.stages.post_rejection
      and $p.stages.post_release_retry == $p.stages.post_restart
      and $p.stages.post_release_retry.exact_points
        == (($p.stages.pre_pressure.exact_points + $p.retried_points) | sort_by(.id))
      and all($p.stages[];
        (.point_count | type) == "number"
        and (.points_sha256 | test("^[0-9a-f]{64}$"))
        and (.exact_points | length) == .point_count))
    and (pressure("memory_integrity_after_pressure") as $p
      | $p.resource == "memory"
      and $p.exact_points
      and $p.rejected_ids_absent
      and $p.rejected_batch_absent
      and ($p.rejected_ids_sha256 | test("^[0-9a-f]{64}$"))
      and ($p.retried_points_sha256 | test("^[0-9a-f]{64}$"))
      and ($p.retried_points | map(.id)) == $p.rejected_ids
      and $p.rejection_preserved_exact_fingerprint
      and $p.restart_preserved_exact_fingerprint
      and $p.stages.pre_pressure == $p.stages.post_rejection
      and $p.stages.post_release_retry == $p.stages.post_restart
      and $p.stages.post_release_retry.exact_points
        == (($p.stages.pre_pressure.exact_points + $p.retried_points) | sort_by(.id))
      and all($p.stages[];
        (.point_count | type) == "number"
        and (.points_sha256 | test("^[0-9a-f]{64}$"))
        and (.exact_points | length) == .point_count))
    and .isolation.loopback_bind_allowed
    and .isolation.non_loopback_egress_denied
    and .isolation.host_sensitive_roots_absent
    and (.isolation.host_root_bound == false)
    and .isolation.transient_unit_policy.runtime_max_sec == 900
    and .isolation.transient_unit_policy.timeout_stop_sec == 30
    and .isolation.transient_unit_policy.kill_mode == "control-group"
    and .isolation.transient_unit_policy.send_sigkill
    and .ports.loopback_only
    and .cleanup.owned_processes_stopped
    and .runtime.invocation.mode == "--execute"
    and .runtime.invocation.work_root == "/tmp/<fresh-work-root>"
    and .runtime.invocation.binary_root == "/run/qdrant-inputs"
    and (.runtime.invocation.command | contains("tools/validate_qdrant_migration.zsh --execute"))
    and (.runtime.tool_versions | keys | sort == ["bwrap","curl","jq","openssl","qdrant_1_17_1","qdrant_1_18_3","qdrant_1_19_0","systemd","zsh"])
    and (all(.runtime.tool_versions[]; type == "string" and length > 0))
    and .runtime.tool_versions.qdrant_1_17_1 == "qdrant 1.17.1"
    and .runtime.tool_versions.qdrant_1_18_3 == "qdrant 1.18.3"
    and .runtime.tool_versions.qdrant_1_19_0 == "qdrant 1.19.0"
    and (.required_g3_obligations | sort == ($required | sort))
    and (.obligation_results | length == ($required | length))
    and (all(.obligation_results[]; .status == "pass"))
  ' >/dev/null || fail 'evidence candidate failed its schema and completeness gate'

  validate_candidate_artifact_bindings "$candidate_json"

  print -r -- "$candidate_json" | jq '.disposition = "runtime_validated"' >| "$runtime_candidate"
  chmod 600 -- "$runtime_candidate"
  jq -e --arg schema "$EVIDENCE_SCHEMA" \
    '.schema == $schema and .disposition == "runtime_validated" and .isolation.host_sensitive_roots_absent and .cleanup.owned_processes_stopped' \
    "$runtime_candidate" >/dev/null || fail 'runtime evidence candidate failed its serialization gate'
}

finalize_evidence_after_unit() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local unit_name=$1
  local evidence_root=$MIGRATION_WORK_ROOT/evidence
  local runtime_candidate=$evidence_root/manifest.runtime-validated.json
  local manifest=$evidence_root/manifest.json
  local final_json=''
  local candidate_sha256=''

  [[ -s $runtime_candidate ]] || fail 'runtime-validated evidence candidate is absent'
  validate_candidate_artifact_bindings "$(<"$runtime_candidate")"
  verify_transient_unit_collected "$unit_name"
  candidate_sha256=$(file_sha256 "$runtime_candidate")
  final_json=$(jq -c \
    --arg unit_pattern 'qdrant-migration-<run>.service' \
    --arg candidate_sha256 "$candidate_sha256" \
    --argjson runtime_max_sec "$TRANSIENT_RUNTIME_MAX_SEC" \
    --argjson timeout_stop_sec "$TRANSIENT_TIMEOUT_STOP_SEC" '
      .disposition = "accepted"
      | .runtime_candidate_sha256 = $candidate_sha256
      | .promotion_delta = {
          candidate_sha256:$candidate_sha256,
          disposition:{from:"runtime_validated",to:"accepted"},
          added_paths:["cleanup.transient_unit","promotion_delta","runtime_candidate_sha256"],
          removed_paths:[]
        }
      | .cleanup.transient_unit = {
          name_pattern:$unit_pattern,
          runtime_max_sec:$runtime_max_sec,
          timeout_stop_sec:$timeout_stop_sec,
          kill_mode:"control-group",
          send_sigkill:true,
          outer_keepalive_closed:true,
          owned_systemd_run_client_reaped:true,
          client_exit_status:0,
          wait_completed:true,
          collect_requested:true,
          unit_collected:true,
          owned_unit_absent:true,
          owned_cgroup_absent:true
        }
    ' "$runtime_candidate")
  validate_promotion_delta "$final_json" "$candidate_sha256"
  print -r -- "$final_json" | jq -e --arg schema "$EVIDENCE_SCHEMA" \
    --arg candidate_sha256 "$candidate_sha256" '
      .schema == $schema
      and .disposition == "accepted"
      and .runtime_candidate_sha256 == $candidate_sha256
      and .promotion_delta == {
        candidate_sha256:$candidate_sha256,
        disposition:{from:"runtime_validated",to:"accepted"},
        added_paths:["cleanup.transient_unit","promotion_delta","runtime_candidate_sha256"],
        removed_paths:[]
      }
      and .cleanup.owned_processes_stopped
      and .cleanup.transient_unit.runtime_max_sec == 900
      and .cleanup.transient_unit.timeout_stop_sec == 30
      and .cleanup.transient_unit.kill_mode == "control-group"
      and .cleanup.transient_unit.send_sigkill
      and .cleanup.transient_unit.outer_keepalive_closed
      and .cleanup.transient_unit.owned_systemd_run_client_reaped
      and .cleanup.transient_unit.client_exit_status == 0
      and .cleanup.transient_unit.wait_completed
      and .cleanup.transient_unit.collect_requested
      and .cleanup.transient_unit.unit_collected
      and .cleanup.transient_unit.owned_unit_absent
      and .cleanup.transient_unit.owned_cgroup_absent
      and all(.. | strings;
        (contains("/home/") | not)
        and (contains("/root/") | not)
        and (contains("/etc/qdrant") | not)
        and (contains("/var/lib/qdrant") | not)
        and (test("user-[0-9]+|@[0-9]+\\.service|net:\\[[0-9]+\\]|qdrant-migration-[0-9]+") | not)
        and ((gsub("/tmp/<fresh-work-root>|/tmp/<work-root>"; "")) | contains("/tmp/") | not)
      )
    ' >/dev/null || fail 'outer lifecycle evidence failed its acceptance gate'

  MIGRATION_FINAL_MANIFEST_TMP=$evidence_root/.manifest.final.tmp
  print -r -- "$final_json" >| "$MIGRATION_FINAL_MANIFEST_TMP"
  chmod 600 -- "$MIGRATION_FINAL_MANIFEST_TMP"
  jq -e '.disposition == "accepted" and .cleanup.transient_unit.unit_collected' \
    "$MIGRATION_FINAL_MANIFEST_TMP" >/dev/null ||
    fail 'final manifest serialization failed before atomic publication'
  mv -f -- "$MIGRATION_FINAL_MANIFEST_TMP" "$manifest"
  MIGRATION_FINAL_MANIFEST_TMP=''
  print -r -- "$(file_sha256 "$manifest")  manifest.json" >| "$evidence_root/manifest.sha256"
  chmod 600 -- "$evidence_root/manifest.sha256"
}

execute_acceptance() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local qdrant_1_17=$1
  local qdrant_1_18=$2
  local qdrant_1_19=$3
  local api_key=''
  local config_empty_17=''
  local config_empty_18=''
  local config_17=''
  local config_18=''
  local config_19=''
  local config_empty_19=''
  local collection_17_snapshot=$MIGRATION_WORK_ROOT/evidence/collection-1.17.1.snapshot
  local full_17_snapshot=$MIGRATION_WORK_ROOT/evidence/full-storage-1.17.1.snapshot
  local collection_18_snapshot=$MIGRATION_WORK_ROOT/evidence/collection-1.18.3.snapshot
  local empty_19_snapshot=$MIGRATION_WORK_ROOT/evidence/collection-empty-1.19.0.snapshot
  local full_18_snapshot=$MIGRATION_WORK_ROOT/evidence/full-storage-1.18.3.snapshot
  local collection_snapshot_before=''
  local unexpected_entry=''
  local control_root=$MIGRATION_WORK_ROOT/control
  local keepalive_fifo=$control_root/outer-alive
  local interrupt_ready_marker=${QDRANT_MIGRATION_INTERRUPT_READY_MARKER:-}
  integer interrupt_probe=0

  umask 077
  [[ -d $MIGRATION_WORK_ROOT && ! -L $MIGRATION_WORK_ROOT ]] ||
    fail 'isolated execution work root is not a real directory'
  [[ $(stat -c '%a' -- "$MIGRATION_WORK_ROOT") == 700 ]] ||
    fail 'isolated execution work root must have mode 0700'
  [[ -d $control_root && ! -L $control_root && $(stat -c '%a' -- "$control_root") == 700 ]] ||
    fail 'isolated execution control directory is absent or unsafe'
  [[ -p $keepalive_fifo && ! -L $keepalive_fifo && $(stat -c '%a' -- "$keepalive_fifo") == 600 ]] ||
    fail 'isolated execution keepalive is absent or unsafe'
  [[ $(find "$control_root" -mindepth 1 -maxdepth 1 -printf '%f\n') == outer-alive ]] ||
    fail 'isolated execution control directory contains an unexpected entry'
  if [[ ${QDRANT_MIGRATION_INTERRUPT_PROBE:-} == 1 ]]; then
    interrupt_probe=1
    [[ $interrupt_ready_marker == "$control_root/interrupt-ready.json" ]] ||
      fail 'isolated interrupt probe marker path is not exact'
  elif [[ -n $interrupt_ready_marker ]]; then
    fail 'interrupt readiness marker was supplied outside probe mode'
  fi
  rm -f -- "$keepalive_fifo"
  (( interrupt_probe )) || rmdir -- "$control_root"
  if (( interrupt_probe )); then
    unexpected_entry=$(find "$MIGRATION_WORK_ROOT" -mindepth 1 -maxdepth 1 \
      ! -path "$control_root" -print -quit)
  else
    unexpected_entry=$(find "$MIGRATION_WORK_ROOT" -mindepth 1 -maxdepth 1 -print -quit)
  fi
  [[ -z $unexpected_entry ]] || fail "isolated execution work root was not fresh: $unexpected_entry"
  mkdir -m 700 -- "$MIGRATION_WORK_ROOT/evidence"
  MIGRATION_EVENTS_FILE=$MIGRATION_WORK_ROOT/evidence/events.jsonl
  : >| "$MIGRATION_EVENTS_FILE"
  chmod 600 -- "$MIGRATION_EVENTS_FILE"

  verify_isolation_boundary
  record_isolation_event

  api_key=$(openssl rand -hex 32)
  [[ ${#api_key} == 64 && -z ${api_key//[0-9a-f]/} ]] ||
    fail 'openssl did not produce a 64-hex API key'
  MIGRATION_API_KEY=$api_key

  print -r -- 'empty-state: preserving an empty 1.17.1 rollback anchor'
  config_empty_17=$(write_config "$MIGRATION_WORK_ROOT/empty-anchor-1.17.1")
  start_server "$qdrant_1_17" 1.17.1 "$MIGRATION_WORK_ROOT/empty-anchor-1.17.1" \
    "$config_empty_17"
  publish_interrupt_probe_readiness_and_wait
  stop_server
  copy_storage "$MIGRATION_WORK_ROOT/empty-anchor-1.17.1/storage" \
    "$MIGRATION_WORK_ROOT/evidence/empty-1.17.1-anchor"
  seal_cold_copy "$MIGRATION_WORK_ROOT/evidence/empty-1.17.1-anchor"
  record_cold_copy empty_1_17_anchor_sealed 1.17.1 \
    "$MIGRATION_WORK_ROOT/evidence/empty-1.17.1-anchor"

  print -r -- 'empty-state: proving the migration-only 1.18.3 binary starts and stops cleanly'
  config_empty_18=$(write_config "$MIGRATION_WORK_ROOT/empty-start-stop-1.18.3")
  start_server "$qdrant_1_18" 1.18.3 "$MIGRATION_WORK_ROOT/empty-start-stop-1.18.3" \
    "$config_empty_18"
  stop_server
  record_event empty_1_18_start_stop empty_state \
    '{"version":"1.18.3","fresh_storage":true,"start_succeeded":true,"clean_stop_succeeded":true,"active_package_producer_changed":false}'

  print -r -- 'retained-data: creating authenticated 1.17.1 fixture'
  config_17=$(write_config "$MIGRATION_WORK_ROOT/retained-1.17.1")
  start_server "$qdrant_1_17" 1.17.1 "$MIGRATION_WORK_ROOT/retained-1.17.1" "$config_17"
  create_fixture
  verify_fixture
  record_fixture_queries
  create_collection_snapshot "$FIXTURE_COLLECTION" "$collection_17_snapshot"
  record_snapshot snapshot_collection_1_17 1.17.1 collection "$collection_17_snapshot"
  collection_snapshot_before=$(file_sha256 "$collection_17_snapshot")
  create_full_snapshot "$full_17_snapshot"
  [[ -s $collection_17_snapshot && $(file_sha256 "$collection_17_snapshot") == $collection_snapshot_before ]] ||
    fail 'preserved 1.17.1 collection snapshot disappeared or changed during full-snapshot creation'
  record_snapshot snapshot_full_1_17 1.17.1 full_storage "$full_17_snapshot"
  stop_server
  copy_storage "$MIGRATION_WORK_ROOT/retained-1.17.1/storage" \
    "$MIGRATION_WORK_ROOT/evidence/cold-1.17.1"
  seal_cold_copy "$MIGRATION_WORK_ROOT/evidence/cold-1.17.1"
  record_cold_copy cold_copy_1_17_sealed 1.17.1 \
    "$MIGRATION_WORK_ROOT/evidence/cold-1.17.1"

  print -r -- 'retained-data: exercising the 1.17.1 snapshot restore matrix'
  restore_collection_snapshot "$qdrant_1_17" 1.17.1 "$collection_17_snapshot" \
    "$MIGRATION_WORK_ROOT/restore-1.17.1-same" migration-17-same migration-17-same-current \
    restore_1_17_same_1_17
  restore_collection_snapshot "$qdrant_1_18" 1.18.3 "$collection_17_snapshot" \
    "$MIGRATION_WORK_ROOT/restore-1.17.1-next-1.18.3" migration-17-next migration-17-next-current \
    restore_1_17_next_1_18
  restore_full_storage_snapshot "$qdrant_1_18" 1.18.3 1.17.1 "$full_17_snapshot" \
    "$MIGRATION_WORK_ROOT/full-restore-1.18.3" restore_full_1_17_next_1_18
  prove_truncated_rejection_and_retry "$qdrant_1_18" 1.18.3 1.17.1 \
    "$collection_17_snapshot" "$MIGRATION_WORK_ROOT/reject-1.17.1-truncated-1.18.3" \
    reject_1_17_to_1_18_truncated retry_1_17_to_1_18_truncated
  prove_checksum_rejection_and_retry "$qdrant_1_18" 1.18.3 1.17.1 \
    "$collection_17_snapshot" "$MIGRATION_WORK_ROOT/reject-1.17.1-checksum-1.18.3" \
    reject_1_17_to_1_18_checksum retry_1_17_to_1_18_checksum

  print -r -- 'retained-data: opening only a copy with 1.18.3'
  mkdir -p -- "$MIGRATION_WORK_ROOT/retained-1.18.3"
  copy_storage "$MIGRATION_WORK_ROOT/evidence/cold-1.17.1" \
    "$MIGRATION_WORK_ROOT/retained-1.18.3/storage"
  make_storage_writable "$MIGRATION_WORK_ROOT/retained-1.18.3/storage"
  config_18=$(write_config "$MIGRATION_WORK_ROOT/retained-1.18.3")
  start_server "$qdrant_1_18" 1.18.3 "$MIGRATION_WORK_ROOT/retained-1.18.3" "$config_18"
  verify_fixture
  restart_and_verify "$qdrant_1_18" 1.18.3 \
    "$MIGRATION_WORK_ROOT/retained-1.18.3" "$config_18"
  create_collection_snapshot "$FIXTURE_COLLECTION" "$collection_18_snapshot"
  record_snapshot snapshot_collection_1_18 1.18.3 collection "$collection_18_snapshot"
  collection_snapshot_before=$(file_sha256 "$collection_18_snapshot")
  create_full_snapshot "$full_18_snapshot"
  [[ -s $collection_18_snapshot && $(file_sha256 "$collection_18_snapshot") == $collection_snapshot_before ]] ||
    fail 'preserved 1.18.3 collection snapshot disappeared or changed during full-snapshot creation'
  record_snapshot snapshot_full_1_18 1.18.3 full_storage "$full_18_snapshot"
  stop_server
  record_cold_migration cold_migration_1_17_to_1_18_verified 1.17.1 1.18.3 \
    "$MIGRATION_WORK_ROOT/evidence/cold-1.17.1"
  copy_storage "$MIGRATION_WORK_ROOT/retained-1.18.3/storage" \
    "$MIGRATION_WORK_ROOT/evidence/cold-1.18.3"
  seal_cold_copy "$MIGRATION_WORK_ROOT/evidence/cold-1.18.3"
  record_cold_copy cold_copy_1_18_sealed 1.18.3 \
    "$MIGRATION_WORK_ROOT/evidence/cold-1.18.3"

  print -r -- 'retained-data: exercising the 1.18.3 snapshot restore matrix'
  restore_collection_snapshot "$qdrant_1_18" 1.18.3 "$collection_18_snapshot" \
    "$MIGRATION_WORK_ROOT/restore-1.18.3-same" migration-18-same migration-18-same-current \
    restore_1_18_same_1_18
  restore_collection_snapshot "$qdrant_1_19" 1.19.0 "$collection_18_snapshot" \
    "$MIGRATION_WORK_ROOT/restore-1.18.3-next-1.19.0" migration-18-next migration-18-next-current \
    restore_1_18_next_1_19
  prove_truncated_rejection_and_retry "$qdrant_1_19" 1.19.0 1.18.3 \
    "$collection_18_snapshot" "$MIGRATION_WORK_ROOT/reject-1.18.3-truncated-1.19.0" \
    reject_1_18_to_1_19_truncated retry_1_18_to_1_19_truncated
  prove_checksum_rejection_and_retry "$qdrant_1_19" 1.19.0 1.18.3 \
    "$collection_18_snapshot" "$MIGRATION_WORK_ROOT/reject-1.18.3-checksum-1.19.0" \
    reject_1_18_to_1_19_checksum retry_1_18_to_1_19_checksum

  print -r -- 'retained-data: opening only the 1.18.3 cold copy with 1.19.0'
  mkdir -p -- "$MIGRATION_WORK_ROOT/retained-1.19.0"
  copy_storage "$MIGRATION_WORK_ROOT/evidence/cold-1.18.3" \
    "$MIGRATION_WORK_ROOT/retained-1.19.0/storage"
  make_storage_writable "$MIGRATION_WORK_ROOT/retained-1.19.0/storage"
  config_19=$(write_config "$MIGRATION_WORK_ROOT/retained-1.19.0")
  start_server "$qdrant_1_19" 1.19.0 "$MIGRATION_WORK_ROOT/retained-1.19.0" "$config_19"
  verify_fixture
  restart_and_verify "$qdrant_1_19" 1.19.0 \
    "$MIGRATION_WORK_ROOT/retained-1.19.0" "$config_19"
  stop_server
  record_cold_migration cold_migration_1_18_to_1_19_verified 1.18.3 1.19.0 \
    "$MIGRATION_WORK_ROOT/evidence/cold-1.18.3"

  print -r -- 'retained-data: restoring the 1.18.3 full-storage snapshot with 1.19.0'
  restore_full_storage_snapshot "$qdrant_1_19" 1.19.0 1.18.3 "$full_18_snapshot" \
    "$MIGRATION_WORK_ROOT/full-restore-1.19.0" restore_full_1_18_next_1_19

  print -r -- 'empty-state: creating and restarting a fresh 1.19.0 fixture'
  config_empty_19=$(write_config "$MIGRATION_WORK_ROOT/empty-1.19.0")
  start_server "$qdrant_1_19" 1.19.0 "$MIGRATION_WORK_ROOT/empty-1.19.0" "$config_empty_19"
  create_fixture
  restart_and_verify "$qdrant_1_19" 1.19.0 \
    "$MIGRATION_WORK_ROOT/empty-1.19.0" "$config_empty_19"
  create_collection_snapshot "$FIXTURE_COLLECTION" "$empty_19_snapshot"
  record_snapshot snapshot_collection_1_19 1.19.0 collection "$empty_19_snapshot"
  stop_server
  restore_collection_snapshot "$qdrant_1_19" 1.19.0 "$empty_19_snapshot" \
    "$MIGRATION_WORK_ROOT/empty-restore-1.19.0" migration-empty-restored migration-empty-current \
    restore_1_19_same_1_19
  record_event empty_1_19_fixture_verified empty_state \
    '{"version":"1.19.0","fresh_storage":true,"stable_ids_verified":true,"dense_sparse_hybrid_equivalent":true,"restart_verified":true,"same_minor_restore_verified":true}'

  print -r -- 'resource-pressure: exercising disk threshold, rejection, and recovery'
  exercise_disk_pressure "$qdrant_1_19"
  print -r -- 'resource-pressure: exercising memory threshold, rejection, and recovery'
  exercise_memory_pressure "$qdrant_1_19"

  verify_final_cleanup "$api_key"
  write_runtime_evidence_candidate "$qdrant_1_17" "$qdrant_1_18" "$qdrant_1_19"
  print -r -- 'Qdrant runtime obligations passed; awaiting outer transient-unit cleanup'
}

launch_isolated_execution() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL
  local qdrant_1_17_package=$1
  local qdrant_1_17=$2
  local qdrant_1_18=$3
  local qdrant_1_19=$4
  local int_receipt=${5:-}
  local term_receipt=${6:-}
  local probe_signal=${7:-}
  local script_path=$MIGRATION_SCRIPT_PATH
  local parent_netns=''
  local isolated_qdrant_1_17=/run/qdrant-inputs/qdrant-1.17.1
  local isolated_qdrant_1_17_package=/run/qdrant-inputs/qdrant-1.17.1-1-x86_64.pkg.tar.zst
  local isolated_qdrant_1_18=/run/qdrant-inputs/qdrant-1.18.3
  local isolated_qdrant_1_19=/run/qdrant-inputs/qdrant-1.19.0
  local isolated_script=/run/qdrant-inputs/validate_qdrant_migration.zsh
  local isolated_int_receipt=/run/qdrant-inputs/interrupt-INT.json
  local isolated_term_receipt=/run/qdrant-inputs/interrupt-TERM.json
  local unit_name="qdrant-migration-${$}-${RANDOM}.service"
  local keepalive_fifo=$MIGRATION_WORK_ROOT/control/outer-alive
  local interrupt_ready_marker=$MIGRATION_WORK_ROOT/control/interrupt-ready.json
  integer run_status=0
  local -a receipt_binds=()
  local -a receipt_args=()
  local -a probe_environment=()

  if [[ -n $int_receipt && -n $term_receipt ]]; then
    receipt_binds=(
      --ro-bind "$int_receipt" "$isolated_int_receipt"
      --ro-bind "$term_receipt" "$isolated_term_receipt"
    )
    receipt_args=(
      --int-receipt "$isolated_int_receipt"
      --term-receipt "$isolated_term_receipt"
    )
  fi
  if [[ -n $probe_signal ]]; then
    probe_environment=(
      --setenv QDRANT_MIGRATION_INTERRUPT_PROBE 1
      --setenv QDRANT_MIGRATION_INTERRUPT_READY_MARKER "$interrupt_ready_marker"
    )
  fi

  parent_netns=$(readlink -- /proc/self/ns/net)
  mkdir -m 700 -- "$MIGRATION_WORK_ROOT"
  mkdir -m 700 -- "$MIGRATION_WORK_ROOT/control"
  mkfifo -m 600 -- "$keepalive_fifo"
  exec {MIGRATION_TRANSIENT_KEEPALIVE_FD}<> "$keepalive_fifo"
  MIGRATION_TRANSIENT_UNIT=$unit_name
  MIGRATION_TRANSIENT_WAIT_COMPLETED=0
  MIGRATION_TRANSIENT_WAIT_UNIT=''
  MIGRATION_TRANSIENT_WAIT_STATUS=''
  systemd-run --user --pipe --wait --collect --quiet --service-type=exec \
    --unit="$unit_name" \
    --expand-environment=no \
    --property="MemoryMax=$ISOLATED_MEMORY_MAX_BYTES" \
    --property="MemoryHigh=$ISOLATED_MEMORY_HIGH_BYTES" \
    --property="RuntimeMaxSec=$TRANSIENT_RUNTIME_MAX_SEC" \
    --property="TimeoutStopSec=$TRANSIENT_TIMEOUT_STOP_SEC" \
    --property="KillMode=control-group" \
    --property="SendSIGKILL=yes" \
    --setenv=QDRANT_MIGRATION_UNIT_SUPERVISOR=1 \
    --setenv=QDRANT_MIGRATION_CGROUP_RECEIPT="$MIGRATION_WORK_ROOT/control/unit-cgroup" \
    -- "$script_path" --supervise-isolated-payload -- /usr/bin/bwrap \
      --unshare-user --uid 0 --gid 0 \
      --unshare-net --unshare-pid --unshare-uts --unshare-ipc \
      --new-session --die-with-parent --clearenv \
      --ro-bind /usr /usr \
      --symlink usr/bin /bin \
      --symlink usr/bin /sbin \
      --symlink usr/lib /lib \
      --symlink usr/lib /lib64 \
      --proc /proc --dev /dev \
      --dir /sys --dir /sys/fs \
      --ro-bind /sys/fs/cgroup /sys/fs/cgroup \
      --dir /etc --dir /etc/ssl --dir /etc/ssl/certs \
      --ro-bind /etc/ca-certificates/extracted/tls-ca-bundle.pem /etc/ssl/certs/ca-certificates.crt \
      --tmpfs /tmp \
      --bind "$MIGRATION_WORK_ROOT" "$MIGRATION_WORK_ROOT" \
      --tmpfs /run \
      --dir /run/qdrant-inputs \
      --ro-bind "$script_path" "$isolated_script" \
      --ro-bind "$qdrant_1_17_package" "$isolated_qdrant_1_17_package" \
      --ro-bind "$qdrant_1_17" "$isolated_qdrant_1_17" \
      --ro-bind "$qdrant_1_18" "$isolated_qdrant_1_18" \
      --ro-bind "$qdrant_1_19" "$isolated_qdrant_1_19" \
      $receipt_binds \
      --cap-add CAP_SYS_ADMIN --cap-add CAP_SETPCAP \
      --setenv PATH /usr/bin:/bin \
      --setenv HOME /tmp \
      --setenv LANG C.UTF-8 \
      --setenv SSL_CERT_FILE /etc/ssl/certs/ca-certificates.crt \
      --setenv QDRANT_MIGRATION_ISOLATED 1 \
      --setenv QDRANT_MIGRATION_PARENT_NETNS "$parent_netns" \
      $probe_environment \
      --chdir "$MIGRATION_WORK_ROOT" \
      -- "$isolated_script" --execute-isolated \
        --work-root "$MIGRATION_WORK_ROOT" \
        --http-port "$MIGRATION_HTTP_PORT" \
        --grpc-port "$MIGRATION_GRPC_PORT" \
        --qdrant-1.17.1-package "$isolated_qdrant_1_17_package" \
        --qdrant-1.17.1 "$isolated_qdrant_1_17" \
        --qdrant-1.18.3 "$isolated_qdrant_1_18" \
        --qdrant-1.19.0 "$isolated_qdrant_1_19" \
        $receipt_args \
      < "$keepalive_fifo" {MIGRATION_TRANSIENT_KEEPALIVE_FD}>&- &
  MIGRATION_TRANSIENT_CLIENT_PID=$!
  MIGRATION_TRANSIENT_CLIENT_EXE=/usr/bin/systemd-run
  capture_process_exec_identity $MIGRATION_TRANSIENT_CLIENT_PID \
    "$MIGRATION_TRANSIENT_CLIENT_EXE" || {
    stop_transient_unit best_effort
    fail 'could not establish the transient-unit client ownership token'
  }
  MIGRATION_TRANSIENT_CLIENT_START=$REPLY
  capture_transient_cgroup "$unit_name"
  if [[ -n $probe_signal ]]; then
    await_interrupt_probe_readiness "$interrupt_ready_marker"
    schedule_probe_interrupt "$probe_signal"
  fi
  if wait $MIGRATION_TRANSIENT_CLIENT_PID; then
    run_status=0
  else
    run_status=$?
  fi
  MIGRATION_TRANSIENT_WAIT_COMPLETED=1
  MIGRATION_TRANSIENT_WAIT_UNIT=$unit_name
  MIGRATION_TRANSIENT_WAIT_STATUS=$run_status
  MIGRATION_TRANSIENT_CLIENT_PID=''
  MIGRATION_TRANSIENT_CLIENT_START=''
  MIGRATION_TRANSIENT_CLIENT_EXE=''
  close_transient_keepalive
  if (( run_status != 0 )); then
    fail "transient isolation unit exited unsuccessfully: $unit_name (status $run_status)"
  fi
  verify_transient_unit_collected "$unit_name"
  MIGRATION_TRANSIENT_UNIT=''
  finalize_evidence_after_unit "$unit_name"
  print -r -- "Qdrant disposable migration acceptance passed; evidence retained at $MIGRATION_WORK_ROOT"
}

main() {
  emulate -L zsh
  setopt ERR_EXIT NO_UNSET PIPE_FAIL

  integer plan_mode=0
  integer execute_mode=0
  integer isolated_mode=0
  integer probe_mode=0
  integer work_root_supplied=0
  integer http_port_supplied=0
  integer grpc_port_supplied=0
  integer receipt_supplied=0
  integer int_receipt_supplied=0
  integer term_receipt_supplied=0
  local qdrant_1_17_package=''
  local qdrant_1_17=''
  local qdrant_1_18=''
  local qdrant_1_19=''

  while (( $# )); do
    case $1 in
      --help|-h)
        usage
        return 0
        ;;
      --plan)
        plan_mode=1
        shift
        ;;
      --execute)
        execute_mode=1
        shift
        ;;
      --execute-isolated)
        isolated_mode=1
        shift
        ;;
      --probe-interrupt)
        (( $# >= 2 )) || fail "$1 requires INT or TERM"
        probe_mode=1
        MIGRATION_PROBE_SIGNAL=$2
        shift 2
        ;;
      --work-root)
        (( $# >= 2 )) || fail "$1 requires PATH"
        MIGRATION_WORK_ROOT=$2
        work_root_supplied=1
        shift 2
        ;;
      --http-port)
        (( $# >= 2 )) || fail "$1 requires PORT"
        MIGRATION_HTTP_PORT=$2
        http_port_supplied=1
        shift 2
        ;;
      --grpc-port)
        (( $# >= 2 )) || fail "$1 requires PORT"
        MIGRATION_GRPC_PORT=$2
        grpc_port_supplied=1
        shift 2
        ;;
      --receipt)
        (( $# >= 2 )) || fail "$1 requires PATH"
        MIGRATION_PROBE_RECEIPT=$2
        receipt_supplied=1
        shift 2
        ;;
      --int-receipt)
        (( $# >= 2 )) || fail "$1 requires PATH"
        MIGRATION_INT_RECEIPT=$2
        int_receipt_supplied=1
        shift 2
        ;;
      --term-receipt)
        (( $# >= 2 )) || fail "$1 requires PATH"
        MIGRATION_TERM_RECEIPT=$2
        term_receipt_supplied=1
        shift 2
        ;;
      --qdrant-1.17.1-package)
        (( $# >= 2 )) || fail "$1 requires PATH"
        qdrant_1_17_package=$2
        shift 2
        ;;
      --qdrant-1.17.1)
        (( $# >= 2 )) || fail "$1 requires PATH"
        qdrant_1_17=$2
        shift 2
        ;;
      --qdrant-1.18.3)
        (( $# >= 2 )) || fail "$1 requires PATH"
        qdrant_1_18=$2
        shift 2
        ;;
      --qdrant-1.19.0)
        (( $# >= 2 )) || fail "$1 requires PATH"
        qdrant_1_19=$2
        shift 2
        ;;
      --)
        shift
        (( $# == 0 )) || fail "unexpected positional arguments: ${(@q)argv}"
        ;;
      *)
        fail "unknown argument: $1"
        ;;
    esac
  done

  (( plan_mode + execute_mode + isolated_mode + probe_mode == 1 )) ||
    fail 'exactly one mode is required; use --plan, --execute, or --probe-interrupt'
  validate_binary_inputs "$qdrant_1_17" "$qdrant_1_18" "$qdrant_1_19"

  if (( plan_mode )); then
    (( ! work_root_supplied && ! http_port_supplied && ! grpc_port_supplied &&
      ! receipt_supplied && ! int_receipt_supplied && ! term_receipt_supplied )) ||
      fail '--plan does not accept execution paths, ports, or receipts'
  else
    (( work_root_supplied )) || fail '--execute requires --work-root under /tmp'
    require_command realpath
    if (( execute_mode || probe_mode )); then
      validate_work_root "$MIGRATION_WORK_ROOT"
    else
      [[ $MIGRATION_WORK_ROOT == /tmp/* && -d $MIGRATION_WORK_ROOT && ! -L $MIGRATION_WORK_ROOT ]] ||
        fail 'isolated --work-root must be an existing real directory under /tmp'
      [[ $(realpath -m -- "$MIGRATION_WORK_ROOT") == $MIGRATION_WORK_ROOT ]] ||
        fail 'isolated --work-root must be canonical'
    fi
    validate_port --http-port $MIGRATION_HTTP_PORT
    validate_port --grpc-port $MIGRATION_GRPC_PORT
    (( MIGRATION_HTTP_PORT != MIGRATION_GRPC_PORT )) ||
      fail '--http-port and --grpc-port must be distinct'
  fi

  require_command bsdtar
  require_command sha256sum
  require_command stat
  require_command grep
  validate_exact_candidate_binary "$qdrant_1_18" 1.18.3 "$QDRANT_1_18_BINARY_SHA256"
  MIGRATION_QDRANT_1_18_BINARY_SHA256=$REPLY
  validate_exact_candidate_binary "$qdrant_1_19" 1.19.0 "$QDRANT_1_19_BINARY_SHA256"
  MIGRATION_QDRANT_1_19_BINARY_SHA256=$REPLY
  validate_qdrant_1_17_package "$qdrant_1_17_package" "$qdrant_1_17"
  MIGRATION_TOOL_SHA256=$(file_sha256 "$MIGRATION_SCRIPT_PATH")

  if (( probe_mode )); then
    [[ $MIGRATION_PROBE_SIGNAL == INT || $MIGRATION_PROBE_SIGNAL == TERM ]] ||
      fail '--probe-interrupt accepts only INT or TERM'
    (( receipt_supplied && ! int_receipt_supplied && ! term_receipt_supplied )) ||
      fail '--probe-interrupt requires only --receipt, not accepted receipt inputs'
    validate_receipt_destination "$MIGRATION_PROBE_RECEIPT"
  elif (( execute_mode )); then
    (( ! receipt_supplied && int_receipt_supplied && term_receipt_supplied )) ||
      fail '--execute requires --int-receipt and --term-receipt and rejects --receipt'
    validate_interrupt_receipt "$MIGRATION_INT_RECEIPT" INT 130
    MIGRATION_INT_RECEIPT_SHA256=$REPLY
    validate_interrupt_receipt "$MIGRATION_TERM_RECEIPT" TERM 143
    MIGRATION_TERM_RECEIPT_SHA256=$REPLY
  elif (( isolated_mode )); then
    (( ! receipt_supplied )) || fail '--execute-isolated rejects --receipt'
    (( int_receipt_supplied == term_receipt_supplied )) ||
      fail '--execute-isolated requires both accepted receipts or neither for an interrupt probe'
    if (( int_receipt_supplied )); then
      validate_interrupt_receipt "$MIGRATION_INT_RECEIPT" INT 130
      MIGRATION_INT_RECEIPT_SHA256=$REPLY
      validate_interrupt_receipt "$MIGRATION_TERM_RECEIPT" TERM 143
      MIGRATION_TERM_RECEIPT_SHA256=$REPLY
    fi
  fi

  if (( plan_mode )); then
    print_plan
    return 0
  fi

  local command
  if (( execute_mode || probe_mode )); then
    for command in bwrap systemd-run mkfifo mkdir rmdir readlink jq sha256sum mv rm ln; do
      require_command $command
    done
    launch_isolated_execution "$qdrant_1_17_package" "$qdrant_1_17" "$qdrant_1_18" "$qdrant_1_19" \
      "$MIGRATION_INT_RECEIPT" "$MIGRATION_TERM_RECEIPT" "$MIGRATION_PROBE_SIGNAL"
    return 0
  fi

  for command in curl jq openssl sha256sum ss stat readlink cp truncate tail \
    setpriv ip python3 mount umount df fallocate sync find sort ps grep uname \
    findmnt date; do
    require_command $command
  done
  MIGRATION_BASE_URL="http://127.0.0.1:$MIGRATION_HTTP_PORT"
  validate_ports_available
  {
    execute_acceptance "$qdrant_1_17" "$qdrant_1_18" "$qdrant_1_19"
  } always {
    cleanup
  }
}

if [[ ${QDRANT_MIGRATION_TEST_SOURCE_ONLY:-} == 1 ]]; then
  [[ $ZSH_EVAL_CONTEXT == *:file ]] || {
    fail 'test source-only mode requires sourcing the script'
    exit $?
  }
  return 0
fi

if [[ ${1:-} == --supervise-isolated-payload ]]; then
  [[ ${QDRANT_MIGRATION_UNIT_SUPERVISOR:-} == 1 ]] ||
    fail 'unit supervisor marker is absent'
  shift
  [[ ${1:-} == -- ]] || fail 'unit supervisor requires -- before its payload'
  shift
  [[ ${1:-} == /usr/bin/bwrap ]] || fail 'unit supervisor accepts only the exact Bubblewrap payload'
  supervise_isolated_payload "$@"
  exit $?
fi

main "$@"
