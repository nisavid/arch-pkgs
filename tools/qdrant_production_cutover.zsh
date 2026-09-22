#!/usr/bin/env zsh
# Operator handoff for the production Qdrant cutover described in
# docs/maintainers/qdrant-production-cutover.md. Dry-run by default; nothing
# on the host changes without --apply, and --apply requires root.

emulate -L zsh
setopt errexit nounset pipefail extendedglob

script_name=${0:t}

# Accepted identities. The byte-identical rebuilds are bound by the accepted
# G0-G3 evidence under docs/maintainers/evidence/qdrant-1.19.0-1/.
typeset -A want_version want_file want_size want_sha
want_version=(qdrant-migration 1.18.3-1 qdrant 1.19.0-1 qdrant-web-ui 0.2.16-1)
want_file=(
  qdrant-migration qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst
  qdrant qdrant-1.19.0-1-x86_64.pkg.tar.zst
  qdrant-web-ui qdrant-web-ui-0.2.16-1-any.pkg.tar.zst
)
want_size=(qdrant-migration 26721008 qdrant 28018464 qdrant-web-ui 5719063)
want_sha=(
  qdrant-migration 591f16328fcff0fc0193353a65f4c783afc1d24258ae251d3a8927283276ce9e
  qdrant 15f15fe2c0c774691bf3193bc8fc7883fa530c89db697f7c0bcc2720d231b011
  qdrant-web-ui f3d46e6ff09b8eb87b1465ee6a17a7cc35c574596b7fbf30518d3bc1d42fe10a
)
baseline_version=1.17.1-1
baseline_file=qdrant-1.17.1-1-x86_64.pkg.tar.zst
baseline_sha=d237ac6b804c7b4ec3f73f8ef57340ebaba62abff7853636286f140c8affd5cb
migration_binary=/usr/lib/qdrant/migration/qdrant-1.18.3
collection_prefix=open-webui-rag-v1
collection_suffixes=(memories knowledge files web-search hash-based)
credential_name=qdrant-runtime-api-key

# Defaults match the packaged layout.
url=http://127.0.0.1:6333
storage_dir=/var/lib/qdrant
config_dir=/etc/qdrant
repo=nisavid
sync_db=
pkg_cache=/var/cache/pacman/pkg
rollback_root=/var/lib/qdrant-rollback
rollback_set=qdrant-1.17.1-1-pre-1.19.0
credstore=/etc/credstore.encrypted
disk_quota_percent=85
apply=0

usage() {
  cat <<EOF
Usage: ${script_name} <preflight|cutover|verify|rollback> [options]

  preflight  read-only checks; refuses on identity mismatch, non-empty
             storage, live consumers, or insufficient free space
  cutover    preflight, stop 1.17.1, save the rollback set, run the 1.18.3
             step, install 1.19.0 and the Web UI, provision secrets, create
             the ${collection_prefix} collections, then verify
  verify     post-install smoke of the running 1.19.0 service
  rollback   restore 1.17.1 and the saved state from the rollback set

Options (defaults match the packaged layout):
  --apply                    perform host changes (requires root)
  --url URL                  Qdrant HTTP endpoint [${url}]
  --storage-dir DIR          Qdrant state directory [${storage_dir}]
  --config-dir DIR           Qdrant configuration directory [${config_dir}]
  --repo NAME                pacman repository [${repo}]
  --sync-db FILE             repository sync database [/var/lib/pacman/sync/<repo>.db]
  --pkg-cache DIR            pacman package cache [${pkg_cache}]
  --rollback-root DIR        rollback set parent [${rollback_root}]
  --rollback-set NAME        rollback set name [${rollback_set}]
  --credstore DIR            encrypted credential store [${credstore}]
  --disk-quota-percent N     packaged Qdrant disk quota [${disk_quota_percent}]
EOF
}

die() { print -ru2 -- "${script_name}: $*"; exit 2; }
note() { print -r -- "$*"; }

typeset -a refusals
refuse() { refusals+=("$*"); print -ru2 -- "REFUSE: $*"; }

hand_back() {
  # The single line an operator returns to the delegate.
  print -r -- "HAND-BACK: $*"
}

finish_or_refuse() {
  local stage=$1
  if (( $#refusals )); then
    hand_back "qdrant ${stage} refused (${#refusals} check(s) failed); host unchanged by this stage"
    exit 1
  fi
}

run() {
  if (( apply )); then
    note "+ ${(j: :)${(q-)@}}"
    "$@"
  else
    note "DRY-RUN: ${(j: :)${(q-)@}}"
  fi
}

sha256_of() { sha256sum -- "$1" | awk '{print $1}'; }

http_code() {
  # http_code METHOD PATH [HEADER_FILE] [BODY]
  local method=$1 endpoint=$2 headers=${3:-} body=${4:-}
  local -a args=(-sS -o /dev/null -w '%{http_code}' -m 10 -X "$method")
  [[ -n "$headers" ]] && args+=(-H "@${headers}")
  [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' --data-binary "$body")
  curl "${args[@]}" "${url}${endpoint}" 2>/dev/null || print -r -- 000
}

http_json() {
  local endpoint=$1 headers=${2:-}
  local -a args=(-sS -m 10)
  [[ -n "$headers" ]] && args+=(-H "@${headers}")
  curl "${args[@]}" "${url}${endpoint}"
}

sync_db_field() {
  # sync_db_field PKGNAME FIELD -> value from the repository database entry
  local name=$1 field=$2 entry
  entry=$(bsdtar -tf "$sync_db" 2>/dev/null | grep -E "^${name}-[^-]+-[^-]+/desc$" | head -n1) || true
  [[ -n "$entry" ]] || return 1
  bsdtar -xOf "$sync_db" "$entry" | awk -v f="%${field}%" '$0 == f { getline; print; exit }'
}

storage_usage() {
  # prints "<used-percent> <available-bytes> <size-bytes>" for the storage filesystem
  df -B1 --output=pcent,avail,size -- "$storage_dir" | awk 'NR == 2 { gsub(/%/, "", $1); print $1, $2, $3 }'
}

check_disk() {
  local used avail size need projected
  read -r used avail size < <(storage_usage) || { refuse "could not read filesystem usage for ${storage_dir}"; return; }
  note "disk: ${storage_dir} filesystem ${used}% used, ${avail} bytes free (quota ${disk_quota_percent}%)"
  if (( used >= disk_quota_percent )); then
    refuse "storage filesystem is ${used}% used, at or above the packaged ${disk_quota_percent}% disk quota; Qdrant would refuse writes"
    return
  fi
  if [[ "${1:-}" == with-copy ]]; then
    need=$(du -sb -- "$storage_dir" "$config_dir" 2>/dev/null | awk '{ s += $1 } END { print s + 0 }') \
      || { refuse "could not size ${storage_dir} and ${config_dir}; run preflight as root"; return; }
    projected=$(( (size - avail + need) * 100 / size ))
    note "disk: rollback copy needs ${need} bytes; projected ${projected}% used"
    (( projected < disk_quota_percent )) \
      || refuse "the rollback copy would raise the storage filesystem to ${projected}%, at or above the ${disk_quota_percent}% disk quota"
  fi
}

check_repo_identity() {
  local name got
  [[ -r "$sync_db" ]] || { refuse "repository database ${sync_db} is not readable"; return; }
  for name in qdrant-migration qdrant qdrant-web-ui; do
    got=$(pacman -Si "${repo}/${name}" 2>/dev/null | awk -F': ' '/^Version/ { print $2; exit }') || true
    [[ "$got" == "${want_version[$name]}" ]] \
      || refuse "identity mismatch: ${repo}/${name} offers '${got:-absent}', want ${want_version[$name]}"
    got=$(sync_db_field "$name" FILENAME) || got=
    [[ "$got" == "${want_file[$name]}" ]] \
      || refuse "identity mismatch: ${name} file '${got:-absent}', want ${want_file[$name]}"
    got=$(sync_db_field "$name" CSIZE) || got=
    [[ "$got" == "${want_size[$name]}" ]] \
      || refuse "identity mismatch: ${name} size '${got:-absent}', want ${want_size[$name]}"
    got=$(sync_db_field "$name" SHA256SUM) || got=
    [[ "$got" == "${want_sha[$name]}" ]] \
      || refuse "identity mismatch: ${name} sha256 '${got:-absent}', want ${want_sha[$name]}"
  done
}

config_unmodified() {
  # Capture first: grep -q exiting early must not fail the pipeline.
  local info
  info=$(pacman -Qii qdrant 2>/dev/null) || return 1
  [[ "$info" == *"${config_dir}/config.yaml [unmodified]"* ]]
}

check_baseline_archive() {
  local archive=$1
  [[ -f "$archive" ]] || { refuse "baseline archive ${archive} is missing"; return; }
  [[ "$(sha256_of "$archive")" == "$baseline_sha" ]] \
    || refuse "identity mismatch: ${archive} is not the retained ${baseline_version} archive"
}

do_preflight() {
  local installed version count established unit
  note "== preflight"
  installed=$(pacman -Q qdrant 2>/dev/null | awk '{print $2}') || true
  [[ "$installed" == "$baseline_version" ]] \
    || refuse "installed qdrant is '${installed:-absent}', this route starts from ${baseline_version}"
  for unit in qdrant-migration qdrant-web-ui; do
    pacman -Q "$unit" >/dev/null 2>&1 && note "note: ${unit} is already installed"
  done
  config_unmodified \
    || refuse "${config_dir}/config.yaml is modified or unowned; reconcile it before cutover so the packaged config applies"
  check_repo_identity
  check_baseline_archive "${pkg_cache}/${baseline_file}"
  check_disk with-copy

  version=$(http_json / 2>/dev/null | jq -r '.version // empty' 2>/dev/null) || version=
  [[ "$version" == "${baseline_version%-*}" ]] \
    || refuse "running Qdrant reports '${version:-unreachable}', want ${baseline_version%-*}"
  count=$(http_json /collections 2>/dev/null | jq -r '.result.collections | length' 2>/dev/null) || count=
  [[ "$count" == 0 ]] \
    || refuse "Qdrant holds '${count:-unknown}' collections; this route is only for empty storage (use the runbook's full migration route)"
  established=$(ss -tnH state established '( dport = :6333 or dport = :6334 )' 2>/dev/null | wc -l)
  (( established == 0 )) || refuse "${established} client connection(s) to Qdrant are open; stop those consumers first"
  for unit in open-webui.service hayhooks.service; do
    [[ "$(systemctl is-active "$unit" 2>/dev/null)" == active ]] \
      && refuse "consumer ${unit} is active; stop it and keep it stopped until verify passes"
  done
  [[ -e "${config_dir}/qdrant.env" ]] \
    && note "secret: ${config_dir}/qdrant.env exists and will be checked by the packaged preflight" \
    || note "secret: ${config_dir}/qdrant.env is absent and will be provisioned by cutover"
  [[ ! -e "${rollback_root}/${rollback_set}" ]] \
    || refuse "rollback set ${rollback_root}/${rollback_set} already exists; choose another --rollback-set"
  [[ ! -e "${credstore}/open-webui.${credential_name}" ]] \
    || refuse "${credstore}/open-webui.${credential_name} already exists; rotation is a separate act"
}

require_root_for_apply() {
  (( ! apply )) || (( EUID == 0 )) || die "--apply requires root"
}

private_dir=
cleanup() { [[ -z "$private_dir" ]] || rm -rf -- "$private_dir"; }
trap cleanup EXIT

make_private_dir() {
  [[ -n "$private_dir" ]] && return
  # Called in the main shell before any $(admin_header) or $(bearer_header),
  # so the EXIT trap removes it.
  private_dir=$(umask 077 && mktemp -d "${TMPDIR:-/run}/qdrant-cutover.XXXXXX")
}

admin_header() {
  # Write the admin api-key header to a private file; the secret never
  # reaches argv or the environment of a child process.
  local line
  line=$(<"${config_dir}/qdrant.env")
  [[ "$line" == QDRANT__SERVICE__API_KEY=* ]] || die "unexpected ${config_dir}/qdrant.env content"
  print -r -- "api-key: ${line#QDRANT__SERVICE__API_KEY=}" >| "${private_dir}/admin.h"
  print -r -- "${private_dir}/admin.h"
}

mint_jwt() {
  # mint_jwt ROLE LIFETIME_SECONDS(0 = no expiry) -> JWT on stdout
  python3 - "${config_dir}/qdrant.env" "$1" "$2" "$collection_prefix" "${collection_suffixes[@]}" <<'PY'
import base64, hashlib, hmac, json, sys, time
env, role, lifetime, prefix, *suffixes = sys.argv[1:]
line = open(env, encoding="ascii").read().strip()
key = line.split("=", 1)[1].encode("ascii")
def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=")
claims = {"access": [{"collection": f"{prefix}_{s}", "access": role} for s in suffixes]}
if int(lifetime):
    claims["exp"] = int(time.time()) + int(lifetime)
head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
body = b64(json.dumps(claims, separators=(",", ":")).encode())
sig = b64(hmac.new(key, head + b"." + body, hashlib.sha256).digest())
sys.stdout.write((head + b"." + body + b"." + sig).decode())
PY
}

bearer_header() {
  # bearer_header NAME < token
  local token
  token=$(cat)
  print -r -- "Authorization: Bearer ${token}" >| "${private_dir}/$1.h"
  print -r -- "${private_dir}/$1.h"
}

wait_for_version() {
  local want=$1 tries=60 got=
  while (( tries-- > 0 )); do
    got=$(http_json / 2>/dev/null | jq -r '.version // empty' 2>/dev/null) || got=
    [[ "$got" == "$want" ]] && return 0
    sleep 1
  done
  return 1
}

stage=
fail_stage() {
  if [[ "$stage" == 'stop 1.17.1' ]]; then
    hand_back "qdrant cutover FAILED at '${stage}'; 1.17.1 and its state are untouched: run sudo systemctl start qdrant.service"
  elif [[ "$stage" == 'save rollback set' ]]; then
    hand_back "qdrant cutover FAILED at '${stage}'; 1.17.1 and its state are untouched: run sudo systemctl start qdrant.service, inspect the partial set ${rollback_root}/${rollback_set}, and retry with a new --rollback-set"
  else
    hand_back "qdrant cutover FAILED at '${stage}'; run: sudo ${script_name} rollback --apply --rollback-set ${rollback_set}"
  fi
  exit 1
}

create_collections() {
  local admin=$1 suffix name
  local body='{"vectors":{"size":2560,"distance":"Cosine","on_disk":false},"hnsw_config":{"payload_m":16,"m":0}}'
  for suffix in "${collection_suffixes[@]}"; do
    name="${collection_prefix}_${suffix}"
    [[ "$(http_code PUT "/collections/${name}" "$admin" "$body")" == 200 ]] || return 1
    [[ "$(http_code PUT "/collections/${name}/index?wait=true" "$admin" \
      '{"field_name":"tenant_id","field_schema":{"type":"keyword","is_tenant":true,"on_disk":false}}')" == 200 ]] || return 1
    for field in metadata.hash metadata.file_id; do
      [[ "$(http_code PUT "/collections/${name}/index?wait=true" "$admin" \
        "{\"field_name\":\"${field}\",\"field_schema\":{\"type\":\"keyword\",\"on_disk\":false}}")" == 200 ]] || return 1
    done
  done
}

snapshot_restore_drill() {
  # One collection snapshot and restore on the still-empty memories collection,
  # before any consumer writes. Both snapshot files are removed afterwards.
  local admin=$1 name="${collection_prefix}_memories" snap upload
  snap=$(curl -sS -m 60 -H "@${admin}" -X POST "${url}/collections/${name}/snapshots?wait=true" | jq -er '.result.name') || return 1
  upload="restore-${snap}"
  curl -sS -m 60 -f -H "@${admin}" -o "${private_dir}/${upload}" "${url}/collections/${name}/snapshots/${snap}" || return 1
  [[ "$(curl -sS -m 60 -o /dev/null -w '%{http_code}' -H "@${admin}" \
    -F "snapshot=@${private_dir}/${upload}" \
    "${url}/collections/${name}/snapshots/upload?wait=true&priority=snapshot")" == 200 ]] || return 1
  rm -f -- "${private_dir}/${upload}"
  note "snapshot drill: ${name} snapshot restored"
  # Cleanup only; a leftover empty snapshot file is not a cutover failure.
  for snap in "$snap" "$upload"; do
    [[ "$(http_code DELETE "/collections/${name}/snapshots/${snap}?wait=true" "$admin")" == 200 ]] \
      || note "warning: could not delete snapshot ${snap} of ${name}; remove it by hand"
  done
}

do_cutover() {
  local set_dir="${rollback_root}/${rollback_set}" admin
  do_preflight
  finish_or_refuse preflight
  note "== cutover"
  (( apply )) || note "(dry run: pass --apply as root to perform these steps)"

  stage='stop 1.17.1'
  run systemctl stop qdrant.service || fail_stage

  stage='save rollback set'
  run install -d -m 0700 -- "$set_dir" || fail_stage
  run cp -a --reflink=auto -- "$storage_dir" "${set_dir}/state" || fail_stage
  run cp -a -- "$config_dir" "${set_dir}/config" || fail_stage
  run cp -a -- "${pkg_cache}/${baseline_file}" "${set_dir}/${baseline_file}" || fail_stage
  if (( apply )); then
    {
      print -r -- "baseline ${baseline_file} ${baseline_sha}"
      pacman -Q qdrant qdrant-migration qdrant-web-ui 2>/dev/null | sed 's/^/installed /' || true
    } >| "${set_dir}/MANIFEST"
    (cd "$storage_dir" && find . -type f -print0 | sort -z | xargs -0r sha256sum) >| "${set_dir}/state.sha256"
    (cd "${set_dir}/state" && sha256sum --quiet -c "${set_dir}/state.sha256") || fail_stage
  fi

  stage='1.18.3 migration step'
  run pacman -S --needed --noconfirm "${repo}/qdrant-migration" || fail_stage
  run systemd-run --unit=qdrant-migration-step --collect \
    --uid=qdrant --gid=qdrant --working-directory="$storage_dir" \
    -p IPAddressDeny=any -p IPAddressAllow=localhost \
    --setenv=QDRANT__TELEMETRY_DISABLED=true \
    "$migration_binary" --config-path "${config_dir}/config.yaml" || fail_stage
  if (( apply )); then
    wait_for_version 1.18.3 || { systemctl stop qdrant-migration-step.service || true; fail_stage; }
    [[ "$(http_json /collections | jq -r '.result.collections | length')" == 0 ]] \
      || { systemctl stop qdrant-migration-step.service || true; fail_stage; }
  fi
  run systemctl stop qdrant-migration-step.service || fail_stage

  stage='provision HMAC secret'
  if [[ ! -e "${config_dir}/qdrant.env" ]]; then
    run install -o root -g qdrant -m 0640 /dev/null "${config_dir}/qdrant.env" || fail_stage
    if (( apply )); then
      { print -rn -- QDRANT__SERVICE__API_KEY=; openssl rand -hex 32; } >| "${config_dir}/qdrant.env" || fail_stage
    else
      note "DRY-RUN: write QDRANT__SERVICE__API_KEY=<openssl rand -hex 32> to ${config_dir}/qdrant.env"
    fi
  fi

  stage='install 1.19.0'
  run pacman -S --needed --noconfirm "${repo}/qdrant" "${repo}/qdrant-web-ui" || fail_stage
  if (( apply )); then
    [[ ! -e "${config_dir}/config.yaml.pacnew" ]] || fail_stage
    config_unmodified || fail_stage
  fi
  run systemctl daemon-reload || fail_stage
  run systemctl start qdrant.service || fail_stage

  if (( apply )); then
    stage='create collections'
    wait_for_version 1.19.0 || fail_stage
    make_private_dir
    admin=$(admin_header)
    create_collections "$admin" || fail_stage

    stage='snapshot restore drill'
    snapshot_restore_drill "$admin" || fail_stage

    stage='deliver runtime JWT'
    install -d -m 0700 -- "$credstore" || fail_stage
    mint_jwt prw 0 | systemd-creds encrypt --name="$credential_name" - \
      "${credstore}/open-webui.${credential_name}" || fail_stage
  else
    note "DRY-RUN: create ${collection_prefix}_{${(j:,:)collection_suffixes}} (2560, Cosine, payload indexes tenant_id/metadata.hash/metadata.file_id)"
    note "DRY-RUN: snapshot and restore ${collection_prefix}_memories while empty"
    note "DRY-RUN: systemd-creds encrypt --name=${credential_name} <prw JWT> ${credstore}/open-webui.${credential_name}"
    note "DRY-RUN: restart qdrant.service, then verify (the collections must survive the restart)"
    hand_back "qdrant cutover dry run complete; rerun as root with --apply"
    return
  fi

  stage='restart persistence check'
  systemctl restart qdrant.service || fail_stage
  wait_for_version 1.19.0 || fail_stage

  stage='verify'
  do_verify || fail_stage
  hand_back "qdrant cutover COMPLETE on 1.19.0-1; rollback set ${set_dir} retained"
}

do_verify() {
  local name admin runtime readonly_h code listeners point vector before after
  note "== verify"
  (( EUID == 0 )) || die "verify reads the HMAC secret and the runtime credential; run it as root"
  for name in qdrant-migration qdrant qdrant-web-ui; do
    [[ "$(pacman -Q "$name" 2>/dev/null | awk '{print $2}')" == "${want_version[$name]}" ]] \
      || refuse "installed ${name} is not ${want_version[$name]}"
  done
  [[ "$(http_json / 2>/dev/null | jq -r '.version // empty')" == 1.19.0 ]] || refuse "running Qdrant is not 1.19.0"
  [[ "$(http_code GET /readyz)" == 200 ]] || refuse "Qdrant /readyz is not 200"
  listeners=$(ss -ltnH '( sport = :6333 or sport = :6334 or sport = :6335 )' | awk '{print $4}')
  for code in 127.0.0.1:6333 127.0.0.1:6334; do
    (( ${${(f)listeners}[(Ie)$code]} )) || refuse "Qdrant is not listening on ${code}"
  done
  for code in ${(f)listeners}; do
    [[ "$code" == 127.0.0.1:6333 || "$code" == 127.0.0.1:6334 ]] || refuse "non-loopback or unexpected listener ${code}"
  done
  [[ "$(http_code GET /collections)" == 401 ]] || refuse "unauthenticated GET /collections was not refused with 401"
  check_disk

  make_private_dir
  admin=$(admin_header)
  for name in "${collection_suffixes[@]}"; do
    name="${collection_prefix}_${name}"
    http_json "/collections/${name}" "$admin" | jq -e '
      .result.config.params.vectors.size == 2560 and .result.config.params.vectors.distance == "Cosine"
      and (.result.payload_schema | has("tenant_id") and has("metadata.hash") and has("metadata.file_id"))' >/dev/null \
      || refuse "collection ${name} is missing or has the wrong shape"
  done

  runtime=$(systemd-creds decrypt --name="$credential_name" "${credstore}/open-webui.${credential_name}" - | bearer_header runtime)
  readonly_h=$(mint_jwt r 300 | bearer_header readonly)
  name="${collection_prefix}_knowledge"
  # A fresh ID per run, confirmed absent, so the smoke write cannot overwrite
  # or later delete an existing point.
  point=$(</proc/sys/kernel/random/uuid)
  [[ "$(http_code GET "/collections/${name}/points/${point}" "$admin")" == 404 ]] \
    || refuse "smoke point ID ${point} is not free in ${name}"
  vector=$(jq -nc '[1] + [range(2559) | 0]')
  before=$(http_json "/collections/${name}" "$admin" | jq -r '.result.points_count')
  [[ "$(http_code PUT "/collections/${name}/points?wait=true" "$runtime" \
    "{\"points\":[{\"id\":\"${point}\",\"vector\":${vector},\"payload\":{\"tenant_id\":\"qdrant-cutover-smoke\"}}]}")" == 200 ]] \
    || refuse "runtime prw JWT could not write to ${name}"
  [[ "$(http_code PUT "/collections/${name}/points?wait=true" "$readonly_h" \
    "{\"points\":[{\"id\":\"${point}\",\"vector\":${vector},\"payload\":{\"tenant_id\":\"qdrant-cutover-smoke\"}}]}")" == 403 ]] \
    || refuse "read-only JWT was not refused a write with 403"
  [[ "$(http_code PUT "/collections/${collection_prefix}_smoke" "$runtime" \
    '{"vectors":{"size":4,"distance":"Cosine"}}')" == 403 ]] \
    || refuse "runtime prw JWT was not refused collection creation with 403"
  [[ "$(http_code POST "/collections/${name}/points/delete?wait=true" "$runtime" "{\"points\":[\"${point}\"]}")" == 200 ]] \
    || refuse "runtime prw JWT could not delete its smoke point"
  after=$(http_json "/collections/${name}" "$admin" | jq -r '.result.points_count')
  [[ "$before" == "$after" ]] || refuse "smoke point count did not return to ${before} (now ${after})"
  if (( $#refusals )); then
    return 1
  fi
  note "verify: all checks passed"
}

do_rollback() {
  local set_dir="${rollback_root}/${rollback_set}" failed_dir name
  note "== rollback"
  [[ -f "${set_dir}/MANIFEST" && -d "${set_dir}/state" && -d "${set_dir}/config" ]] \
    || { refuse "rollback set ${set_dir} is incomplete"; finish_or_refuse rollback; }
  check_baseline_archive "${set_dir}/${baseline_file}"
  [[ -r "${set_dir}/state.sha256" ]] \
    && (cd "${set_dir}/state" && sha256sum --quiet -c "${set_dir}/state.sha256") \
    || refuse "saved state in ${set_dir} does not match state.sha256 (or is unreadable; run as root)"
  finish_or_refuse rollback
  (( apply )) || note "(dry run: pass --apply as root to perform these steps)"
  failed_dir="${storage_dir}.failed-$(date -u +%Y%m%dT%H%M%SZ)"

  rollback_failed() {
    hand_back "qdrant rollback FAILED at '$1'; the rollback set ${set_dir} is untouched; failed state (if moved) is at ${failed_dir}"
    exit 1
  }
  run systemctl stop qdrant.service || rollback_failed 'stop qdrant'
  if [[ -e "$storage_dir" ]]; then
    run mv -- "$storage_dir" "$failed_dir" || rollback_failed 'move failed state aside'
  fi
  run cp -a --reflink=auto -- "${set_dir}/state" "$storage_dir" || rollback_failed 'restore state'
  run pacman -U --noconfirm "${set_dir}/${baseline_file}" || rollback_failed "install ${baseline_version}"
  for name in qdrant-web-ui qdrant-migration; do
    if ! grep -q "^installed ${name} " "${set_dir}/MANIFEST" && pacman -Q "$name" >/dev/null 2>&1; then
      run pacman -R --noconfirm "$name" || rollback_failed "remove ${name}"
    fi
  done
  run install -m 0644 -- "${set_dir}/config/config.yaml" "${config_dir}/config.yaml" || rollback_failed 'restore config'
  run systemctl daemon-reload || rollback_failed 'daemon-reload'
  run systemctl start qdrant.service || rollback_failed 'start qdrant'
  if (( apply )); then
    wait_for_version "${baseline_version%-*}" || rollback_failed "wait for ${baseline_version%-*}"
    hand_back "qdrant rollback COMPLETE on ${baseline_version}; failed 1.19 state kept at ${failed_dir}"
  else
    hand_back "qdrant rollback dry run complete; rerun as root with --apply"
  fi
}

(( $# )) || { usage; exit 2; }
command=$1
shift
case "$command" in
  preflight|cutover|verify|rollback) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; die "unknown subcommand: ${command}" ;;
esac

while (( $# )); do
  case "$1" in
    --apply) apply=1; shift ;;
    --url|--storage-dir|--config-dir|--repo|--sync-db|--pkg-cache|--rollback-root|--rollback-set|--credstore|--disk-quota-percent)
      (( $# >= 2 )) || die "$1 requires a value"
      case "$1" in
        --url) url=$2 ;;
        --storage-dir) storage_dir=$2 ;;
        --config-dir) config_dir=$2 ;;
        --repo) repo=$2 ;;
        --sync-db) sync_db=$2 ;;
        --pkg-cache) pkg_cache=$2 ;;
        --rollback-root) rollback_root=$2 ;;
        --rollback-set) rollback_set=$2 ;;
        --credstore) credstore=$2 ;;
        --disk-quota-percent) disk_quota_percent=$2 ;;
      esac
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ "$disk_quota_percent" == <1-100> ]] || die "--disk-quota-percent must be 1-100"
[[ "$rollback_set" == [A-Za-z0-9._-]## && "$rollback_set" != .* ]] || die "--rollback-set must be a plain name"
[[ -n "$sync_db" ]] || sync_db=/var/lib/pacman/sync/${repo}.db
[[ "$command" != preflight ]] || (( ! apply )) || die "preflight is read-only; --apply does not apply"
require_root_for_apply

case "$command" in
  preflight)
    do_preflight
    finish_or_refuse preflight
    hand_back "qdrant preflight PASSED; cutover may proceed"
    ;;
  cutover) do_cutover ;;
  verify)
    do_verify || { hand_back "qdrant verify FAILED (${#refusals} check(s)); consider rollback"; exit 1; }
    hand_back "qdrant verify PASSED on 1.19.0-1"
    ;;
  rollback) do_rollback ;;
esac
