# Open WebUI 0.11 runtime, trust, and migration boundary

Research snapshot: 2026-08-18

## Conclusion

The household runtime accepted in [the Open WebUI policy decision][decision-26]
is feasible on Open WebUI 0.11.0, with one source change: the supported
`open-webui serve` command needs the accepted mutually exclusive `--uds` option.
Upstream 0.11.0 otherwise supplies the required authentication, per-user and
per-group access grants, authenticated-instance sharing, anonymous-sharing
denial, persistent configuration, Redis-compatible session revocation, and
health/readiness primitives.

The implementation must not infer effective behavior from the environment file
or `/ready` alone:

- Most administrator settings are seeded from the environment and then owned by
  individual database rows. Existing database values win on later starts.
- OAuth settings remain environment-owned by default, while several runtime and
  security settings are always environment-owned.
- Startup catches and logs database-migration exceptions. `/ready` proves only
  startup completion plus database and optional Redis connectivity; it does not
  prove the expected Alembic head.
- Server-side Tools and Functions execute submitted Python in the Open WebUI
  process. A user allowed to create or import a Tool crosses the backend service
  boundary. Runtime frontmatter requirements may also invoke `pip install`.
- A stable `WEBUI_SECRET_KEY`, the database, Valkey revocation state, uploads,
  vector state, effective configuration, proxy/socket policy, and the old
  launcher must move and roll back as one runtime boundary.

No upstream feasibility blocker remains for the map. The next facts and
decisions are sharply bounded: [issue #65][issue-65] must collect the redacted
private deployment facts enumerated below under separate read-only authority;
[issue #66][issue-66] must freeze their target ownership and values. This
research inspected no live private service state and authorizes no deployment.

## Authority and scope

This document answers [issue #64][issue-64] for the execution map rooted at
[issue #48][issue-48]. It interprets, but does not amend, the accepted household
contract in [issue #26][decision-26]. That contract remains authoritative for
exposure, users, sharing, plugins, egress, limits, state, migration, rollback,
and acceptance.

The source audit is pinned to the official Open WebUI tags:

- `v0.11.0` at commit
  [`f9590b8017199e56d5e953657e6498e3cef1d246`][owui-011-commit]
- `v0.9.5` at commit
  [`3660bc00fd807deced3400a63bfa6db47811a3bb`][owui-095-commit]

Only public source, public documentation, and public tracker decisions were
used. Hostnames, addresses, account identifiers, secret values, content names,
and private paths are deliberately absent.

## Effective configuration authority

Open WebUI 0.11 stores persistent settings as one database row per dotted key.
Reads return the database value when present, and startup only inserts defaults
for missing keys. OAuth keys are excluded unless
`ENABLE_OAUTH_PERSISTENT_CONFIG=true` ([model][config-model],
[startup configuration][config-startup]).

The deployment has three configuration authorities:

| Authority | Representative settings | Required treatment |
| --- | --- | --- |
| Database rows | `ui.enable_signup`, `ui.default_user_role`, `user.permissions`, sharing, upload limits, `auth.jwt_expiry`, `webui.url`, models/providers, search, webhooks | Preserve and export the effective redacted rows. Do not assume a changed environment default overrides an existing row. |
| Environment when OAuth persistence is off | OAuth enablement, clients, redirects, role/group mapping, and OAuth credentials | Preserve the effective environment source separately. Revisit persistence deliberately before changing this default. |
| Environment-only runtime boundary | `DATA_DIR`, `DATABASE_URL`, `REDIS_URL`, `REDIS_KEY_PREFIX`, `WEBUI_AUTH`, `WEBUI_SECRET_KEY`, cookie flags, `CORS_ALLOW_ORIGIN`, plugin and runtime-pip flags, `OFFLINE_MODE`, API passthrough, profile-image forwarding, storage and vector backends | Set explicitly in the packaged service and verify process-effective values without exposing secrets. |

Keep `ENABLE_PERSISTENT_CONFIG=true`. Before cutover, acceptance must compare the
complete persistent key set and selected redacted effective values against the
pre-cutover fixture. The environment file, database export, and admin UI are
different views; none is a substitute for the others.

The supported `serve` entrypoint also treats secret storage as configuration
state. If `WEBUI_SECRET_KEY` is absent, it creates `.webui_secret_key` in the
current working directory ([entrypoint][serve-entrypoint]). The packaged service
must instead name one stable secret authority and must not rely on an incidental
working directory.

### Configuration acceptance checks

The migration fixtures and deployed runtime must prove:

1. the complete pre-upgrade persistent key set is represented after migration;
2. signup remains disabled and the default role remains `pending`;
3. effective permissions and share controls equal the accepted matrix;
4. the exact HTTPS `webui.url`, JWT expiry, upload limits, allowed extensions,
   and provider/search choices are preserved;
5. environment-only security settings are process-effective; and
6. no plaintext secret is emitted into logs, reports, build artifacts, or the
   repository.

## Authentication, authorization, and sharing

Authentication defaults on. Open WebUI 0.11 exits when authentication is on and
`WEBUI_SECRET_KEY` is empty; cookie SameSite defaults to `lax` and cookie Secure
defaults to false ([environment source][auth-env]). The household target must
set both auth and session cookies to Secure and SameSite `strict`, preserve the
stable secret, and keep bypass access-control flags false.

The first account becomes administrator and then writes
`ui.enable_signup=false`. Later signups require the persisted signup and login
flags ([signup path][signup-source]). The accepted runtime must preserve the
existing accounts, roles, groups, and first administrator rather than exercise
bootstrap behavior. New accounts remain `pending` until an administrator acts.

Open WebUI models sharing as access grants:

| Intended audience | Stored grant | Household policy |
| --- | --- | --- |
| Named user | `user:<id>` | Allowed |
| Named group | `group:<id>` | Allowed |
| Every authenticated instance user | `user:*` | Allowed |
| Anyone with the link, without authentication | `anyone:*` read | Disabled |

The distinction is explicit in the [access-grant model][access-grants]. A shared
chat is a database-backed snapshot and its read endpoint accepts an anonymous
request only when the `anyone:*` path succeeds ([chat sharing][chat-sharing]).
Default user/group access grants are enabled, while public and open chat sharing
default off ([permission defaults][permission-defaults]). Group permissions
combine permissively, so any group can grant a capability that another group
denies ([permission merge][permission-merge]).

Acceptance therefore needs positive tests for owner, named-user, named-group,
and `user:*` access, plus negative tests for unrelated authenticated users where
no grant exists and for anonymous access in every case. It must also inspect the
effective union of each test user's group permissions.

If OAuth is later enabled, issue #66 must revisit SameSite `strict` against the
chosen provider's callback flow. The current household contract does not require
OAuth, so that compatibility question is not a blocker for the accepted local
authentication target.

## Plugin, Tool, and code-execution boundary

Open WebUI's server-side extension model is not a sandbox:

- Tool and Function source is executed with Python `exec` inside the backend
  process ([plugin loader][plugin-loader]).
- A Function create route is administrator-only, but a non-administrator can
  create a Tool when either `workspace.tools` or `workspace.tools_import` is
  granted ([Function route][function-route], [Tool route][tool-route]).
- `ENABLE_PLUGINS` and runtime frontmatter installation default on. Frontmatter
  requirements call the running interpreter's `pip`, including a startup pass
  over active Functions and administrator Tools ([dependency loader][plugin-deps]).
- Workspace Tool access/import defaults off, but persisted permissions and
  permissive group unions can change the effective result.

For this household boundary, Open WebUI administrators are host-equivalent.
Only reviewed administrator-owned server extensions are allowed. Ordinary users
may use approved extensions but must not create or import server-side Tool or
Function code. The package must set
`ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS=false`; approved dependencies belong
in the reproducible package closure.

Browser-local Pyodide remains a separate, ordinary-user capability. Its browser
execution does not relax the backend Tool/Function boundary. Acceptance must
exercise both: approved browser-local execution succeeds, while an ordinary
user's server Tool creation/import request is denied.

Inventory active Tools and Functions by owner-role class, active state, source
digest, and requirements digest. Do not publish private source or names. Review
each approved extension for filesystem access, subprocesses, credential access,
and egress before enabling it.

## Egress, origin, cookies, and proxy headers

Open WebUI has multiple independent egress producers: model and embedding
providers, web search/fetch, content extractors, speech/image services, webhooks,
OAuth/LDAP, object storage, tool/MCP/OpenAPI servers, update checks, model
downloads, profile-image forwarding, and arbitrary plugin Python. Disabling one
feature does not constrain the others.

The built-in web-fetch path restricts schemes to HTTP(S), blocks non-global
addresses when local fetch is off, and revalidates DNS at connection time
([fetch validation][fetch-validation]). That is useful defense in depth, but it
does not govern arbitrary plugin code. The accepted no-unexpected-egress
contract therefore requires both:

- an explicit feature-to-destination allowlist with unneeded features disabled;
  and
- network-boundary observation/enforcement that detects plugin and dependency
  traffic outside that allowlist.

Keep local web fetch, API passthrough, profile-image URL forwarding, unattended
model downloads, startup dependency installation, and version checks disabled
unless a later reviewed decision adds a destination. Admin-configured providers
and search endpoints are allowed only as recorded allowlist entries.

`CORS_ALLOW_ORIGIN` defaults to `*`, and middleware allows credentials, every
method, and every header ([CORS source][cors-source]). Set one exact HTTPS origin
and no custom schemes. Set the same persisted `webui.url`. Caddy must overwrite
rather than append client forwarding headers and must support WebSocket, SSE,
uploads, reloads, and long responses. The upstream CLI currently starts Uvicorn
with `forwarded_allow_ips='*'`, so socket reachability and Caddy header
normalization are security controls, not conveniences.

## Unix socket and Caddy boundary

Upstream `open-webui serve` accepts only `host` and `port`, then forwards them to
Uvicorn ([entrypoint][serve-entrypoint]). The accepted patch remains necessary:

- add nullable `--uds`;
- make `--uds` mutually exclusive with host/port selection;
- pass the path to Uvicorn while retaining every `serve` initialization step;
  and
- reject direct Uvicorn invocation as a supported service path.

The service creates `/run/open-webui/open-webui.sock` inside a systemd
`RuntimeDirectory` with mode `0750`. Only the Caddy service identity's narrow
socket-access group may traverse it. Caddy must not join the Open WebUI data
group and must not read the database, environment, secret, uploads, vector data,
cache, or snapshots. Open WebUI must have no TCP listener.

Caddy supports a Unix socket upstream in `reverse_proxy` and handles WebSocket
upgrades ([Caddy reverse proxy][caddy-reverse-proxy]). G3 must verify socket
creation, stale-socket recovery, restart behavior, owner/group/mode, and listener
inventory. G4 must verify external HTTPS behavior, forwarding-header spoofing
denial, WebSocket, SSE, maximum-size uploads, 25-file operations, reloads, and
long responses.

`/health` is unconditional liveness. `/ready` additionally checks startup,
database reachability, and configured Redis reachability
([health source][health-source]). Neither endpoint is a migration or application
data-integrity check.

## Secret, Valkey, and durable state

`WEBUI_SECRET_KEY` signs JWTs and is the default key for OAuth client/session
encryption ([auth source][auth-source]). It also derives the key for encrypted
valve values ([valve encryption][valve-encryption]). Treat it as durable state:
snapshot and restore it with the database, verify identity by a non-reversible
fingerprint, and never write the value into public evidence.

Open WebUI accepts `redis://` or `rediss://` URLs, not a `valkey://` scheme
([Redis-compatible URL][redis-url]). Valkey must therefore be exposed through
its Redis-compatible protocol and URL. Logout and back-channel revocation are
checked only when Redis-compatible state is present; logout stores revocation
keys with the JWT's remaining TTL ([token revocation][token-revocation]). Losing
or evicting a revocation key can make a signed-out token valid until its bounded
expiry.

Use a dedicated Valkey ownership boundary where practical. Set a stable prefix,
a 24-hour JWT expiry, `noeviction`, authentication/ACLs, and durable AOF or RDB
persistence. Bind the Valkey recovery point to the same quiesced snapshot as the
database and secret. Valkey documents the durability and recovery tradeoffs of
RDB and AOF ([Valkey persistence][valkey-persistence]). If the private inventory
finds a shared instance or database, issue #66 must decide how to avoid restoring
or deleting unrelated applications' keys.

### Durable state manifest

The migration and rollback manifest must enumerate effective, not assumed,
locations and providers for:

- the SQL database and Alembic version;
- the complete `DATA_DIR`, including local uploads and cache;
- the vector backend and its local or remote state;
- object-storage configuration and remote objects, if configured;
- persistent Config rows, accounts, groups, access grants, shared snapshots,
  Tools, Functions, prompts, knowledge, models, and provider definitions;
- the stable secret and any distinct OAuth encryption keys;
- Valkey prefix/database, persistence artifacts, and revocation state;
- service, proxy, socket, environment, and secret-store configuration;
- the old Python 3.11 launcher, package artifacts, dependency cache, and exact
  rollback commands.

Open WebUI derives local uploads and cache from `DATA_DIR`, and its default
SQLite database and Chroma vector state live there too
([data layout][data-layout]). The 0.11 startup path also deletes and copies files
under `STATIC_DIR` ([static layout][static-layout]). A read-only packaged
application tree therefore needs an explicit writable `STATIC_DIR` or an
equivalent reviewed source change. G3 must prove startup under the final systemd
sandbox rather than only in a writable build tree.

## Database migration and whole-runtime rollback

The official migration graph has a single v0.9.5 head
[`a0b1c2d3e4f5`][095-migration-head] and a single v0.11.0 head
[`f0bd01a18a3d`][011-migration-head]. The 13-revision forward path includes a
knowledge-directory table, legacy primary-key repair, the Config storage
reshape, chat/message/memory/automation changes, indexes, and normalized-email
uniqueness.

Two migration details change the acceptance and rollback design:

1. `3ff2c63645b8` renames the old Config table to `config_old`, flattens the JSON
   blob into per-key rows, and retains unknown keys. Its normal downgrade drops
   the current per-key table and restores the frozen `config_old` table
   ([Config migration][config-migration]). Post-upgrade configuration changes do
   not merge into that preserved blob.
2. `f0bd01a18a3d` refuses to create its normalized-email unique index when
   case-insensitive duplicate emails exist ([email migration][email-migration]).

Separately, migration startup catches exceptions and continues importing the
application ([migration runner][migration-runner]). Deployment must therefore
fail closed on an independent exact-head query. A 200 from `/ready` is not
evidence of schema completion.

The two required migration fixtures have different purposes:

- Build a synthetic fixture with actual v0.9.5 code and migrate it to the
  v0.9.5 head, then start the packaged v0.11 runtime and verify the v0.11 head,
  Config reshape, accounts, groups, sharing, files, knowledge, providers, and
  security settings.
- Make a separately authorized disposable copy of the current 0.11/Python 3.11
  runtime, quiesce writers, start the packaged 0.11/Python 3.14 runtime against
  the copy, and compare structural and behavioral invariants without publishing
  private content.

Rollback is snapshot restoration, not an Alembic downgrade. Quiesce writers;
restore the database, state directories or remote-state recovery points,
Valkey, secrets, configuration, proxy/socket policy, and old launcher from one
identified pre-cutover set; then run negative and positive authentication,
sharing, plugin, provider, upload, and revocation checks before reopening access.

## Upload and resource boundary

The accepted limit is 250 MiB per file and 25 files per operation with a reviewed
extension allowlist. Open WebUI checks extension before upload, but its local
upload path obtains the stored file's complete byte content before enforcing the
configured maximum size ([upload source][upload-source]). Application limits
alone therefore do not bound pre-rejection disk, memory, proxy buffering, or
concurrent request cost.

The measurement task must exercise accepted and rejected files at the proxy and
service, include 25-file operations and concurrent users, and record peak memory,
disk, latency, and proxy behavior. Final limits belong in both effective Config
and the reverse-proxy/service resource policy.

## Minimum private deployment facts for issue #65

Issue #65 should capture these facts only after its separate read-only privilege
gate. Reports remain public-safe: publish topology classes, counts, modes,
versions, and digests; never publish secret values, addresses, private paths,
identifiers, content, filenames, or database rows.

| Boundary | Minimum facts to capture | Public-safe representation |
| --- | --- | --- |
| Runtime | Open WebUI version/commit if known, launcher, interpreter, dependency environment, service identity, unit/override identity, package/artifact origin | Versions, role classes, hashes, and ownership/mode classes |
| Network | Listening protocols, proxy-to-backend transport, firewall/exposure class, effective origin, forwarding-header behavior | `private HTTPS`, `loopback TCP`, or `UDS`; redact address and origin |
| Configuration | Every source file/provider, environment key names, complete persistent Config key set, effective security booleans and limits | Key names and redacted values; secret-bearing values replaced by type and digest |
| Secret | Secret source authority, stability across restarts, owner/mode, length class, distinct OAuth keys | Stable non-reversible fingerprint only; never the value |
| Database | Engine, version, Alembic head, owner/mode, size, checksum, backup mechanism, case-folded email-duplicate count | Engine/version/head, aggregate counts, sizes, hashes; no rows or identities |
| Authorization | Counts by role, group and membership counts, effective group-permission unions, access-grant counts by principal/resource/permission class | Aggregate matrix only |
| User state | Counts and sizes for chats, shared snapshots, uploads, knowledge, prompts, models, feedback, memory, and related tables | Aggregate counts/bytes and integrity digests; no names or content |
| Extensions | Tool/Function count, active state, owner-role class, source and requirements digests, runtime-installed dependencies | Aggregate inventory and digests; no private source |
| Providers and egress | Enabled feature classes, endpoint schemes and topology classes, proxy variables, observed destination classes | Provider/feature class and scheme; redact endpoints and credentials |
| Files/vector/object storage | Effective backend, root/provider authority, owner/mode, count/bytes, backup coverage, consistency method | Backend class, aggregate count/bytes, snapshot identity |
| Valkey | Version, dedicated/shared ownership, URL scheme, DB index, key prefix, ACL source, eviction policy, persistence mode, data recovery point, key/TTL classes | Redacted topology, policy, counts, and snapshot digest; no credential or endpoint |
| Proxy/socket | Caddy version and config digest, service identity/group memberships, socket path class, directory/socket owner/mode, routes and limits | Version, hashes, role and mode classes; redact origin/path if private |
| Rollback | Old launcher/interpreter/artifacts, pre-cutover snapshot set, checksums, encryption, retention, restore ordering, tested commands | Artifact identities, hashes, storage class, and redacted runbook |

The inventory must also record whether the current Valkey and object/vector
backends are shared with another application. Shared ownership is a decision
gate because whole-runtime restore must not mutate unrelated state.

## Decision inputs for issue #66

Issue #66 can be decision-complete once it freezes:

1. one owner and source of truth for every database-backed, OAuth, and
   environment-only setting;
2. the final service identity, writable state roots, `STATIC_DIR`, systemd
   sandbox, UDS lifecycle, runtime-directory group, and Caddy access;
3. the exact private HTTPS origin, cookie policy, client-header normalization,
   and no-secondary-listener invariant;
4. the account enrollment, effective permission, user/group sharing, `user:*`,
   and `anyone:*` matrix;
5. approved server extensions, ordinary-user negative permissions, packaged
   dependency closure, and browser-local Pyodide boundary;
6. the feature-to-destination egress allowlist and enforcement/observation
   mechanism;
7. the stable secret provider, distinct OAuth-key policy, Valkey ownership,
   prefix/database, ACL, no-eviction and persistence policy;
8. the complete state/snapshot manifest, exact schema-head gate, fixture
   invariants, writer-quiescence protocol, restore order, and retention window;
9. proxy/service upload and resource limits derived from measurement; and
10. G3 local acceptance, G4 deployed acceptance, promotion, cutover, rollback,
    and evidence owners.

No decision should use a live private value in a public issue. The issue should
record the selected policy and a redacted evidence locator or fingerprint.

## Acceptance implications

G3 local acceptance must produce immutable evidence for:

- exact package and source identity;
- supported `serve --uds` behavior and absence of TCP listeners;
- service sandbox and writable-state correctness;
- exact Alembic head and both migration fixtures;
- effective Config, environment-only controls, stable-secret identity, and
  Valkey restart/revocation behavior;
- role, group-union, sharing, anonymous denial, and Tool-import denial paths;
- allowed and denied egress;
- uploads, WebSocket, SSE, liveness, readiness, and whole-runtime rollback.

G4 deployed acceptance must repeat externally observable HTTPS, cookie, origin,
header, sharing, upload, streaming, provider, logout/revocation, and rollback
checks against the promoted artifact. It must keep build validation, immutable
artifact identity, hosted review/policy acceptance, and live publication as
separate evidence.

## Primary source log

- Open WebUI 0.11.0 source commit: [official tag commit][owui-011-commit]
- Open WebUI 0.9.5 source commit: [official tag commit][owui-095-commit]
- Open WebUI documentation: [plugin security][plugin-docs],
  [RBAC permissions][rbac-docs], [security hardening][hardening-docs], and
  [reverse-proxy/CORS troubleshooting][proxy-docs]
- Caddy documentation: [reverse proxy][caddy-reverse-proxy]
- Valkey documentation: [persistence][valkey-persistence]
- Repository authority: [decision #26][decision-26], [map #48][issue-48], and
  [research issue #64][issue-64]

[decision-26]: https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835
[issue-48]: https://github.com/nisavid/arch-pkgs/issues/48
[issue-64]: https://github.com/nisavid/arch-pkgs/issues/64
[issue-65]: https://github.com/nisavid/arch-pkgs/issues/65
[issue-66]: https://github.com/nisavid/arch-pkgs/issues/66
[owui-011-commit]: https://github.com/open-webui/open-webui/commit/f9590b8017199e56d5e953657e6498e3cef1d246
[owui-095-commit]: https://github.com/open-webui/open-webui/commit/3660bc00fd807deced3400a63bfa6db47811a3bb
[config-model]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/models/config.py#L99-L165
[config-startup]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/models/config.py#L239-L264
[serve-entrypoint]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/__init__.py#L13-L88
[auth-env]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/env.py#L705-L742
[signup-source]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/routers/auths.py#L844-L903
[access-grants]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/models/access_grants.py#L14-L32
[chat-sharing]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/routers/chats.py#L1188-L1213
[permission-defaults]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/config.py#L1699-L1862
[permission-merge]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/utils/access_control/__init__.py#L32-L69
[plugin-loader]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/utils/plugin.py#L206-L315
[function-route]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/routers/functions.py#L199-L227
[tool-route]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/routers/tools.py#L344-L394
[plugin-deps]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/utils/plugin.py#L419-L483
[fetch-validation]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/retrieval/web/utils.py#L106-L253
[cors-source]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/config.py#L2106-L2124
[caddy-reverse-proxy]: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
[health-source]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/main.py#L2768-L2811
[auth-source]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/utils/auth.py#L219-L273
[valve-encryption]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/utils/valves.py#L13-L39
[redis-url]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/utils/redis.py#L32-L53
[token-revocation]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/utils/auth.py#L244-L297
[valkey-persistence]: https://valkey.io/topics/persistence/
[data-layout]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/env.py#L218-L267
[static-layout]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/config.py#L91-L139
[095-migration-head]: https://github.com/open-webui/open-webui/blob/3660bc00fd807deced3400a63bfa6db47811a3bb/backend/open_webui/migrations/versions/a0b1c2d3e4f5_add_memory_user_id_index.py
[011-migration-head]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/migrations/versions/f0bd01a18a3d_add_unique_normalized_user_email_index.py
[config-migration]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/migrations/versions/3ff2c63645b8_reshape_config_to_per_key_rows.py#L462-L584
[email-migration]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/migrations/versions/f0bd01a18a3d_add_unique_normalized_user_email_index.py#L59-L75
[migration-runner]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/config.py#L62-L79
[upload-source]: https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/backend/open_webui/routers/files.py#L337-L397
[plugin-docs]: https://docs.openwebui.com/features/extensibility/plugin/
[rbac-docs]: https://docs.openwebui.com/features/authentication-access/rbac/permissions/
[hardening-docs]: https://docs.openwebui.com/getting-started/advanced-topics/hardening/
[proxy-docs]: https://docs.openwebui.com/troubleshooting/connection-error/
