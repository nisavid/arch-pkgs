# Open WebUI household production install

This is the owner handoff for
[Deploy the accepted Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/59).
It replaces the host's out-of-band `open-webui` 0.11.0-1 with the published
0.11.0-6 identity, served on the tailnet only: the package's
`open-webui-tailnet.service` sidecar runs Tailscale Serve and proxies straight
to the service's Unix socket. The former state is retained, never migrated.

Every privileged step belongs to the owner. Each phase lists its exact
commands, its rollback, the HAND-BACK phrase the owner replies with, and the
unprivileged checks the agent runs afterwards. There is no new privileged
script: the commands are here, and the only scripts involved are the packaged
helpers and the Qdrant cutover route from
[Deploy the accepted Qdrant service](https://github.com/nisavid/arch-pkgs/issues/58).

Placeholders: `<kit-checkout>` is a root-readable checkout of this repository
at the kit commit recorded in the acceptance evidence; `<root>` is the kept
acceptance root; `<name>` is the sidecar's tailnet node name and
`<tailnet>` the tailnet's DNS label, so `<household-origin>` is
`https://<name>.<tailnet>.ts.net`. None of these values is committed; the
concrete ones stay in the owner's session-local handoff variables.

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
  shows 0.11.0-6, 3.9.2-1, and 1.2.1-1, and the sync-database SHA-256 values
  equal the candidate manifest.
- The 0.11.0-6 candidate, which adds the tailnet sidecar, replaces 0.11.0-5
  as the candidate of record once it is built, merged, and tree-equal. Its
  archive is `open-webui-0.11.0-6-x86_64.pkg.tar.zst`, size
  **`<pending>`** bytes, SHA-256 **`<pending>`**; both are recorded when the
  candidate is built.
- `<kit-checkout>` carries the Qdrant cutover route,
  `tools/qdrant_production_cutover.zsh`, and its
  [runbook](qdrant-production-cutover.md), both on `main` since
  [feat(qdrant): add production cutover route and rebind accepted candidates](https://github.com/nisavid/arch-pkgs/pull/93)
  merged.
- The Lemonade M4 receipts are cited, and Lemonade serves and has loaded the
  packaged zembed and zerank ids and the owner-pinned chat model.
- The [P5.0](#p50-tailnet-prerequisites) prerequisites hold, and the owner
  has chosen `<name>`, because P3.4 writes `<household-origin>` before the
  first start.
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
`python-antlr4`. The tailnet route also needs `tailscale`, an optional
dependency of `open-webui`. Caddy is installed but is not in Open WebUI's
path; never remove the `caddy` package or change its install reason.

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

## P0.1: credential-mode preflight

Every `/etc/credstore.encrypted` secret in this runbook is encrypted in one
mode, and this preflight picks it. It encrypts and decrypts a probe as root
with the same mode the install will use. First the default mode:

```bash
sudo sh -c 'printf probe | systemd-creds encrypt --name=probe - - | systemd-creds decrypt --name=probe - -'; echo
```

It must print `probe`. If it fails (on a host where TPM2 unsealing fails, the
decrypt reports a TPM2 unseal error), try the host key:

```bash
sudo sh -c 'printf probe | systemd-creds encrypt --with-key=host --name=probe - - | systemd-creds decrypt --name=probe - -'; echo
```

Then set two variables in the owner's shell from the mode that printed
`probe`. Every `systemd-creds encrypt` line below uses `creds_key`, including
the admin credentials in P4, and P1 passes `creds_mode` to the Qdrant cutover
route; set both again in any new shell:

```bash
creds_key=() creds_mode=auto                # the default mode printed probe
creds_key=(--with-key=host) creds_mode=host # only the host-key mode printed probe
```

If both fail, stop: the owner repairs credential decryption before this
install continues.

Known limitation of the host-key mode: those credentials are not bound to the
TPM. They are sealed with `/var/lib/systemd/credential.secret`, and systemd
warns when that file is not on encrypted media; such credentials are only as
protected as the root filesystem.

P1 writes the Qdrant runtime credential through the Qdrant cutover route, and
Open WebUI decrypts it with the rest. The route's `--creds-key auto|host`
option forces one mode: its own preflight then probes only that mode, and
cutover encrypts the runtime credential in it. P1 passes `creds_mode`, so
every credential Open WebUI loads uses the mode chosen here.

- Rollback: none; the probe writes nothing.
- HAND-BACK: `HAND-BACK: open-webui P0.1 credential mode <auto|host>`
- Agent: none; the owner's output is the proof.

## P1: Qdrant cutover

Follow the [Qdrant production cutover runbook](qdrant-production-cutover.md)
for
[Deploy the accepted Qdrant service](https://github.com/nisavid/arch-pkgs/issues/58),
from `<kit-checkout>`, with the mode [P0.1](#p01-credential-mode-preflight)
chose:

```bash
sudo tools/qdrant_production_cutover.zsh preflight --creds-key "$creds_mode"
sudo tools/qdrant_production_cutover.zsh cutover --creds-key "$creds_mode"
sudo tools/qdrant_production_cutover.zsh cutover --apply --creds-key "$creds_mode"
sudo tools/qdrant_production_cutover.zsh verify
```

Preflight must print `credential mode: <creds_mode>`. The cutover creates the
five `open-webui-rag-v1` collections and delivers the runtime credential to
`/etc/credstore.encrypted/open-webui.qdrant-runtime-api-key`. The Qdrant
administrative key stays with the owner.

Before Open WebUI writes, prove rollback: run the dry-run `rollback` command
that verify's `HAND-BACK:` line prints, exactly as printed and without
`--apply`. It must end with `HAND-BACK: qdrant rollback dry run complete`.

- Rollback: the Qdrant runbook's `rollback --apply`.
- HAND-BACK: the script's own lines, first
  `HAND-BACK: qdrant verify PASSED on 1.19.0-1; …` and then
  `HAND-BACK: qdrant rollback dry run complete; …`.
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
- Leave `open-webui.service` and `open-webui-tailnet.service` disabled.

Rollback, if P2 is aborted: `sudo systemctl disable --now open-webui.service`,
and reinstall `python-rapidocr-onnxruntime` with `sudo pacman -U` only if its
archive is still in the package cache. The service stays closed; the former
package is not a rollback target.

- HAND-BACK: `HAND-BACK: open-webui P2 installed 0.11.0-6`
- Agent:
  - `pacman -Q open-webui python-rapidocr python-faster-whisper` shows the
    published versions;
  - `sha256sum /var/cache/pacman/pkg/{open-webui-0.11.0-6-x86_64,python-rapidocr-3.9.2-1-any,python-faster-whisper-1.2.1-1-any}.pkg.tar.zst`
    equals the promotion record;
  - `pacman -Q python-rapidocr-onnxruntime` fails;
  - `pacman -Qi caddy python-omegaconf python-antlr4 tailscale` succeeds;
  - `systemctl is-enabled open-webui.service open-webui-tailnet.service`
    shows both disabled;
  - `sha256sum /usr/lib/systemd/system/open-webui-tailnet.service` equals
    **`<pending>`**, the unit digest recorded by the 0.11.0-6 reference build.

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
    | sudo systemd-creds encrypt "${creds_key[@]}" --name="$n" - "/etc/credstore.encrypted/open-webui.$n"
done
```

`creds_key` comes from [P0.1](#p01-credential-mode-preflight).

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
  | sudo systemd-creds encrypt "${creds_key[@]}" --name=valkey-url - /etc/credstore.encrypted/open-webui.valkey-url
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
- `30-origin.conf` sets both `WEBUI_URL` and `CORS_ALLOW_ORIGIN` to the
  tailnet origin `https://<name>.<tailnet>.ts.net`. `WEBUI_URL` is a
  persistent-config seed: the first start copies it into the database, and
  the stored value wins after that, so it must be in place before the first
  start. The lasting way to change it later is Admin Panel > Settings >
  General > WebUI URL. `ENABLE_PERSISTENT_CONFIG=false` lets the environment
  win only while it stays set, and for every persistent setting.
  `CORS_ALLOW_ORIGIN` is read at every start. Changing the origin later signs
  every user out. The package README's
  [Tailnet Route](../../packages/open-webui/README.md#tailnet-route) step 3
  writes the same two lines to `open-webui.env`; this runbook uses the
  drop-in instead, never both.

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
Environment=WEBUI_URL=https://<name>.<tailnet>.ts.net
Environment=CORS_ALLOW_ORIGIN=https://<name>.<tailnet>.ts.net
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

The tailnet route is not published yet, so nothing outside the host can
reach the socket.

1. The owner types the four admin values; none pass through an agent:

   ```bash
   for n in admin-email admin-name admin-bootstrap-password admin-final-password; do
     systemd-ask-password -n "$n" \
       | sudo systemd-creds encrypt "${creds_key[@]}" --name="$n" - "/etc/credstore.encrypted/open-webui.$n"
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

## P5: open the tailnet route

The route is tailnet-only. The `open-webui-tailnet.service` sidecar that
0.11.0-6 ships runs a second, untagged `tailscaled` owned by the owner's
tailnet account, in userspace-networking mode, and its Tailscale Serve proxies
HTTPS on 443 straight to `/run/open-webui/open-webui.sock`. The package
README's [Tailnet Route](../../packages/open-webui/README.md#tailnet-route)
section, which lands with 0.11.0-6, is the reference for the unit, the
loopback deny, and each step's reasons; this section keeps only the operator
sequence and its hand-backs. Caddy is not in Open WebUI's path.

Every `tailscale --socket=/run/open-webui-tailnet/tailscaled.sock ...` command
runs through `sudo`: the LocalAPI socket's directory admits only root and the
daemon's own user.

Tailscaled log uploads are off by default (the unit sets
`TS_NO_LOGS_NO_SUPPORT=true`). The owner decided to keep them off; the
README's log-upload paragraph describes the opt-in drop-in if that changes.

A dedicated Tailscale Service was rejected: Services require a tagged host,
which would strip the host's user identity.

### P5.0 Tailnet prerequisites

- Each household member who uses Open WebUI joins the tailnet; the owner
  invites them.
- The tailnet policy stays the default allow-all.
- MagicDNS and HTTPS certificates are enabled for the tailnet.
- The owner has chosen the node name `<name>` before P3, because P3.4 seeds
  `WEBUI_URL` from it. Record the choice on
  [Deploy the accepted Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/59)
  generically; the concrete name is never committed.

### P5.1 Start the sidecar and log it in

README step 1:

```bash
sudo systemctl enable --now open-webui-tailnet.service
sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock up --hostname=<name>
sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock status --peers=false
```

`up` prints a login URL; the owner signs in interactively as themselves, so
the node stays untagged and user-owned. `status` shows the node's name; if
Tailscale added a suffix, the P3.4 origin no longer matches, so stop and
settle the origin with the lead before P5.3. Then, in the Tailscale admin
console, disable key expiry for the `<name>` node.

### P5.2 Loopback check (owner-run proof)

README step 2, before any serve configuration exists. In
userspace-networking mode `tailscaled` forwards a tailnet connection on a port
it does not serve to that port on the host's `127.0.0.1`; the unit's
`IPAddressDeny=127.0.0.1 ::1` must block that on this host. From another
tailnet device with `nc`, probe the Qdrant port:

```bash
nc -vz -w 5 <name>.<tailnet>.ts.net 6333
```

It must time out, and about two minutes later
`sudo journalctl -u open-webui-tailnet.service` must show the forward to
`127.0.0.1:6333` failing. A connection or a quick refusal means the deny is
not in effect: stop and run the P5.3 rollback. A timeout with no journal line
means the tailnet policy blocked the probe; retry from a device it admits.

- HAND-BACK: `HAND-BACK: open-webui P5.2 loopback deny proven`

### P5.3 Publish the route

README step 4. Run the `serve` command exactly as written, as root through
`sudo`: since Tailscale 1.98.9
([TS-2026-005](https://tailscale.com/security-bulletins#ts-2026-005)),
`tailscaled` accepts a serve configuration with a Unix-socket target only from
a local admin, and inside the unit's sandbox root is the only admin.

```bash
sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock serve --bg --https=443 unix:/run/open-webui/open-webui.sock
sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock serve status
```

`serve status` must show `https://<name>.<tailnet>.ts.net` proxying to
`unix:/run/open-webui/open-webui.sock`.

- Rollback, in reverse order, always with `sudo` and `--socket` (a bare
  `tailscale serve --https=443 off` reaches the system `tailscaled` instead):

  ```bash
  sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock serve --https=443 off
  sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock logout
  sudo systemctl disable --now open-webui-tailnet.service
  ```

- HAND-BACK: `HAND-BACK: open-webui P5 tailnet route open`
- Agent, unprivileged, from another tailnet device:
  - `curl -sS -o /dev/null -w '%{http_code}\n' https://<name>.<tailnet>.ts.net/`
    returns 200 on the portless HTTPS origin, with default certificate
    verification;
  - `curl -sS https://<name>.<tailnet>.ts.net/api/config | jq -e '.features.enable_signup == false'`
    succeeds;
  - an authenticated WebSocket upgrade returns 101.
- Agent, on the host:
  - `ss -ltnH 'sport = :8080'` prints nothing, and no Open WebUI TCP listener
    exists;
  - the `serve status` output the owner ran names only the Open WebUI socket
    as the target, so Caddy is not in the path. The agent reads the owner's
    output rather than running it.

### P5.4 The smoke account

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
a=/var/lib/arch-pkgs-anchors/open-webui-0.11.0-6-$(date -u +%Y%m%dT%H%M%SZ)
sudo install -d -m 0700 "$a" "$a/credstore" "$a/archives" "$a/qdrant"
sudo systemctl stop open-webui.service valkey.service
sudo cp -a /var/lib/open-webui/data "$a/open-webui-data"
sudo cp -a /var/lib/valkey/open-webui/dump.rdb "$a/"
sudo sh -c 'cp -a /etc/credstore.encrypted/open-webui.* "$1/credstore/"' sh "$a"
sudo /usr/lib/open-webui/open-webui-session-epoch-ledger current | sudo tee "$a/epoch-bound"
sudo cp -a /var/cache/pacman/pkg/{open-webui-0.11.0-6-x86_64,python-rapidocr-3.9.2-1-any,python-faster-whisper-1.2.1-1-any}.pkg.tar.zst "$a/archives/"
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

- HAND-BACK: `HAND-BACK: open-webui verify PASSED on 0.11.0-6`

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
  # first close the route:
  sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock serve --https=443 off
  sudo systemctl stop open-webui.service
  sudo /usr/lib/open-webui/open-webui-session-epoch-ledger reserve
  sudo sh -c 'cd "$1" && sha256sum -c SHA256SUMS' sh <anchor>
  sudo pacman -U <anchor>/archives/{open-webui-0.11.0-6-x86_64,python-rapidocr-3.9.2-1-any,python-faster-whisper-1.2.1-1-any}.pkg.tar.zst
  ```

  Then restore the tuple: stop Valkey and replace its `dump.rdb`, replace
  `/var/lib/open-webui/data`, the encrypted credential files, and recover the
  five Qdrant snapshots as the Qdrant runbook describes. Start Valkey and Open
  WebUI, check SQLite `quick_check`, the digests, the collection shapes, that
  a pre-anchor session is rejected, and that a fresh login works; then
  republish the route with the P5.3 `serve` command.

  - HAND-BACK: `HAND-BACK: open-webui rollback PASSED to anchor <anchor-id>`

- **To withdraw the tailnet route only:** the P5.3 rollback. Caddy is not
  involved; never remove the `caddy` package or change its install reason.
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
