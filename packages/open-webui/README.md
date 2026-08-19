# open-webui

Disposable Arch package candidate for Open WebUI 0.11.0 and the fresh household
native-RAG boundary.

This candidate is not approved for production activation or publication. A
successful source verification or build is only a package gate; issue
[#68](https://github.com/nisavid/arch-pkgs/issues/68) still requires the exact
composed runtime and disposable evidence, including the accepted patched
Lemonade/llama provider root. The dated measurement boundary remains in
[`docs/maintainers/open-webui-household-envelope.md`](../../docs/maintainers/open-webui-household-envelope.md).

## Packaged Boundary

- Open WebUI serves only on `/run/open-webui/open-webui.sock`. Caddy can reach
  the socket through the dedicated `open-webui-proxy` group once an accepted
  route is installed and restarted; Caddy does not join the Open WebUI data
  group.
- The package builds the exact 0.11.0 source archive, seeds and verifies the 60
  release-authored Pyodide files from the exact release wheel, runs `npm ci`
  from a verified 1,233-tarball npm cache, and installs a hash-locked
  222-wheel private server closure. Both closure archives are immutable
  `makepkg` sources and both installers run in offline mode.
- The ML and native scientific stack remains pacman-owned. The package verifies
  that none of the 21 externalized provider distributions appears under
  `/opt/open-webui`.
- Native RAG uses the five Qdrant collections under
  `open-webui-rag-v1`, zembed query/document prefixes, and the external zerank
  reranker. Reranker qualification is mandatory for document RAG; ordinary
  chat remains available when that provider is unhealthy.
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
| `lemonade-inference-api-key` | inference-only embedding/reranking credential |
| `session-epoch` | read-only copy of the external root-owned epoch ledger |

Provision the six encrypted service credentials once under the exact paths
declared by `open-webui.service`. The service receives no Qdrant or Lemonade
administrative credential. Manual delivery is not part of ordinary startup;
operator handling is limited to initial provisioning, deliberate rotation, or
restore.

The Lemonade embedding and reranking keys remain external service authority:
Open WebUI neither persists nor exports them, and its document settings do not
accept replacements. Rotate that credential at its systemd source and restart
the service.

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

The first start happens while Caddy cannot reach the new socket. A temporary
systemd drop-in supplies `admin-email`, `admin-name`, and
`admin-bootstrap-password` credentials to the launcher. Run
`/usr/lib/open-webui/open-webui-commission-admin` once through a transient
systemd unit that supplies `admin-email`, `admin-name`,
`admin-bootstrap-password`, and `admin-final-password` as protected
credentials—not arguments or environment values—so the complete commissioned
identity is verified.

The helper signs in over the Unix socket, changes the password through the
exact 0.11 API, proves the bootstrap password no longer works, proves the final
password works, verifies exactly one intended administrator, and verifies
signup is false. After it succeeds, consume and remove every bootstrap input
and temporary drop-in, restart `open-webui.service` normally, repeat the
postconditions, and only then make Caddy routing eligible for a later accepted
deployment task.

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

These inputs remove the dependency-network blocker. They do not by themselves
make the package accepted: build and payload inspection remain package gates,
and the integrated provider, restore, and rollback evidence required by #68
must still pass before #69 can begin.

```bash
makepkg --verifysource
makepkg -f
```

Do not enable or start the candidate on a production route from this package
directory. Staging, disposable install, commissioning, evidence capture,
promotion, cutover, rollback, and soak belong to their accepted implementation
and deployment tasks and must bind exact package/archive identities.
