# open-webui

Disposable Arch package candidate for Open WebUI 0.11.0 and the fresh household
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
- The package builds the exact 0.11.0 source archive, seeds and verifies the 60
  release-authored Pyodide files from the exact release wheel, runs `npm ci`
  from a verified 1,233-tarball npm cache, and installs a hash-locked
  222-wheel private server closure. Both closure archives are immutable
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

Open WebUI 0.11.0 joins a prefix directly to the text. Settings can only
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
signup is false. After it succeeds, consume and remove every bootstrap input
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
target under `/run` (for example a local TLS terminator listening on one)
needs no unit change. A loopback target would need one, and allowing
`127.0.0.1` would undo the loopback deny below. The route needs the optional `tailscale` package.

In userspace-networking mode, `tailscaled` forwards a tailnet connection on
any port it does not serve to that port on the host's `127.0.0.1`, which
would expose services that listen only on localhost to the tailnet. The unit
therefore denies the daemon `127.0.0.1` and `::1` (`IPAddressDeny=`), so
tailnet peers reach only what the node itself serves. Do not advertise routes
or an exit node from this node; those would forward to the host network
without this check. The deny drops a blocked forward rather than refusing it,
so the peer's attempt times out and holds one of the daemon's connection slots
for about two minutes. Peers that scan many ports can therefore exhaust those
slots and stall the serve route; if it stops answering after such a scan,
restart `open-webui-tailnet.service`. A tailnet policy that admits peers to
this node only on `tcp:443` avoids that, once step 2's check has passed.

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
   check the loopback deny from another tailnet computer that has `nc`,
   before any tailnet policy narrows this node to `tcp:443`. Use the Qdrant
   port in `open-webui.env` (6333 by default):

   ```sh
   nc -vz -w 5 <name>.<tailnet>.ts.net 6333
   ```

   It must time out, and about two minutes later
   `sudo journalctl -u open-webui-tailnet.service` must show the forward to
   `127.0.0.1:6333` failing. A connection or a quick refusal means the deny
   is not in effect; stop and roll back.
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

## Maintenance Baseline

- `authoritative_reference`: exact-version AUR `open-webui` recipe at commit
  `6a65fb1cc4583d1ab9a1215a9cdf74054b36655b`
- `advisory_references`: upstream `open-webui/open-webui` 0.11.0 PyPI source
  archive and build metadata at tag commit
  `f9590b8017199e56d5e953657e6498e3cef1d246`, source SHA-256
  `e28c4fa997bf0a678caa7a0db6441da2e0c33b9a4120677f959ec3e45fccf9e9`,
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
    tailnet route, with log uploads off unless the operator opts in and no
    access to the host's loopback address; its login and serve configuration
    stay runtime state.
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

`open-webui-private-requirements.lock` is generated from the exact 0.11.0
source archive, whose upstream `uv.lock` is SHA-256
`bf42de5c836d5afe5628533cf8369e856d5d09bfd00efef302c31df3fa249947`.
The package-local constraints select the audited release versions plus the
`qdrant-client==1.18.0` optional backend and its
`portalocker==3.2.0` dependency. The separate provider list removes the 21
pacman-owned distributions. Resolution is fixed to CPython 3.14 on
`x86_64-unknown-linux-gnu`, uv 0.12.5, and the recorded index cutoff.

Regenerate and verify the lock from an exact downloaded source archive with:

```bash
./generate-open-webui-private-lock.zsh ./open_webui-0.11.0.tar.gz
```

The generator verifies the source and upstream-lock digests, emits hashes for
every selected distribution, and runs the package-local structural verifier
before replacing the lock. Update the constraint/provider manifests and the
bound constants deliberately when changing the release or provider boundary.

### Offline dependency closures

The recipe binds two versioned release assets as `noextract` sources:

- `open-webui-npm-offline-closure-0.11.0.tar.zst` contains the 1,233 unique
  registry tarballs required by the exact release lock. The tracked manifest
  binds all 1,275 lock records to their SHA-512 integrity values and archive
  members. `prepare()` verifies the archive and seeds an isolated npm cache;
  the frontend build then runs `npm ci --offline`.
- `open-webui-python-offline-closure-0.11.0-cp314-x86_64.tar.zst` contains the
  222 wheels selected for CPython 3.14 on x86_64 Linux. Its embedded manifest
  binds every file to the private requirements lock. `prepare()` verifies safe
  members and exact identities before extraction; installation uses
  `uv --offline --no-index --require-hashes` against only that wheelhouse.

The closure helpers are deterministic and reject extra, missing, unsafe, or
digest-mismatched members. Regenerate candidate archives in disposable output
directories, compare two independent outputs byte-for-byte, and publish only
the reviewed bytes at the recipe's versioned build-input release:

```bash
python npm-offline-closure.py materialize \
  --lock open_webui-0.11.0/package-lock.json \
  --manifest npm-offline-closure-manifest.json \
  --archive open-webui-npm-offline-closure-0.11.0.tar.zst \
  --cache npm-download-cache

python python-offline-closure.py materialize \
  --lock open-webui-private-requirements.lock \
  --output python-closure
python python-offline-closure.py archive \
  --lock open-webui-private-requirements.lock \
  --manifest python-closure/manifest.json \
  --wheelhouse python-closure/wheelhouse \
  --output open-webui-python-offline-closure-0.11.0-cp314-x86_64.tar.zst
```

These inputs remove the dependency-network blocker. The subsequent no-egress
pkgrel-3 build and payload-inspection gate passed and is recorded in
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
