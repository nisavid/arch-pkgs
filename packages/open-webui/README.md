# open-webui

Disposable Arch package candidate for Open WebUI 0.11.4 and the fresh household
native-RAG boundary.

This candidate is not approved for production activation or publication. A
successful source verification or build is only a package gate;
[Acceptance-deploy the Open WebUI household candidate set](https://github.com/nisavid/arch-pkgs/issues/89)
still requires the one integrated trial set against the exact composed runtime
and the live-validated Lemonade provider. The dated measurement boundary
remains in
[`docs/maintainers/open-webui-household-envelope.md`](../../docs/maintainers/open-webui-household-envelope.md).

## Packaged Boundary

- Open WebUI serves only on `/run/open-webui/open-webui.sock`. Members of the
  dedicated `open-webui-proxy` group can reach the socket: the tailnet sidecar
  (`open-webui-tailnet.service`) for the tailnet-only production route, and
  Caddy for a possible later route through a local TLS terminator. Neither
  joins the Open WebUI data group.
- The package builds the exact 0.11.4 source archive, seeds and verifies the 63
  release-authored Pyodide files from the exact release wheel, runs `npm ci`
  from a verified npm cache, and installs a hash-locked private server
  closure. Both closure archives are immutable
  `makepkg` sources and both installers run in offline mode.
- The ML and native scientific stack remains pacman-owned. The package verifies
  that none of the 21 externalized provider distributions or their top-level
  import roots appears in the installed private server closure under
  `/opt/open-webui/lib/python3.14/site-packages`. The bundled browser-side
  Pyodide wheels are a separate WebAssembly runtime, not server providers or a
  security boundary.
- Native RAG uses the five Qdrant collections under
  `open-webui-rag-v1`, zembed query/document prefixes, and the external zerank
  reranker (Lemonade model `zerank-2-GGUF`, the built-in entry that carries
  the ZeroEntropy selected-logit adapter). The packaged defaults send embedding and reranking requests to
  Lemonade at `http://127.0.0.1:13305/api/v1` and enable hybrid search,
  because the reranker gate rejects non-hybrid document retrieval. Reranker
  qualification is mandatory for document RAG; ordinary chat remains
  available when that provider is unhealthy.
- The packaged chat connection seed disables the Ollama API and names only
  Lemonade at `http://127.0.0.1:13305/api/v1`, so a fresh instance has no
  default Ollama or `api.openai.com` peer. Open WebUI copies these values, and
  the other persistent settings such as `RAG_RERANKING_MODEL`, into its
  database the first time an instance starts. After that, the stored values
  win over `open-webui.env`, so a later edit to the file or a package update
  does not change an existing instance. Change them in the admin UI, or start
  from a fresh data directory.
- Open WebUI's Lemonade connection uses no credential in this refresh (owner
  decision). The package still keeps the embedding and reranking API-key
  settings out of persistent configuration and out of the document settings
  form.
- Qualification runs at service start and when an administrator saves the
  document settings. After any runtime reranker fault, document RAG stays
  closed (the authenticated `/api/v1/retrieval/health` probe returns 503)
  until one of those requalifies it; once the provider is healthy again,
  restart `open-webui.service`.
- Before service start, an operator with Qdrant administrative authority must
  precreate the exact 2560-dimensional cosine collections
  `open-webui-rag-v1_memories`, `open-webui-rag-v1_knowledge`,
  `open-webui-rag-v1_files`, `open-webui-rag-v1_web-search`, and
  `open-webui-rag-v1_hash-based`, together with their required payload indexes.
  Open WebUI receives only the generation-scoped `prw` credential and cannot
  create or reset collections.
- Application state and writable static files live under `/var/lib/open-webui`.
  The root-only forward session epoch lives separately under
  `/var/lib/open-webui-session-epoch` and is outside application snapshots and
  rollback state.
- Signup, API keys, server-side package installation, profile-image URL
  forwarding, code execution/interpreter, automations, calendar, evaluation
  arena, update checks, and non-loopback IP egress are disabled by the packaged
  baseline.

## Mandatory Credentials

The normal service loads these identities automatically on every start. It
fails before importing the application when a required credential is absent or
empty.

| Credential | Authority |
| --- | --- |
| `webui-secret-key` | stable Open WebUI signing key |
| `oauth-client-info-encryption-key` | distinct stable OAuth client-info key |
| `oauth-session-token-encryption-key` | distinct stable OAuth session key |
| `valkey-url` | dedicated Valkey ACL URL |
| `qdrant-runtime-api-key` | collection-scoped runtime `prw` JWT only |
| `session-epoch` | read-only copy of the external root-owned epoch ledger |

Provision the five encrypted service credentials once under the exact paths
declared by `open-webui.service`. The service receives no Qdrant administrative
credential. Manual delivery is not part of ordinary startup; operator handling
is limited to initial provisioning, deliberate rotation, or restore.

## zembed Prefixes

zembed expects each input wrapped as a short chat transcript whose system turn
names the input type. The packaged defaults carry the opening part of that
wrapper, with real newlines, as Open WebUI text prefixes:

- `RAG_EMBEDDING_QUERY_PREFIX`:
  `<|im_start|>system\nquery<|im_end|>\n<|im_start|>user\n`
- `RAG_EMBEDDING_CONTENT_PREFIX`:
  `<|im_start|>system\ndocument<|im_end|>\n<|im_start|>user\n`

Each `\n` stands for a real newline. In `open-webui.env` each value is a
double-quoted string that spans lines, which systemd reads with its newlines
intact. `RAG_EMBEDDING_PREFIX_FIELD_NAME` stays unset, so Open WebUI sends no
`input_type` request field.

Open WebUI 0.11.4 joins a prefix directly to the text. Settings can only
prefix, so the wrapper's closing `<|im_end|>` and newline are not sent. The
zembed semantic canary in
[Acceptance-deploy the Open WebUI household candidate set](https://github.com/nisavid/arch-pkgs/issues/89)
decides whether this is enough. If it fails, the result is escalated for a
decision; neither a formatting adapter nor threshold tuning replaces it.

## Session Epoch

Initialize epoch zero once before the first service start:

```bash
sudo /usr/lib/open-webui/open-webui-session-epoch-ledger initialize
```

Ordinary starts only read the current value. Before any whole-runtime restore,
reserve the next value before touching Open WebUI, SQLite, Valkey, Qdrant, or
credential state:

```bash
sudo /usr/lib/open-webui/open-webui-session-epoch-ledger reserve
```

The restore receipt must bind the reserved epoch. A missing, malformed,
non-forward, or reconstructed-without-complete-evidence ledger is a deployment
failure; do not silently reset it.

## Closed-Route Administrator Commissioning

The first start happens while no route is published: no tailnet serve
configuration and no Caddy route. Complete [Tailnet Route](#tailnet-route)
steps 1 to 3 before it. A temporary systemd drop-in
supplies `admin-email`, `admin-name`, and
`admin-bootstrap-password` credentials to the launcher. Run
`/usr/lib/open-webui/open-webui-commission-admin` once through a transient
systemd unit that supplies `admin-email`, `admin-name`,
`admin-bootstrap-password`, and `admin-final-password` as protected
credentials—not arguments or environment values—so the complete commissioned
identity is verified.

The helper signs in over the Unix socket and verifies exactly one intended
administrator before it changes anything. It then changes the password through
the exact 0.11 API, proves the bootstrap password no longer works, proves the
final password works, verifies the sole administrator again, and verifies
signup is false. Since 0.11.1 a password change revokes every session issued
in the same whole second, so the helper waits for the next second before it
signs in with the final password. After it succeeds, consume and remove every bootstrap input
and temporary drop-in, restart `open-webui.service` normally, repeat the
postconditions, and only then publish the tailnet route
([Tailnet Route](#tailnet-route) step 4).

## Tailnet Route

The production route is tailnet-only. `open-webui-tailnet.service` runs a
second `tailscaled`, separate from any system `tailscaled.service`: an
untagged node owned by the owner's tailnet account, in userspace-networking
mode (no TUN, no root), with its own state under `/var/lib/open-webui-tailnet`
and its own LocalAPI socket at `/run/open-webui-tailnet/tailscaled.sock`. It
runs as a dynamic user in the `open-webui-proxy` group, which is how it
reaches the Open WebUI socket. The package installs the unit disabled and
ships no node name. The login, node name, and serve configuration are runtime
state in that state directory, so a later route to another Unix-socket
target under `/run` (not `/run/user`) that the `open-webui-proxy` group can
reach, for example a local TLS terminator, needs no unit change. A target on
`127.0.0.1` or `::1` does not work. The route needs the optional `tailscale`
package.

The unit denies the daemon the host addresses `127.0.0.1` and `::1`, so
tailnet peers reach only what the node itself serves.
[Denying `127.0.0.1` and `::1`](#denying-127001-and-1) explains why and what
it rules out, a DNS caveat, how to clear the stall a port scan can cause, the
tailnet policy the route keeps and a stronger one it does not apply now, the
check to repeat after each `tailscale` upgrade, and the options for a later
custom domain. Do not advertise routes or an exit node from this node; those
would forward traffic to the host's network, which the deny does not cover.

These are production cutover steps. Run them only under the accepted
deployment task, never directly from this package directory (see
[Package Verification](#package-verification)). The commands use the
placeholders `<name>` for the node name and `<tailnet>` for the tailnet's DNS
label; neither belongs in this repository. The LocalAPI socket's directory
admits only root and the daemon's own user, so every `tailscale --socket=...`
command runs under `sudo`.

1. Start the node and log it in once, interactively:

   ```sh
   sudo systemctl enable open-webui-tailnet.service
   sudo systemctl start open-webui-tailnet.service
   sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock up --hostname=<name>
   ```

   Then confirm the node's name with
   `sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock status --peers=false`.
   If `<name>` was taken, Tailscale adds a suffix; use the name it shows
   as `<name>` from here on.
2. In the Tailscale admin console, disable key expiry for the new node, and
   make sure MagicDNS and HTTPS certificates are enabled for the tailnet;
   `serve --https=443` needs them to obtain the node's certificate. Then
   check the `127.0.0.1` deny from another tailnet computer that has `nc`,
   before any tailnet policy narrows this node to `tcp:443`. Use the Qdrant
   port in `open-webui.env` (6333 by default):

   ```sh
   nc -vz -w 5 <name>.<tailnet>.ts.net 6333
   ```

   It must time out. The daemon logs the failed forward about 130 seconds
   after the probe, so wait at least 140 seconds but no more than five
   minutes; then
   `sudo journalctl -u open-webui-tailnet.service --since=-5min` must show
   the forward to `127.0.0.1:6333` failing (`--since=-5min` ignores lines
   logged more than five minutes before the query, such as those from an
   earlier check). Go on to step 3 only after both; otherwise stop and roll
   back. A connection or a quick refusal means the deny is not in effect.
   One result allows a single retry: a timeout with no forward line usually
   means the tailnet policy blocked the probe (the journal may show a
   `Drop:` line for it instead). Once
   `sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock status --peers=false`
   shows the node online, retry once from a device the policy admits.
3. Before the first Open WebUI start, set the canonical origin in
   `/etc/open-webui/open-webui.env`:

   ```text
   WEBUI_URL=https://<name>.<tailnet>.ts.net
   CORS_ALLOW_ORIGIN=https://<name>.<tailnet>.ts.net
   ```

   Settle the origin now. `WEBUI_URL` is persistent config: the first start
   copies it into Open WebUI's database, and the stored value wins after
   that, so later edits to this file have no effect. Change it later under
   Admin Panel > Settings > General > WebUI URL. Setting
   `ENABLE_PERSISTENT_CONFIG=false` also lets the environment win, but for
   every persistent setting and only while it stays set.
   `CORS_ALLOW_ORIGIN` is read at every start. A later origin change signs
   every user out and strands their saved passwords, bookmarks, and
   installed web apps, which browsers tie to the old origin.
4. Only after
   [closed-route commissioning](#closed-route-administrator-commissioning)
   succeeds, publish the route:

   ```sh
   sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock serve --bg --https=443 unix:/run/open-webui/open-webui.sock
   ```

   Run it exactly as written, as root through `sudo`; do not move it to an
   unprivileged operator account. Since Tailscale 1.98.9
   ([TS-2026-005](https://tailscale.com/security-bulletins#ts-2026-005)),
   `tailscaled` accepts a Unix-socket serve target only from a local admin:
   root, or a user who passes the daemon's `sudo --list tailscale` check
   (the configured operator, if one is set). That check cannot pass inside
   this unit's sandbox, so root is the only admin here.

Verify with
`sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock serve status`,
then open `https://<name>.<tailnet>.ts.net/` from another tailnet device and
sign in.

Log uploads are off by default. Upstream `tailscaled` uploads its daemon logs
to Tailscale's log service; the unit sets `TS_NO_LOGS_NO_SUPPORT=true`, so the
sidecar keeps its logs local. Tailscale technical support needs those uploads,
and a tailnet with network flow logs enabled takes a node without them offline
("tailnet requires logging to be enabled"). To opt in, add a drop-in with
`sudo systemctl edit open-webui-tailnet.service`:

```ini
[Service]
UnsetEnvironment=TS_NO_LOGS_NO_SUPPORT
```

then run `sudo systemctl restart open-webui-tailnet.service`. If flow logs
had already taken the node offline, also run
`sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock up` to bring
it back. To undo the opt-in, remove the drop-in with
`sudo systemctl revert open-webui-tailnet.service` and restart the service.

Roll back in reverse order. After step 4, `tailscale serve` suggests
`tailscale serve --https=443 off`; run it only in the form below, with `sudo`
and `--socket`, or it reaches the system `tailscaled` instead:

```sh
sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock serve --https=443 off
sudo tailscale --socket=/run/open-webui-tailnet/tailscaled.sock logout
sudo systemctl disable open-webui-tailnet.service
sudo systemctl stop open-webui-tailnet.service
```

### Denying `127.0.0.1` and `::1`

In userspace-networking mode, `tailscaled` forwards tailnet TCP and UDP
traffic on any port it does not serve to that port on the host's `127.0.0.1`,
whether the peer used the node's IPv4 or IPv6 tailnet address. That would open
every service that listens on the host's `127.0.0.1`, such as Valkey, Qdrant,
and Lemonade, to the tailnet. Tailscale 1.102.2 has no setting that turns the
forward off, and `--shields-up` would also block the serve route. The unit
therefore sets `IPAddressDeny=127.0.0.1 ::1`. The forward never dials `::1`,
so that entry only guards against a future change. Keep the deny unchanged:

- `localhost` (`127.0.0.0/8` and `::1`) and `RestrictNetworkInterfaces=~lo`
  would also block the systemd-resolved stub at `127.0.0.53`, which the
  daemon's system-resolver lookups use on a host that resolves through it.
- `IPAddressAllow=` cannot make a narrow exception. It has no port scope, and
  an allow overrides the deny, so allowing `127.0.0.1` would expose every
  service on `127.0.0.1` again.

The deny does not filter Unix sockets, so the LocalAPI and the Unix-socket
serve target keep working. If these features are enabled on this node later,
the deny breaks each one that uses `127.0.0.1`, `::1`, or `localhost`:

- a serve or Funnel target;
- a `--debug` or metrics listener;
- a SOCKS5 or HTTP proxy listener (`--socks5-server`,
  `--outbound-http-proxy-listen`);
- an `HTTP_PROXY` or `HTTPS_PROXY`;
- a control server given with `up --login-server`.

Taildrive sharing would break whatever its settings, because its file server
always listens on `127.0.0.1`.

On a host whose `/etc/resolv.conf` points at `127.0.0.1` or `::1` (a local
dnsmasq or unbound, for example), the deny also blocks the daemon's
system-resolver lookups. The control client has its own DNS fallback, but no
fallback was found for certificate requests, so the node's HTTPS certificate
may fail to issue on such a host. That is untested.

The deny drops a blocked TCP forward rather than refusing it. The daemon waits
out the host's TCP SYN timeout, about two minutes, holding one of its
forwarding slots, and then logs the failure. One source address can hold at
most two thirds of the slots, so a port scan from one address mostly stalls
that peer itself. Stalling the serve route for every peer takes scans from two
or more addresses, and a peer with both an IPv4 and an IPv6 tailnet address
already has two. If the serve route stops answering after such a scan,
restart `open-webui-tailnet.service`; that clears the slots.

The tailnet keeps its default allow-all policy; the owner chose not to narrow
it for this node. The deny is therefore the control, and the stall above is an
accepted risk that a restart clears. A tailnet policy that admits peers to
this node only on `tcp:443` would be the stronger control, and it remains an
option for later. It drops all other traffic before `tailscaled` forwards it,
so that traffic neither reaches the deny nor holds a slot. If the policy is
ever narrowed, do it only after step 2's check has passed. Tailscale policy
rules only grant access, so a new `tcp:443` rule changes nothing by itself:
the default allow-all rule, and every other rule that covers this node, must
stop covering it. Because a rule cannot exclude one node, narrowing the
allow-all rule changes access across the tailnet; grant other devices the
access they had through it again.

The forwarding code ships in the `tailscale` package, and an upgrade does not
restart this unit. After each `tailscale` upgrade, restart
`open-webui-tailnet.service` so that the new daemon runs (the serve route drops
briefly), then repeat step 2's check. Under a narrowed policy, step 2's `nc`
needs a temporary rule that admits one device to this node on the Qdrant port;
remove the rule after the check. Plain `nc` on the host is no exception: it
can reach the node only through a system `tailscaled` on the host, as another
tailnet device, and the node filters its traffic like any peer's. The
`tailscale` 1.102.2 source suggests that a dial through the node's own socket
(`tailscale --socket=/run/open-webui-tailnet/tailscaled.sock nc`) to the
node's own tailnet address loops back inside the daemon without passing the
policy. That is untested, so do not use it in place of the temporary rule.

If the check fails after an upgrade, do not roll back the route; run
`sudo systemctl disable --now open-webui-tailnet.service` instead, and keep
the sidecar stopped except to repeat the check. Once the check passes, run
`sudo systemctl enable open-webui-tailnet.service`.

A later custom domain is an open choice between two variants. Both use
`serve --tcp=443`, which cannot share port 443 with the current
`serve --https=443` route, so either one replaces that route after it is
turned off:

- TLS passthrough to a local terminator on a Unix socket:
  `serve --bg --tcp=443 unix:/run/<dir>/<sock>`, run as root like any `unix:`
  target. It needs no unit change, but it cannot carry the PROXY protocol, so
  the terminator does not see the client's address.
- A terminator on `127.0.0.2`, an address outside the deny:
  `serve --bg --tcp=443 --proxy-protocol=2 tcp://127.0.0.2:<port>`. The PROXY
  header carries the client's address, but this variant is fragile: it
  breaks if the deny is ever widened, and the terminator must trust PROXY
  headers from `127.0.0.1`, which any local process can forge. It is
  untested.

## Qdrant Scroll Paging

`0008-page-qdrant-scroll.patch` makes `query()` and `get()` in both Open WebUI
Qdrant clients follow Qdrant's `next_page_offset`, asking for at most 1,000
points per request.

- **Stop conditions:** paging stops when Qdrant returns no next offset or a
  positive caller `limit` is reached, and the last request asks only for the
  remaining count. As guards, it also stops on an empty page or on the offset
  it was just sent, logs a warning naming the collection, the reason and the
  number of points read, and keeps the points already read. A caller `limit` of
  0 or less makes `query()` return an empty result after the existing
  collection check, without a scroll request (upstream sent the limit to
  Qdrant, which rejects `limit=0`); a missing collection still returns `None`.
- **Why:** upstream reads with a single scroll whose limit is
  `NO_LIMIT = 999999999`, a "fetch everything" stand-in added in
  [open-webui#6050](https://github.com/open-webui/open-webui/pull/6050) (2024).
  The packaged Qdrant enables strict mode with `max_query_limit: 1000` and
  rejects that request with HTTP 400. Uploads fail with that 400 during file
  processing. From reading the code, the failing call is the hash-dedup check
  once the shared collection exists. From reading the code (not reproduced):
  hybrid search's full-collection prefetch hits the same 400, the error is
  caught and logged, and the chat gets zero sources with no error.
- **Concurrent writes:** a paged read is not a point-in-time snapshot. Points
  written during the read may or may not appear; every point present for the
  whole read is returned exactly once. The prior single scroll was one atomic
  read per shard.
- **Page-size coupling:** `SCROLL_PAGE_SIZE` must stay at or below the
  packaged Qdrant `max_query_limit` in
  [`../qdrant/qdrant.config.yaml`](../qdrant/qdrant.config.yaml). Lowering
  that limit requires lowering the page size in the same change.
- **Out of scope:** `search()` top-k is unchanged. In the non-multitenancy
  client, `search(limit=None)` still maps to `NO_LIMIT`; the household runs in
  multitenancy mode and does not use that path.
- **Drop condition:** drop 0008 only once an upstream Open WebUI release
  pages Qdrant scroll reads with requests at or below the packaged Qdrant
  `max_query_limit` (1000), and only after checking a strict-mode read of more
  than 1,000 points against that release.

## Maintenance Baseline

- `authoritative_reference`: same-lane AUR `open-webui` recipe at commit
  `713042bd9585b692ce0ecd02e5e9482d4daee6c2` (0.11.3-1); no 0.11.4 recipe
  exists in Arch, CachyOS, or the AUR
- `advisory_references`: upstream `open-webui/open-webui` 0.11.4 PyPI source
  archive and build metadata at tag commit
  `8bd8b4fac5e059578ac0c74b3c18d11139f88b7d`, source SHA-256
  `1f1a31668a0dee733953c29d6183d78dd78984e696aa8eb0f2083f5796497be0`;
  the AUR 0.11.0-1 recipe at `6a65fb1cc4583d1ab9a1215a9cdf74054b36655b`,
  which differs from 0.11.3-1 only in its version strings;
  and repository issues
  [#63](https://github.com/nisavid/arch-pkgs/issues/63),
  [#66](https://github.com/nisavid/arch-pkgs/issues/66), and
  [#67](https://github.com/nisavid/arch-pkgs/issues/67)
- `divergence_notes`:
  - Support Arch Python 3.14 while leaving the exact upstream Pydantic and
    Psycopg requirements unchanged.
  - Externalize the accepted system ML/native providers and package the
    non-system application closure privately with exact hashes.
  - Freeze the frontend build, Unix-socket-only service, external-reranker
    failure boundary, automatic credential delivery, and forward-only session
    epoch as package-owned source and service assets.
  - Ship a disabled, unprivileged userspace `tailscaled` unit for the
    tailnet route, with the host's `127.0.0.1` and `::1` denied to it and log
    uploads off unless the operator opts in; its login and serve
    configuration stay runtime state.
  - Page Qdrant scroll reads under the packaged strict-mode query limit
    ([Qdrant Scroll Paging](#qdrant-scroll-paging)).
- `update_notes`:
  - Recompute the complete private closure from the immutable release lock and
    selected optional runtime backends; a digest without the full lock is not a
    package input.
  - Regenerate `.SRCINFO`, verify every immutable source, apply every patch with
    zero ambiguity, build in a clean environment, inspect the entire payload,
    and pass the provider-boundary verifier.
  - Keep the package deferred and excluded from publication until the complete
    G0-G4 Open WebUI contract passes against the exact package/provider tuple.

## Package Verification

### Private Python closure

`open-webui-private-requirements.lock` is generated from the exact 0.11.4
source archive, whose upstream `uv.lock` is SHA-256
`f0c49cfa1936887c3447cb4c33cbbfdd2064aa0937140ec1c0520523efae5392`.
The package-local constraints select the 200 audited release versions,
including the `qdrant-client==1.18.0` optional backend and its
`portalocker==3.2.0` dependency. The separate provider list removes the 21
pacman-owned distributions. Resolution is fixed to CPython 3.14 on
`x86_64-unknown-linux-gnu`, uv 0.12.5, and the recorded index cutoff,
`2026-09-21T19:31:44Z`: the first whole second after PyPI recorded the 0.11.4
source archive upload. The lock therefore admits only index files that
existed when upstream published the release.

Regenerate and verify the lock from an exact downloaded source archive with:

```bash
./generate-open-webui-private-lock.zsh ./open_webui-0.11.4.tar.gz
```

The generator verifies the source and upstream-lock digests, emits hashes for
every selected distribution, and runs the package-local structural verifier
before replacing the lock. Update the constraint/provider manifests and the
bound constants deliberately when changing the release or provider boundary.

### Offline dependency closures

The recipe binds two versioned release assets as `noextract` sources:

- `open-webui-npm-offline-closure-0.11.4.tar.zst` contains the 1,231 unique
  registry tarballs required by the exact release lock. The tracked manifest
  binds all 1,273 lock records to their SHA-512 integrity values and archive
  members. `prepare()` verifies the archive and seeds an isolated npm cache;
  the frontend build then runs `npm ci --offline`.
- `open-webui-python-offline-closure-0.11.4-cp314-x86_64.tar.zst` contains the
  200 wheels selected for CPython 3.14 on x86_64 Linux. Its embedded manifest
  binds every file to the private requirements lock. `prepare()` verifies safe
  members and exact identities before extraction; installation uses
  `uv --offline --no-index --require-hashes` against only that wheelhouse.

The closure helpers are deterministic and reject extra, missing, unsafe, or
digest-mismatched members. Regenerate candidate archives in disposable output
directories, compare two independent outputs byte-for-byte, and publish only
the reviewed bytes at the recipe's versioned build-input release:

```bash
python npm-offline-closure.py materialize \
  --lock open_webui-0.11.4/package-lock.json \
  --manifest npm-offline-closure-manifest.json \
  --archive open-webui-npm-offline-closure-0.11.4.tar.zst \
  --cache npm-download-cache

python python-offline-closure.py materialize \
  --lock open-webui-private-requirements.lock \
  --output python-closure
python python-offline-closure.py archive \
  --lock open-webui-private-requirements.lock \
  --manifest python-closure/manifest.json \
  --wheelhouse python-closure/wheelhouse \
  --output open-webui-python-offline-closure-0.11.4-cp314-x86_64.tar.zst
```

The 0.11.4 archives were regenerated this way twice, in independent output
directories with separate download caches, and both runs matched byte for
byte. The recipe fetches them from its `open-webui-0.11.4-offline-closures-v1`
build-input release. Until that release is published, `makepkg --verifysource`
needs local copies of the exact archive bytes in the package directory.

For 0.11.0, these inputs removed the dependency-network blocker. The
subsequent no-egress 0.11.0 pkgrel-3 build and payload-inspection gate passed
and is recorded in
[`docs/maintainers/open-webui-offline-package-build-2026-08-19.md`](../../docs/maintainers/open-webui-offline-package-build-2026-08-19.md).
Reproduce the compact, whole-archive inspection receipt from a retained package
with:

```bash
python inspect-open-webui-package.py \
  open-webui-0.11.0-3-x86_64.pkg.tar.zst \
  -o open-webui-0.11.0-3-package-inspection.json
cmp open-webui-0.11.0-3-package-inspection.json \
  ../../docs/maintainers/evidence/open-webui-offline-package-inspection-2026-08-19.json
```

The receipt binds every archive member by path, type, mode, ownership, size,
content digest, and link target while keeping the full 28,087-member listing
out of the repository. The inspector rejects unsafe paths, ownership or modes,
links, duplicate members, installer metadata, externalized server providers,
and package-build residue.
Python is used for this helper because the contract depends on structured tar
metadata and canonical JSON; it never extracts or executes package payloads.

The published v1 receipt binds the inspector's exact SHA-256. Keep those
verifier bytes immutable; a changed receipt contract must use a new schema and
versioned helper rather than rewriting this historical checkpoint.

That checkpoint does not make the package accepted: the
integrated provider, restore, and rollback evidence of the one integrated trial
set must still pass under
[Acceptance-deploy the Open WebUI household candidate set](https://github.com/nisavid/arch-pkgs/issues/89).

```bash
makepkg --verifysource
makepkg -f
```

Do not enable or start the candidate on a production route from this package
directory. Staging, disposable install, commissioning, evidence capture,
promotion, cutover, rollback, and soak belong to their accepted implementation
and deployment tasks and must bind exact package/archive identities.
