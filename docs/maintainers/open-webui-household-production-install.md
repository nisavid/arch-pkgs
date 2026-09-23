# Open WebUI household production install

This is the owner handoff for
[Deploy the accepted Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/59).
It replaces the host's out-of-band `open-webui` 0.11.0-1 with the published
0.11.0-4 identity behind a Caddy HTTPS route to the service's Unix socket. The
former state is retained, never migrated.

Every privileged step belongs to the owner. Each phase lists its exact
commands, its rollback, the HAND-BACK phrase the owner replies with, and the
unprivileged checks the agent runs afterwards. There is no new privileged
script: the commands are here, and the only scripts involved are the packaged
helpers and the Qdrant cutover route from
[Deploy the accepted Qdrant service](https://github.com/nisavid/arch-pkgs/issues/58).

Placeholders: `<kit-checkout>` is a root-readable checkout of this repository
at the kit commit recorded in the acceptance evidence; `<root>` is the kept
acceptance root; `<chat-model>` and `<whisper-model>` are the lead's choices;
`<whisper-revision>` is the Whisper revision pinned in the acceptance evidence;
`<provider-base-url>` is the `RAG_OPENAI_API_BASE_URL` value in the installed
`/etc/open-webui/open-webui.env`; `<household-origin>` is the owner's HTTPS
origin.

## Preconditions

The agent checks these read-only before the window opens:

- The acceptance evidence from
  [Acceptance-deploy the Open WebUI household candidate set](https://github.com/nisavid/arch-pkgs/issues/89)
  has merged, and
  [Promote or defer the Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/90)
  promoted the stack.
- [Publish the accepted-only package repository](https://github.com/nisavid/arch-pkgs/issues/57)
  is done: `pacman -Si nisavid/open-webui nisavid/python-rapidocr nisavid/python-faster-whisper`
  shows 0.11.0-4, 3.9.2-1, and 1.2.1-1, and the sync-database SHA-256 values
  equal the candidate manifest.
- The Qdrant cutover route has merged:
  [feat(qdrant): add production cutover route and rebind accepted candidates](https://github.com/nisavid/arch-pkgs/pull/93).
- The Lemonade M4 receipts are cited, and Lemonade serves and has loaded the
  packaged zembed and zerank ids and `<chat-model>`.
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

- HAND-BACK: `HAND-BACK: open-webui P2 installed 0.11.0-4`
- Agent:
  - `pacman -Q open-webui python-rapidocr python-faster-whisper` shows the
    published versions;
  - `sha256sum /var/cache/pacman/pkg/{open-webui-0.11.0-4-x86_64,python-rapidocr-3.9.2-1-any,python-faster-whisper-1.2.1-1-any}.pkg.tar.zst`
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

Install this before the first start. The connection seed is exactly three
keys: `ENABLE_OLLAMA_API=false`, `OPENAI_API_BASE_URLS`, and an empty
`OPENAI_API_KEYS`. In Open WebUI 0.11 they are persistent-config seeds: they
apply on first start, and later edits need an admin re-save. The drop-in adds
a second environment file, which wins over the packaged one.

The drop-in also sets the two local Whisper settings the acceptance unit
carried: `WHISPER_MODEL` and `HF_HUB_OFFLINE=1`, so a Whisper load failure can
never fall back to the network. They are not part of the seed.

First check what the installed env already sets (a later package revision
makes the seed a default). An environment file overrides `Environment=`, so if
it sets `WHISPER_MODEL` or `HF_HUB_OFFLINE` to another value, stop and ask the
lead:

```bash
sudo grep -E '^(ENABLE_OLLAMA_API|OPENAI_API_BASE_URLS|OPENAI_API_KEYS|WHISPER_MODEL|HF_HUB_OFFLINE)=' /etc/open-webui/open-webui.env
```

Write only the seed keys it does not already set:

```bash
sudo install -m 0600 /dev/stdin /etc/open-webui/open-webui.connections.env <<'EOF'
ENABLE_OLLAMA_API=false
OPENAI_API_BASE_URLS=<provider-base-url>
OPENAI_API_KEYS=
EOF

sudo install -D -m 0644 /dev/stdin /etc/systemd/system/open-webui.service.d/20-connections.conf <<'EOF'
[Service]
EnvironmentFile=/etc/open-webui/open-webui.connections.env
Environment=WHISPER_MODEL=<whisper-model>
Environment=HF_HUB_OFFLINE=1
EOF
sudo systemctl daemon-reload
```

- Rollback (before P4 only):
  `sudo rm /etc/open-webui/open-webui.connections.env /etc/systemd/system/open-webui.service.d/20-connections.conf && sudo systemctl daemon-reload`

### P3.5 Session epoch

```bash
sudo /usr/lib/open-webui/open-webui-session-epoch-ledger initialize
```

The ledger is forward-only. It has no rollback and is never reset.

### P3.6 Whisper model

Build the Hugging Face cache layout from the flat snapshot the acceptance
trial verified. `teardown --keep-anchor` keeps it at
`<root>/inputs/faster-whisper-<whisper-model>/`. `<whisper-revision>` is the
pinned revision recorded in the acceptance evidence; `refs/main` holds it, as
the kit's own placement does.

```bash
m=/var/lib/open-webui/cache/whisper/models/models--Systran--faster-whisper-<whisper-model>
rev=<whisper-revision>
sudo install -d -o open-webui -g open-webui -m 0750 "$m" "$m/refs" "$m/snapshots" "$m/snapshots/$rev"
sudo install -o open-webui -g open-webui -m 0640 -t "$m/snapshots/$rev" \
  <root>/inputs/faster-whisper-<whisper-model>/*
printf '%s' "$rev" | sudo install -o open-webui -g open-webui -m 0640 /dev/stdin "$m/refs/main"
sudo sha256sum "$m/snapshots/$rev/model.bin"
unset m rev
```

The printed digest must equal the `model.bin` SHA-256 in the acceptance
evidence.

- Rollback (before P4 only):
  `sudo rm -r /var/lib/open-webui/cache/whisper/models/models--Systran--faster-whisper-<whisper-model>`

- HAND-BACK: `HAND-BACK: open-webui P3 credentials, valkey, epoch ready`
- Agent: `systemctl show open-webui.service -p DropInPaths` lists
  `20-connections.conf`, and the P3.2 Valkey checks pass.

## P4: closed-route commissioning

Caddy is not running, so nothing outside the host can reach the new socket.

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
       --socket /run/open-webui/open-webui.sock --chat-model <chat-model>
   ```

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

If the lead and owner approve a non-admin smoke account for the re-smoke, the
owner creates it in the admin UI after P5 and stores its credentials as the
acceptance runbook's re-smoke section shows.

- Rollback: `sudo systemctl disable --now open-webui.service`. The route never
  opened, and `:8080` is never restored.
- HAND-BACK: `HAND-BACK: open-webui P4 commissioned, route closed`
- Agent: `systemctl show open-webui.service -p ActiveState,NRestarts,Result`
  is active with no restarts; `DropInPaths` no longer lists
  `10-bootstrap.conf`.

## P5: open the route

### P5.0 Owner decision: the HTTPS origin

The host already serves `:443` on some addresses. Before this phase the owner
chooses `<household-origin>`, the bind address, and the TLS source: either
route through the existing `:443` terminator, whose own change is then a
separate owner step with its own rollback, or give Caddy a distinct HTTPS
port. `caddy validate` does not catch a bind conflict.

This step is a placeholder until that decision is recorded on the ticket.

### P5.1 Install the site block

```bash
grep -n 'import /etc/caddy/conf.d' /etc/caddy/Caddyfile
sudo install -D -m 0644 /dev/stdin /etc/caddy/conf.d/open-webui.caddy <<'EOF'
<household-origin> {
	bind <bind-address>
	tls <tls-source>
	reverse_proxy unix//run/open-webui/open-webui.sock
}
EOF
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl enable --now caddy.service
```

- Rollback:
  `sudo rm /etc/caddy/conf.d/open-webui.caddy && sudo systemctl disable --now caddy.service`
- HAND-BACK: `HAND-BACK: open-webui P5 route open`
- Agent: `systemctl is-active caddy.service` is active; HTTPS 200 from
  `https://<household-origin>/`; an authenticated WebSocket upgrade returns
  101; `ss -ltnH 'sport = :8080'` prints nothing, and no Open WebUI TCP
  listener exists.

## P6: production anchor

### P6.1 Create the anchor directory

```bash
sudo install -d -m 0700 /var/lib/arch-pkgs-anchors
```

### P6.2 Take the anchor

Close the route and quiesce writers, copy the state tuple, then reopen.
Valkey saves its RDB when it stops.

```bash
a=/var/lib/arch-pkgs-anchors/open-webui-0.11.0-4-$(date -u +%Y%m%dT%H%M%SZ)
sudo install -d -m 0700 "$a" "$a/credstore" "$a/archives" "$a/qdrant"
sudo systemctl stop caddy.service open-webui.service valkey.service
sudo cp -a /var/lib/open-webui/data "$a/open-webui-data"
sudo cp -a /var/lib/valkey/open-webui/dump.rdb "$a/"
sudo sh -c 'cp -a /etc/credstore.encrypted/open-webui.* "$1/credstore/"' sh "$a"
sudo /usr/lib/open-webui/open-webui-session-epoch-ledger current | sudo tee "$a/epoch-bound"
sudo cp -a /var/cache/pacman/pkg/{open-webui-0.11.0-4-x86_64,python-rapidocr-3.9.2-1-any,python-faster-whisper-1.2.1-1-any}.pkg.tar.zst "$a/archives/"
```

With Open WebUI stopped, take the five collection snapshots with the Qdrant
administrative key as the Qdrant runbook describes, and copy them into
`"$a/qdrant/"`. Then record the digests and reopen:

```bash
sudo sh -c 'cd "$1" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + >SHA256SUMS' sh "$a"
sudo systemctl start valkey.service open-webui.service caddy.service
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

- HAND-BACK: `HAND-BACK: open-webui verify PASSED on 0.11.0-4`

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

- **Before P5:** `sudo systemctl disable --now open-webui.service caddy.service`.
  The route stays closed.
- **After P5, to the anchor:**

  ```bash
  sudo rm /etc/caddy/conf.d/open-webui.caddy && sudo systemctl reload caddy.service
  sudo systemctl stop open-webui.service
  sudo /usr/lib/open-webui/open-webui-session-epoch-ledger reserve
  sudo sh -c 'cd "$1" && sha256sum -c SHA256SUMS' sh <anchor>
  sudo pacman -U <anchor>/archives/{open-webui-0.11.0-4-x86_64,python-rapidocr-3.9.2-1-any,python-faster-whisper-1.2.1-1-any}.pkg.tar.zst
  ```

  Then restore the tuple: stop Valkey and replace its `dump.rdb`, replace
  `/var/lib/open-webui/data`, the encrypted credential files, and recover the
  five Qdrant snapshots as the Qdrant runbook describes. Start Valkey and Open
  WebUI, check SQLite `quick_check`, the digests, the collection shapes, that
  a pre-anchor session is rejected, and that a fresh login works; then
  reinstall the site block and reload Caddy.

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
