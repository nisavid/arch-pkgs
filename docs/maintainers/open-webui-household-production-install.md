# Open WebUI household production install

This is the owner handoff for
[Deploy the accepted Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/59).
It replaces the host's out-of-band `open-webui` 0.11.0-1 with the published
0.11.0-5 identity, served through the host's existing `:443` terminator to
the service's Unix socket. The former state is retained, never migrated.

Every privileged step belongs to the owner. Each phase lists its exact
commands, its rollback, the HAND-BACK phrase the owner replies with, and the
unprivileged checks the agent runs afterwards. There is no new privileged
script: the commands are here, and the only scripts involved are the packaged
helpers and the Qdrant cutover route from
[Deploy the accepted Qdrant service](https://github.com/nisavid/arch-pkgs/issues/58).

Placeholders: `<kit-checkout>` is a root-readable checkout of this repository
at the kit commit recorded in the acceptance evidence; `<root>` is the kept
acceptance root; `<household-origin>` is the HTTPS origin that
[P5.0](#p50-owner-decisions-pending) yields, such as
`https://<name>.<tailnet-domain>`.

Fixed values: the chat model is the owner-pinned
`user.Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL` (Lemonade may list its bare form,
`Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL`; both count as the same model), and the
Whisper model is `base`, pinned as `Systran/faster-whisper-base` at revision
`ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66` (file digests in
[P3.6](#p36-whisper-model)). `tiny` is used only if the lead names it.

## Preconditions

The agent checks these read-only before the window opens:

- The acceptance evidence from
  [Acceptance-deploy the Open WebUI household candidate set](https://github.com/nisavid/arch-pkgs/issues/89)
  has merged, and
  [Promote or defer the Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/90)
  promoted the stack.
- [Publish the accepted-only package repository](https://github.com/nisavid/arch-pkgs/issues/57)
  is done: `pacman -Si nisavid/open-webui nisavid/python-rapidocr nisavid/python-faster-whisper`
  shows 0.11.0-5, 3.9.2-1, and 1.2.1-1, and the sync-database SHA-256 values
  equal the candidate manifest.
- The Qdrant cutover route has merged:
  [feat(qdrant): add production cutover route and rebind accepted candidates](https://github.com/nisavid/arch-pkgs/pull/93).
- The Lemonade M4 receipts are cited, and Lemonade serves and has loaded the
  packaged zembed and zerank ids and the owner-pinned chat model.
- The owner has recorded the [P5.0](#p50-owner-decisions-pending) decisions,
  because P3.4 writes `<household-origin>` before the first start.
- No file under `/opt/open-webui` is unowned by pacman (a hard precondition,
  because P2 replaces the same package name in place):

  ```bash
  s=$(mktemp -d)
  find /opt/open-webui -xdev | LC_ALL=C sort >"$s/fs"
  pacman -Qlq open-webui | sed 's:/$::' | LC_ALL=C sort >"$s/owned"
  comm -23 "$s/fs" "$s/owned"   # must print nothing
  rm -r "$s"
  ```

- One household window is agreed for the Qdrant cutover and this install
  together, because the Qdrant preflight refuses while the current
  `open-webui.service` is active.

Runtime dependencies come through pacman: `open-webui` depends on `caddy`,
`qdrant`, and `valkey`, and `python-rapidocr` pulls in `python-omegaconf` and
`python-antlr4`.

## P0: stop and retain the current install

```bash
sudo systemctl disable --now open-webui.service
sudo mv /var/lib/open-webui /var/lib/open-webui.legacy-0.11.0-1
sudo cp -a /etc/open-webui /var/lib/open-webui.legacy-0.11.0-1.etc
```

The retained state is data only. It is never restored automatically and is
kept until
[Release retained rollback anchors and clean target-local state](https://github.com/nisavid/arch-pkgs/issues/62).

- Rollback (before P2 only):
  `sudo mv /var/lib/open-webui.legacy-0.11.0-1 /var/lib/open-webui && sudo systemctl enable --now open-webui.service`
- HAND-BACK: `HAND-BACK: open-webui P0 legacy stopped and retained`
- Agent: `systemctl is-active open-webui.service` is inactive, and
  `ss -ltnH 'sport = :8080'` prints nothing.

## P1: Qdrant cutover

Follow the runbook in
[feat(qdrant): add production cutover route and rebind accepted candidates](https://github.com/nisavid/arch-pkgs/pull/93)
for
[Deploy the accepted Qdrant service](https://github.com/nisavid/arch-pkgs/issues/58):

```bash
sudo tools/qdrant_production_cutover.zsh preflight
sudo tools/qdrant_production_cutover.zsh cutover
sudo tools/qdrant_production_cutover.zsh cutover --apply
sudo tools/qdrant_production_cutover.zsh verify
```

The cutover creates the five `open-webui-rag-v1` collections and delivers the
runtime credential to
`/etc/credstore.encrypted/open-webui.qdrant-runtime-api-key`. The Qdrant
administrative key stays with the owner.

- Rollback: the Qdrant runbook's `rollback --apply`.
- HAND-BACK: the script's own `HAND-BACK: qdrant verify PASSED on 1.19.0-1`.
- Agent: the Qdrant runbook's post-verification.

## P2: install the packages

Run on a fully upgraded host (the owner's routine `sudo pacman -Syu`), with
Qdrant held as the Qdrant runbook says.

```bash
sudo pacman -S nisavid/open-webui nisavid/python-rapidocr nisavid/python-faster-whisper
```

- pacman asks to remove `python-rapidocr-onnxruntime`, because
  `python-rapidocr` conflicts with it. Answer **yes**.
- Do not add `--needed`: the installed `python-faster-whisper` 1.2.1-1 is a
  different build and must be replaced.
- `open-webui` 0.11.0-1 is replaced in place. Its unowned legacy files under
  `/etc/open-webui` were copied in P0.
- Leave `open-webui.service` and `caddy.service` disabled.

Rollback, if P2 is aborted: `sudo systemctl disable --now open-webui.service`,
and reinstall `python-rapidocr-onnxruntime` with `sudo pacman -U` only if its
archive is still in the package cache. The service stays closed; the former
package is not a rollback target.

- HAND-BACK: `HAND-BACK: open-webui P2 installed 0.11.0-5`
- Agent:
  - `pacman -Q open-webui python-rapidocr python-faster-whisper` shows the
    published versions;
  - `sha256sum /var/cache/pacman/pkg/{open-webui-0.11.0-5-x86_64,python-rapidocr-3.9.2-1-any,python-faster-whisper-1.2.1-1-any}.pkg.tar.zst`
    equals the promotion record;
  - `pacman -Q python-rapidocr-onnxruntime` fails;
  - `pacman -Qi caddy python-omegaconf python-antlr4` succeeds;
  - `id -nG caddy` includes `open-webui-proxy`;
  - `systemctl is-enabled open-webui.service caddy.service` shows both
    disabled.

### Optional: remove hayhooks

Hayhooks is installed but disabled on the host. That is not a failure for
this install; its removal belongs to
[Release retained rollback anchors and clean target-local state](https://github.com/nisavid/arch-pkgs/issues/62).
If the owner removes it now:

```bash
sudo pacman -Rns hayhooks
```

- Rollback: `sudo pacman -U` the cached `hayhooks` archive.
- HAND-BACK: `HAND-BACK: hayhooks removed`
- Agent: `pacman -Q hayhooks` fails.

## P3: credentials, Valkey, connection seed, epoch, and model

### P3.1 Stable keys

```bash
for n in webui-secret-key oauth-client-info-encryption-key oauth-session-token-encryption-key; do
  openssl rand -hex 32 \
    | sudo systemd-creds encrypt --name="$n" - "/etc/credstore.encrypted/open-webui.$n"
done
```

### P3.2 Dedicated Valkey

The configuration uses RDB only, loopback only, and an ACL file whose default
user is off. The ACL rule set is the one the kit template
`tools/templates/open-webui-household/valkey-open-webui.acl.in` carries,
including `-flushall -flushdb`; a test compares the `printf` line below with
that template, so the two cannot drift.

```bash
sudo install -d -o valkey -g valkey -m 0700 /var/lib/valkey/open-webui

sudo install -m 0640 -o root -g valkey /dev/stdin /etc/valkey/open-webui.conf <<'EOF'
bind 127.0.0.1
port 6379
protected-mode yes
aclfile /etc/valkey/open-webui.acl
maxmemory-policy noeviction
appendonly no
save 900 1 300 10 60 10000
dir /var/lib/valkey/open-webui
dbfilename dump.rdb
EOF

pw=$(openssl rand -hex 32)
hash=$(printf '%s' "$pw" | sha256sum | cut -d' ' -f1)
printf 'user default off\nuser open-webui on #%s ~* &* +@all -@admin -flushall -flushdb\n' "$hash" \
  | sudo install -m 0640 -o root -g valkey /dev/stdin /etc/valkey/open-webui.acl
printf 'redis://open-webui:%s@127.0.0.1:6379/0' "$pw" \
  | sudo systemd-creds encrypt --name=valkey-url - /etc/credstore.encrypted/open-webui.valkey-url
unset pw hash

sudo install -D -m 0644 /dev/stdin /etc/systemd/system/valkey.service.d/10-open-webui.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/valkey-server /etc/valkey/open-webui.conf --supervised systemd
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now valkey.service
```

The password never reaches the screen, an argument list, or shell history; the
ACL stores only its SHA-256.

- Rollback:
  `sudo systemctl disable --now valkey.service && sudo rm /etc/systemd/system/valkey.service.d/10-open-webui.conf /etc/valkey/open-webui.conf /etc/valkey/open-webui.acl /etc/credstore.encrypted/open-webui.valkey-url && sudo systemctl daemon-reload`
- Agent: `systemctl is-active valkey.service` is active;
  `ss -ltnH 'sport = :6379'` shows only `127.0.0.1`; `valkey-cli -p 6379 ping`
  is refused for the disabled default user.

### P3.3 Qdrant runtime credential

P1 delivered it. Confirm:

```bash
sudo test -s /etc/credstore.encrypted/open-webui.qdrant-runtime-api-key && echo present
```

### P3.4 Connection seed and speech settings

The packaged `open-webui.env` carries the chat connection seed from 0.11.0-5
on: exactly `ENABLE_OLLAMA_API=false`,
`OPENAI_API_BASE_URLS=http://127.0.0.1:13305/api/v1`, and an empty
`OPENAI_API_KEYS`. No seed file is installed. In Open WebUI 0.11 these are
persistent-config seeds: they apply on first start, and later edits need an
admin re-save.

Two drop-ins complete the environment. They are not part of the seed:

- `20-speech.conf` sets only the two local Whisper settings the acceptance
  unit carried: `WHISPER_MODEL=base` and `HF_HUB_OFFLINE=1`, so a Whisper load
  failure can never fall back to the network.
- `30-origin.conf` sets `WEBUI_URL` and `CORS_ALLOW_ORIGIN` from the P5.0
  table. `WEBUI_URL` is a persistent-config seed, so it must be in place
  before the first start; a later change goes through Admin Settings,
  General, "WebUI URL". `CORS_ALLOW_ORIGIN` is the origin only (scheme and
  host), even when variant B serves the app under a path.

Install both before the first start. First confirm the installed env: it must
print the three seed lines above and nothing for the other four keys. An
environment file overrides `Environment=`, so if it sets any of them, or a
seed value differs, stop and ask the lead:

```bash
sudo grep -E '^(ENABLE_OLLAMA_API|OPENAI_API_BASE_URLS|OPENAI_API_KEYS|WHISPER_MODEL|HF_HUB_OFFLINE|WEBUI_URL|CORS_ALLOW_ORIGIN)=' /etc/open-webui/open-webui.env
```

```bash
sudo install -D -m 0644 /dev/stdin /etc/systemd/system/open-webui.service.d/20-speech.conf <<'EOF'
[Service]
Environment=WHISPER_MODEL=base
Environment=HF_HUB_OFFLINE=1
EOF
sudo install -D -m 0644 /dev/stdin /etc/systemd/system/open-webui.service.d/30-origin.conf <<'EOF'
[Service]
Environment=WEBUI_URL=<household-origin>
Environment=CORS_ALLOW_ORIGIN=<household-origin-without-path>
EOF
sudo systemctl daemon-reload
```

- Rollback (before P4 only):
  `sudo rm /etc/systemd/system/open-webui.service.d/{20-speech,30-origin}.conf && sudo systemctl daemon-reload`

### P3.5 Session epoch

```bash
sudo /usr/lib/open-webui/open-webui-session-epoch-ledger initialize
```

The ledger is forward-only. It has no rollback and is never reset.

### P3.6 Whisper model

Build the Hugging Face cache layout from the flat snapshot the acceptance
trial verified. `teardown --keep-anchor` keeps it at
`<root>/inputs/faster-whisper-base/`. `refs/main` holds the pinned revision,
as the kit's own placement does. Only the four pinned files are installed, so
Open WebUI loads the model offline (`HF_HUB_OFFLINE=1`) from exactly these
bytes:

| File | SHA-256 |
| --- | --- |
| `config.json` | `56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a` |
| `model.bin` | `d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9` |
| `tokenizer.json` | `fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab` |
| `vocabulary.txt` | `34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913` |

```bash
m=/var/lib/open-webui/cache/whisper/models/models--Systran--faster-whisper-base
rev=ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66
src=<root>/inputs/faster-whisper-base
sudo install -d -o open-webui -g open-webui -m 0750 "$m" "$m/refs" "$m/snapshots" "$m/snapshots/$rev"
sudo install -o open-webui -g open-webui -m 0640 -t "$m/snapshots/$rev" \
  "$src/config.json" "$src/model.bin" "$src/tokenizer.json" "$src/vocabulary.txt"
printf '%s' "$rev" | sudo install -o open-webui -g open-webui -m 0640 /dev/stdin "$m/refs/main"
sudo sh -c 'cd "$1" && sha256sum config.json model.bin tokenizer.json vocabulary.txt' sh "$m/snapshots/$rev"
unset m rev src
```

The four printed digests must equal the table above, which the acceptance
evidence also records.

- Rollback (before P4 only):
  `sudo rm -r /var/lib/open-webui/cache/whisper/models/models--Systran--faster-whisper-base`

- HAND-BACK: `HAND-BACK: open-webui P3 credentials, valkey, epoch ready`
- Agent: `systemctl show open-webui.service -p DropInPaths` lists
  `20-speech.conf` and `30-origin.conf`, and the P3.2 Valkey checks pass.

## P4: closed-route commissioning

No `:443` route points at the socket yet, so nothing outside the host can
reach it.

1. The owner types the four admin values; none pass through an agent:

   ```bash
   for n in admin-email admin-name admin-bootstrap-password admin-final-password; do
     systemd-ask-password -n "$n" \
       | sudo systemd-creds encrypt --name="$n" - "/etc/credstore.encrypted/open-webui.$n"
   done
   ```

2. Add the temporary bootstrap drop-in:

   ```bash
   sudo install -D -m 0644 /dev/stdin /etc/systemd/system/open-webui.service.d/10-bootstrap.conf <<'EOF'
   [Service]
   LoadCredentialEncrypted=admin-email:/etc/credstore.encrypted/open-webui.admin-email
   LoadCredentialEncrypted=admin-name:/etc/credstore.encrypted/open-webui.admin-name
   LoadCredentialEncrypted=admin-bootstrap-password:/etc/credstore.encrypted/open-webui.admin-bootstrap-password
   EOF
   ```

3. First start, then the root commissioning command:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start open-webui.service
   sudo curl -sf --unix-socket /run/open-webui/open-webui.sock http://localhost/ready
   sudo systemd-run --pipe --wait --collect \
     -p LoadCredentialEncrypted=admin-email:/etc/credstore.encrypted/open-webui.admin-email \
     -p LoadCredentialEncrypted=admin-name:/etc/credstore.encrypted/open-webui.admin-name \
     -p LoadCredentialEncrypted=admin-bootstrap-password:/etc/credstore.encrypted/open-webui.admin-bootstrap-password \
     -p LoadCredentialEncrypted=admin-final-password:/etc/credstore.encrypted/open-webui.admin-final-password \
     /usr/lib/open-webui/open-webui-commission-admin
   ```

4. Configure the chat model over the socket with the kit's shared `configure`
   helper, the same code the acceptance trial ran:

   ```bash
   sudo systemd-run --pipe --wait --collect \
     -p LoadCredentialEncrypted=admin-email:/etc/credstore.encrypted/open-webui.admin-email \
     -p LoadCredentialEncrypted=admin-final-password:/etc/credstore.encrypted/open-webui.admin-final-password \
     /usr/bin/python3 <kit-checkout>/tools/open_webui_household_scenarios.py configure \
       --socket /run/open-webui/open-webui.sock
   ```

   `--chat-model` defaults to the owner-pinned id; the helper sets whichever
   form Open WebUI lists as the default model.

5. Remove the bootstrap inputs and restart normally:

   ```bash
   sudo rm /etc/systemd/system/open-webui.service.d/10-bootstrap.conf \
     /etc/credstore.encrypted/open-webui.admin-bootstrap-password
   sudo systemctl daemon-reload
   sudo systemctl enable open-webui.service
   sudo systemctl restart open-webui.service
   sudo curl -sf --unix-socket /run/open-webui/open-webui.sock http://localhost/api/config \
     | jq -e '.features.enable_signup == false'
   ```

- Rollback: `sudo systemctl disable --now open-webui.service`. The route never
  opened, and `:8080` is never restored.
- HAND-BACK: `HAND-BACK: open-webui P4 commissioned, route closed`
- Agent: `systemctl show open-webui.service -p ActiveState,NRestarts,Result`
  is active with no restarts; `DropInPaths` no longer lists
  `10-bootstrap.conf`.

## P5: open the route

The host's existing `:443` terminator is Tailscale Serve, run by `tailscaled`.
It listens on the host's tailnet addresses only, provisions certificates
automatically for MagicDNS names, and can proxy straight to a Unix socket.
`tailscaled` runs as root, so it can reach `/run/open-webui/open-webui.sock`.

### P5.0 Owner decisions pending

Record both decisions on
[Deploy the accepted Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/59)
before P3, because P3.4 writes `<household-origin>` before the first start:

- **OWNER DECISION PENDING: the variant.** Variant A gives Open WebUI its own
  Tailscale Service name. Variant B adds a path to the host's existing HTTPS
  handler.
- **OWNER DECISION PENDING: whether the package's Caddy stays in the path.**
  If it stays, install a site block that listens on loopback only and proxies
  to the socket, enable `caddy.service`, and use Caddy's listener as the Serve
  target in place of `unix:/run/open-webui/open-webui.sock`. If it does not,
  `caddy.service` stays disabled.

The variant sets `<household-origin>`, which P3.4 writes as `WEBUI_URL`:

| Variant | `<household-origin>` | `CORS_ALLOW_ORIGIN` |
| --- | --- | --- |
| A | `https://<name>.<tailnet-domain>` | the same |
| B | `https://<host-name>.<tailnet-domain>/<path>` | `https://<host-name>.<tailnet-domain>` |

### P5.1 Variant A: a dedicated Tailscale Service

Owner prerequisites, in the Tailscale admin console: define the service
`svc:<name>`, give the host the tags the service requires, and approve the
host as a proxy for the service after the command below advertises it.

```bash
sudo tailscale serve --bg --service=svc:<name> --https=443 unix:/run/open-webui/open-webui.sock
sudo tailscale serve status
```

`tailscale serve status` must list `svc:<name>` with HTTPS on 443 proxying to
`unix:/run/open-webui/open-webui.sock`, and nothing else must change.

- Rollback:
  `sudo tailscale serve --service=svc:<name> --https=443 unix:/run/open-webui/open-webui.sock off`,
  then `sudo tailscale serve status` shows no `svc:<name>` handler. Remove the
  service definition in the admin console if it is no longer wanted.

### P5.1 Variant B: a path on the host's existing HTTPS handler

```bash
sudo tailscale serve status   # record the current handlers first
sudo tailscale serve --bg --https=443 --set-path=/<path> unix:/run/open-webui/open-webui.sock
sudo tailscale serve status
```

The second `status` must show the recorded handlers unchanged plus `/<path>`
proxying to `unix:/run/open-webui/open-webui.sock`.

Open WebUI does not document serving under a path prefix. The agent's
post-verification therefore also loads the UI assets and the WebSocket under
`/<path>`; if they fail, roll back and choose again in P5.0.

- Rollback:
  `sudo tailscale serve --https=443 --set-path=/<path> off`, then
  `sudo tailscale serve status` matches the handlers recorded first.

### P5.2 Hand-back and verification

- HAND-BACK: `HAND-BACK: open-webui P5 route open (variant <A|B>)`
- Agent, unprivileged:
  - `tailscale serve status` shows the handler from the chosen variant, and
    its target is the socket (or Caddy's loopback listener, if Caddy stays);
  - the TLS name: `curl -sS -o /dev/null -w '%{http_code}\n' <household-origin>/`
    returns 200 with default certificate verification, so the certificate
    matches the origin's MagicDNS name;
  - the route reaches the socket:
    `curl -sS <household-origin>/api/config | jq -e '.features.enable_signup == false'`
    succeeds;
  - an authenticated WebSocket upgrade returns 101;
  - `ss -ltnH 'sport = :8080'` prints nothing, and no Open WebUI TCP listener
    exists.

### P5.3 The smoke account

If the lead and owner approve a dedicated non-admin smoke account for the
re-smoke, the owner creates it in the admin UI, grants it access to the
owner-pinned chat model, and stores its credentials as the acceptance
runbook's re-smoke section shows. The account is never an admin.

- HAND-BACK: `HAND-BACK: open-webui smoke account ready`
- Agent: the re-smoke precondition passes: the account signs in and Open
  WebUI lists the chat model for it.

## P6: production anchor

### P6.1 Create the anchor directory

```bash
sudo install -d -m 0700 /var/lib/arch-pkgs-anchors
```

### P6.2 Take the anchor

Quiesce writers, copy the state tuple, then restart. With Open WebUI stopped,
the `:443` route fails closed. Valkey saves its RDB when it stops.

```bash
a=/var/lib/arch-pkgs-anchors/open-webui-0.11.0-5-$(date -u +%Y%m%dT%H%M%SZ)
sudo install -d -m 0700 "$a" "$a/credstore" "$a/archives" "$a/qdrant"
sudo systemctl stop open-webui.service valkey.service
sudo cp -a /var/lib/open-webui/data "$a/open-webui-data"
sudo cp -a /var/lib/valkey/open-webui/dump.rdb "$a/"
sudo sh -c 'cp -a /etc/credstore.encrypted/open-webui.* "$1/credstore/"' sh "$a"
sudo /usr/lib/open-webui/open-webui-session-epoch-ledger current | sudo tee "$a/epoch-bound"
sudo cp -a /var/cache/pacman/pkg/{open-webui-0.11.0-5-x86_64,python-rapidocr-3.9.2-1-any,python-faster-whisper-1.2.1-1-any}.pkg.tar.zst "$a/archives/"
```

With Open WebUI stopped, take the five collection snapshots with the Qdrant
administrative key as the Qdrant runbook describes, and copy them into
`"$a/qdrant/"`. Then record the digests and reopen:

```bash
sudo sh -c 'cd "$1" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + >SHA256SUMS' sh "$a"
sudo systemctl start valkey.service open-webui.service
```

The acceptance drill receipts and this anchor together record the drills for
this install, unless the lead asks for production drills.

- Rollback: none needed; the anchor is additive.
- HAND-BACK: `HAND-BACK: open-webui P6 anchor retained <anchor-id>`
- Agent: HTTPS 200 again after reopening.

## P7: owner-run verification

These read root-only state. The environ read prints only the five telemetry
keys.

```bash
pid=$(systemctl show -p MainPID --value open-webui.service)
sudo cat "/proc/$pid/environ" | tr '\0' '\n' \
  | grep -E '^(ANONYMIZED_TELEMETRY|DO_NOT_TRACK|SCARF_NO_ANALYTICS|ENABLE_VERSION_UPDATE_CHECK|OFFLINE_MODE)='
sudo ss -tnp | grep "pid=$pid,"
sudo /usr/lib/open-webui/open-webui-session-epoch-ledger current
```

Expected: `ANONYMIZED_TELEMETRY=false`, `DO_NOT_TRACK=true`,
`SCARF_NO_ANALYTICS=true`, `ENABLE_VERSION_UPDATE_CHECK=false`, and
`OFFLINE_MODE=true`; the only peers are the Lemonade provider, Qdrant, and
Valkey.

Then, signed in as the admin:

1. The Users page shows exactly one admin.
2. Reranker down: in Admin Settings, Documents, set the external reranker URL
   to an unused loopback URL and save. Ordinary chat returns 200; a
   file-attached chat and retrieval return 503 with no citation.
3. Restore the packaged reranker URL and save. Retrieval health returns 200,
   and a cited answer carries a finite score.

- HAND-BACK: `HAND-BACK: open-webui verify PASSED on 0.11.0-5`

## Agent post-verification

Unprivileged, after P7:

- the pacman identities and cached-archive SHA-256 values;
- `systemctl show open-webui.service -p User,IPAddressDeny,IPAddressAllow,NRestarts,Result,DropInPaths`,
  which covers every row of the acceptance A-ID2 table;
- `ss -ltnH 'sport = :8080'` prints nothing, and no Open WebUI TCP listener;
- HTTPS 200 and WebSocket 101 at `<household-origin>`;
- the re-smoke set against production, per the acceptance runbook, if the
  smoke account exists;
- `systemctl is-active hayhooks.service` and `systemctl is-enabled hayhooks.service`
  report inactive and disabled (or `pacman -Q hayhooks` fails if removed).

The acceptance trial values are the baseline.

## Rollback

- **Before P5:** `sudo systemctl disable --now open-webui.service`. The route
  was never opened.
- **After P5, to the anchor:**

  ```bash
  # first close the route with the chosen P5 variant's rollback
  sudo systemctl stop open-webui.service
  sudo /usr/lib/open-webui/open-webui-session-epoch-ledger reserve
  sudo sh -c 'cd "$1" && sha256sum -c SHA256SUMS' sh <anchor>
  sudo pacman -U <anchor>/archives/{open-webui-0.11.0-5-x86_64,python-rapidocr-3.9.2-1-any,python-faster-whisper-1.2.1-1-any}.pkg.tar.zst
  ```

  Then restore the tuple: stop Valkey and replace its `dump.rdb`, replace
  `/var/lib/open-webui/data`, the encrypted credential files, and recover the
  five Qdrant snapshots as the Qdrant runbook describes. Start Valkey and Open
  WebUI, check SQLite `quick_check`, the digests, the collection shapes, that
  a pre-anchor session is rejected, and that a fresh login works; then
  reopen the route with the chosen P5 variant.

  - HAND-BACK: `HAND-BACK: open-webui rollback PASSED to anchor <anchor-id>`

- The Qdrant rollback stays with the Qdrant runbook.
- The former wildcard `:8080` service is never re-enabled. The legacy state
  from P0 stays retained until the anchor-release ticket.

## Later restarts

The re-smoke may ask for a restart when the reranker gate latched during a
Lemonade redeploy, or after the speech provider is rebuilt:

```bash
sudo systemctl restart open-webui.service
```

- HAND-BACK: `HAND-BACK: open-webui restarted`
- Agent: rerun the re-smoke once.
