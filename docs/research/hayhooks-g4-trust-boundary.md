# Hayhooks G4 runtime and trust-boundary audit

Status: decision-complete research for [#39](https://github.com/nisavid/arch-pkgs/issues/39), based on the accepted G4 contract in [#27](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959).

## Disposition

Hayhooks 1.23.0 and Haystack 3.0.0 can support the intended household service, but the unmodified upstream runtime and the current package service are not acceptable for that role. A small downstream Hayhooks production-profile patch, the already-required Haystack telemetry patch, an immutable pipeline manifest, and tighter systemd isolation are required.

There is no architectural deal-breaker. The main implementation risk is that upstream's normal convenience surface is deliberately much broader than the accepted service: unauthenticated runtime deployment, an always-mounted dashboard trace API, permissive cross-origin access, fail-open startup, and request-payload logging all exist in the default application.

Two operator decisions remain:

1. Whether every process and browser origin on the service host is trusted to call Hayhooks. Loopback binding limits network reach but supplies no caller identity.
2. The exact positive HTTP route allowlist for production, especially docs, drawing, unversioned OpenAI aliases, and file upload. The accepted contract excludes mutation and dashboard surfaces but does not enumerate every allowed base route.

Everything else below is sufficiently concrete for ordinary implementation-ticket projection.

## Scope and provenance

This audit covers only the initial G4 service lane: Hayhooks REST/OpenAI compatibility, Haystack pipeline loading, a loopback Qdrant dependency, systemd execution, and the reviewed administrator-owned pipeline artifact. A2A, MCP, Chainlit, dashboard UI/tracing, external model providers, GPU use, and runtime package installation remain outside the accepted surface.

| Source | Exact revision | Verified release artifact |
| --- | --- | --- |
| Hayhooks 1.23.0 | [80276610cb92eab74d623482f24226a2308ff609](https://github.com/deepset-ai/hayhooks/tree/80276610cb92eab74d623482f24226a2308ff609) | [PyPI sdist](https://files.pythonhosted.org/packages/9e/d1/3e78fa4115908e6d7af880c09474715ae7c7a5c6151d776cb8c6ec22175f/hayhooks-1.23.0.tar.gz), SHA-256 98e70929844ce4adc11eef8853e05dc95ee39d49d8dd558d8d2abfad46dae403 |
| Haystack 3.0.0 | [86e06ee1f0b6a5301a82263bdb01118ebd76af73](https://github.com/deepset-ai/haystack/tree/86e06ee1f0b6a5301a82263bdb01118ebd76af73) | [PyPI sdist](https://files.pythonhosted.org/packages/19/74/f5b82c7bd90345abfff69a76445ee63e9b42f362303946a97bfd5cf49e08/haystack_ai-3.0.0.tar.gz), SHA-256 c948a337e7a53d9bc47f3c08c2ad5e52ca6bd44956ad6d9e3512209a056493b4 |
| fastapi-openai-compat 1.2.0 | [11da3a2262e9c09dbb5cbe44ce5b9cccd731e952](https://github.com/deepset-ai/fastapi-openai-compat/tree/11da3a2262e9c09dbb5cbe44ce5b9cccd731e952) | [PyPI sdist](https://files.pythonhosted.org/packages/51/1d/529d4ed39cc4b3936d7ad24161a614b420f784cf2109c137937184eeca98/fastapi_openai_compat-1.2.0.tar.gz), SHA-256 0cb5a545e6e65c67172c0b98531cac9949dd5ff614893007789470f3dc096956 |

The release-tag commits were resolved before inspection. The Python source in each sdist was compared with its exact commit. Hayhooks differed only by an empty hidden Chainlit directory that Git can represent and the sdist cannot.

The repository currently packages Hayhooks 1.19.2, not the target. Its [service](../../packages/hayhooks/hayhooks.service), [environment defaults](../../packages/hayhooks/hayhooks.env), [tmpfiles rules](../../packages/hayhooks/hayhooks.tmpfiles), and [PKGBUILD](../../packages/hayhooks/PKGBUILD) are evaluated here as the migration baseline, not as evidence about 1.23 behavior.

## Accepted service boundary

The accepted #27 contract describes this system:

- Open WebUI is the only intended client; household users do not call Hayhooks directly.
- Hayhooks listens on loopback and starts only reviewed, administrator-owned pipelines.
- Runtime deploy, undeploy, dashboard build, dependency bootstrap, A2A, MCP, Chainlit, dashboard/tracing, external providers, subprocesses, GPU access, and broad filesystem access are absent.
- The expected pipeline names, artifact digest, component classes, and deterministic canary are verified fail-closed.
- Telemetry is disabled when unset downstream and explicitly disabled in the service.
- Prompts, uploads, and secrets do not enter logs.
- Request, upload, concurrency, timeout, memory, and disk limits are finite.

The resulting trust boundaries are:

| Boundary | Trusted input | Untrusted or constrained input |
| --- | --- | --- |
| Administrator to packaged artifact | Reviewed YAML and wrapper files, exact manifest and hashes | Any unexpected, changed, wildcard-enabled, or unsafe artifact |
| Open WebUI to Hayhooks | Requests relayed by the intended local client | Direct same-host callers, browser origins, malformed bodies, oversized prompts/uploads |
| Hayhooks process to pipeline code | Exact reviewed classes and wrapper setup | Runtime-supplied Python, arbitrary deserialization targets, unreviewed component constructors |
| Hayhooks to Qdrant | One loopback dependency using a scoped credential | All non-loopback network destinations and unrelated Qdrant collections |
| Process to host | Narrow read-only artifact, temporary files, bounded runtime state | Persistent pipeline mutation, working-directory environment injection, home/device/kernel access |
| Process to observability | Request identifiers and bounded operational metadata | Prompt text, uploaded bytes, secret values, trace payloads, raw exception data |

## Confirmed upstream runtime

### Application and route surface

The normal Hayhooks application has no authentication middleware. Its settings default to host localhost, port 1416, wildcard CORS origins, methods, and headers, and a disabled dashboard UI flag. The application nevertheless includes status, draw, deploy, undeploy, OpenAI, and dashboard API routers unconditionally; only the dashboard static UI and Chainlit mount are conditional. FastAPI's docs and OpenAPI routes are also left at their defaults. See [settings.py lines 36–57 and 114–162](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/settings.py#L36-L162) and [app.py lines 279–344](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/app.py#L279-L344).

The concrete base process exposes:

| Surface | Routes |
| --- | --- |
| Framework | GET /openapi.json, /docs, /docs/oauth2-redirect, /redoc |
| Status and drawing | GET /status, /status/{pipeline_name}, /draw/{pipeline_name} |
| Runtime mutation | POST /deploy-yaml, /deploy_files; POST /undeploy/{pipeline_name} |
| OpenAI compatibility | GET /v1/models and /models; POST /v1/chat/completions and /chat/completions; POST /v1/responses and /responses; POST /v1/files and /files |
| Dashboard API | GET /dashboard/api/entrypoints, /config, /traces, /traces/stream; POST /dashboard/api/traces/clear |
| Per-pipeline | POST /{pipeline_name}/run, generated when a pipeline is loaded |

The OpenAI aliases and upload implementation are confirmed in the exact [fastapi-openai-compat routers](https://github.com/deepset-ai/fastapi-openai-compat/tree/11da3a2262e9c09dbb5cbe44ce5b9cccd731e952/src/fastapi_openai_compat). File upload reads the entire upload into memory before handing it to a compatible wrapper, with no application-level size limit in that code path ([files/router.py lines 58–71](https://github.com/deepset-ai/fastapi-openai-compat/blob/11da3a2262e9c09dbb5cbe44ce5b9cccd731e952/src/fastapi_openai_compat/files/router.py#L58-L71)).

A2A and MCP are separate CLI server commands; the ordinary hayhooks run command does not start them. Chainlit is a conditional mount. They can therefore remain absent through dependency selection, service invocation, and route tests rather than by maintaining a second service.

### Runtime deploy and undeploy

Runtime deploy is code execution, not merely configuration upload. POST /deploy_files accepts text files including pipeline_wrapper.py, optionally persists them, imports the package, instantiates PipelineWrapper, and calls setup. Even save_files=false writes the submitted files to a temporary directory before import, so making the configured pipeline directory read-only does not disable execution. See [deploy.py lines 21–152](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/routers/deploy.py#L21-L152), [deploy_utils.py lines 645–685](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/utils/deploy_utils.py#L645-L685), and [module_loader.py lines 21–101](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/utils/module_loader.py#L21-L101).

The persistence path also joins caller-supplied pipeline and file names beneath the pipeline directory without a visible containment check ([deploy_utils.py lines 131–180](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/utils/deploy_utils.py#L131-L180)). This is not a production-service finding to patch separately because the accepted profile must not compose any mutation route at all. A reverse-proxy rule alone is insufficient: a same-host caller could reach the backend directly.

Required control: add an explicit production application profile that does not include the deploy or undeploy routers and does not register mutation tools. Verify route absence in the application's OpenAPI document and with direct requests to the backend.

### Startup deployment and readiness

At startup, Hayhooks scans every top-level YAML file and every directory in the configured pipeline directory. Both sequential and parallel loaders catch individual failures, log that the source was skipped, and continue. The process then serves even if only a subset loaded. The aggregate status endpoint always reports Up! with whatever names reached the registry; it does not verify an expected manifest or canary. See [app.py lines 124–245](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/app.py#L124-L245) and [status.py lines 25–49](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/routers/status.py#L25-L49).

Required control: startup must compare an administrator-owned manifest against the exact discovered names and content digests, reject extra or missing artifacts, load all expected pipelines, run the deterministic canary, and withhold readiness on any discrepancy. This is the implementation boundary shared with [#40](https://github.com/nisavid/arch-pkgs/issues/40) and [#44](https://github.com/nisavid/arch-pkgs/issues/44).

### YAML and Python trust

Haystack's YAML marshaller subclasses PyYAML SafeLoader, which prevents Python-specific YAML object construction ([yaml.py](https://github.com/deepset-ai/haystack/blob/86e06ee1f0b6a5301a82263bdb01118ebd76af73/haystack/marshal/yaml.py)). Pipeline reconstruction still imports component classes and invokes their from_dict methods or constructors. That is appropriate only for a reviewed artifact.

Haystack 3's deserialization gate always starts with these module prefixes: haystack, haystack_integrations, haystack_experimental, builtins, typing, and collections. Per-call arguments, the process API, and HAYSTACK_DESERIALIZATION_ALLOWLIST only add permission; unsafe=true bypasses the gate. They cannot narrow the default set. Hayhooks calls AsyncPipeline.loads without an allowed_modules argument or unsafe mode. See [serialization_security.py lines 5–40 and 132–161](https://github.com/deepset-ai/haystack/blob/86e06ee1f0b6a5301a82263bdb01118ebd76af73/haystack/core/serialization_security.py#L5-L161) and [yaml_pipeline_wrapper.py lines 250–268](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/utils/yaml_pipeline_wrapper.py#L250-L268).

Consequences:

- Setting HAYSTACK_DESERIALIZATION_ALLOWLIST to a narrow value does not implement an exact component-class allowlist.
- A value of * grants every module and must be rejected.
- Removing python-haystack-experimental from the package closes the import path but does not change the built-in string allowlist.
- The exact manifest must validate every serialized component type before Haystack loads it. If the accepted class set is narrower than all of haystack, the downstream patch must provide a genuinely replacing allowlist or enforce the class manifest ahead of deserialization.
- Reviewed Python wrappers are fully trusted code. Import and setup run during startup, and any wrapper can use the process's filesystem, network, environment, or subprocess permissions.

### Egress and telemetry

Unpatched Haystack 3 enables telemetry when HAYSTACK_TELEMETRY_ENABLED is unset. Initialization writes a UUID to ~/.haystack/config.yaml, collects system properties, and configures PostHog at https://eu.posthog.com; pipeline-run events include component classes, names, and component-provided metadata. See [_telemetry.py lines 26–115 and 139–193](https://github.com/deepset-ai/haystack/blob/86e06ee1f0b6a5301a82263bdb01118ebd76af73/haystack/telemetry/_telemetry.py#L26-L193).

The accepted downstream behavior therefore requires both:

1. A small Haystack patch changing the unset default to disabled while preserving explicit true as the reversible library-level opt-in.
2. HAYSTACK_TELEMETRY_ENABLED=false in the Hayhooks service, independently of the library default.

The service also needs a destination-level egress policy. RestrictAddressFamilies permits socket families; it does not limit destination addresses. Haystack's allowed core package contains network-capable components such as LinkContentFetcher ([link_content.py lines 76–113](https://github.com/deepset-ai/haystack/blob/86e06ee1f0b6a5301a82263bdb01118ebd76af73/haystack/components/fetchers/link_content.py#L76-L113)), and reviewed Python wrappers have the same process network access.

For this provider-free service, use systemd IPAddressDeny=any with IPAddressAllow=localhost, then verify that the host supports the required cgroup eBPF enforcement. The localhost symbolic set covers IPv4 loopback and ::1 according to the [systemd.resource-control specification](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html#IPAddressAllow=ADDRESS%5B/PREFIXLENGTH%5D%E2%80%A6). Qdrant loopback traffic must remain successful while DNS and external IPv4/IPv6 probes fail. A future provider integration requires a separate accepted policy and service override.

### Logs, exceptions, uploads, and traces

The dynamic pipeline endpoint binds the complete parsed request payload to an INFO log record. Hayhooks' formatter prints every bound extra field other than request_id. The trace tag builder is safer by default—it records types and lengths and redacts values only when raw trace payloads are explicitly enabled—but it does not protect the independent INFO log. See [deploy_utils.py lines 258–325 and 408–419](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/utils/deploy_utils.py#L258-L419) and [logger.py lines 33–67](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/logger.py#L33-L67).

Dashboard UI disabled is not equivalent to dashboard tracing disabled. The dashboard API router is always mounted, its trace-list and SSE routes expose the in-process buffer, and Haystack-span capture defaults on ([dashboard.py lines 74–232](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/routers/dashboard.py#L74-L232), [settings.py lines 139–158](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/settings.py#L139-L158)).

Required controls:

- Remove request payload binding. Log only request ID, reviewed pipeline name, result class, elapsed time, and bounded status metadata.
- Keep raw trace payload values off and prevent the production profile from composing the dashboard API or in-process Haystack trace capture.
- Sanitize exception responses and logs so component inputs, prompt fragments, uploaded content, filesystem paths, and secret values cannot be reflected.
- Bound body and multipart upload size before reading the full request, and bound concurrency and execution time.

### Secrets

Haystack TokenSecret deliberately cannot serialize and redacts its representation. EnvVarSecret serializes only environment-variable names and resolves the first set variable at runtime ([auth.py lines 136–215](https://github.com/deepset-ai/haystack/blob/86e06ee1f0b6a5301a82263bdb01118ebd76af73/haystack/utils/auth.py#L136-L215)). No literal secret belongs in pipeline YAML, a unit file, command-line arguments, the package's environment-default file, OpenAPI, or logs.

Every trusted wrapper in the single process can read every process environment variable. Environment transport therefore cannot isolate one pipeline's secret from another. The current package installs /etc/hayhooks/hayhooks.env mode 0644, so that file must remain non-secret configuration. [#41](https://github.com/nisavid/arch-pkgs/issues/41) must select the Qdrant credential injection and rotation mechanism. If systemd credentials are selected, the wrapper or Qdrant adapter must read the credential file and construct a non-serializable TokenSecret; merely setting an environment-variable name in YAML does not consume a systemd credential.

The service's network and Qdrant-side collection permissions are both required. A scoped credential limits operations at Qdrant; loopback-only egress prevents the same process from sending the credential elsewhere over IP.

### Filesystem, environment discovery, subprocesses, and devices

Hayhooks imports python-dotenv at module load and searches upward from the current working directory for .env ([settings.py lines 1–15](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/settings.py#L1-L15)). The current service uses /var/lib/hayhooks as both StateDirectory and WorkingDirectory, and tmpfiles makes its pipelines subdirectory owned by the service account. StateDirectory makes that path writable despite ProtectSystem=strict. This lets a compromised process persist pipeline changes and a working-directory .env for the next restart.

Required layout:

- Put the accepted pipeline artifact in a root-owned, service-readable, non-writable directory.
- Do not use that directory as persistent process state.
- Make dotenv discovery unreachable in the production profile, preferably by a small upstreamable setting or patch, and use a root-owned working directory.
- Grant no persistent write path unless a demonstrated runtime requirement names it. Use PrivateTmp for transient upload files.
- Add PrivateDevices=true. Haystack can select CUDA, XPU, or MPS automatically when supporting libraries and devices exist ([device.py lines 437–523](https://github.com/deepset-ai/haystack/blob/86e06ee1f0b6a5301a82263bdb01118ebd76af73/haystack/utils/device.py#L437-L523)).

Core Hayhooks does not automatically install a pipeline directory's requirements.txt. The automatic dependency bootstrap found in 1.23.0 is the optional dashboard path: --with-tracing-dashboard can run npm ci or npm install followed by npm run build when prebuilt assets are absent ([cli/base.py lines 31–73 and 193–214](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/cli/base.py#L31-L214)). The production service must not pass that flag, must not install optional dashboard/A2A/MCP/Chainlit dependencies, and should omit dashboard source or make the build path unreachable. Reviewed wrapper code still has Python subprocess capability unless systemd syscall policy or the exact artifact review/test removes it.

## Threat model

| ID | Abuse path | Impact | Required break |
| --- | --- | --- | --- |
| T1 | Any local caller uses deploy_files to submit a wrapper | Code execution as the service user; filesystem and Qdrant access | Mutation routers absent in production; direct-backend negative test |
| T2 | Prompt, uploaded content, or secret-shaped input reaches logs or trace API | Household data disclosure and retention | Payload-free logging; dashboard API/capture absent; sentinel tests |
| T3 | Approved-module component or wrapper opens an external socket | Telemetry or content exfiltration; model/provider use | Exact component manifest plus deny-all/non-loopback egress |
| T4 | Service modifies its pipeline directory or working-directory .env | Persistent code/configuration change across restart | Root-owned artifact and workdir; dotenv disabled; no persistent write |
| T5 | One expected pipeline fails while the process still reports Up! | Silent partial service and misleading migration evidence | Exact manifest, all-or-nothing startup, canary-backed readiness |
| T6 | Same-host process or hostile browser origin calls the unauthenticated loopback API | Unauthorized household actions or data access | Resolve local-peer trust; authenticate or mediate if not all local callers are trusted; remove wildcard CORS |
| T7 | Oversized upload, prompt, fan-out, or long pipeline consumes resources | Denial of service, memory/disk exhaustion | Pre-read limits, finite concurrency/time/memory/disk policy |
| T8 | Secret is serialized, passed in argv, logged, or shared process-wide | Credential disclosure and cross-pipeline access | File-backed credential adapter, redaction tests, one reviewed pipeline boundary |

The attacker model is intentionally local and bounded: an unprivileged same-host process, a browser origin visited by a household user, malformed Open WebUI-relayed input, or a compromised request path. Administrator-controlled package installation and the exact reviewed pipeline artifact remain trusted. A malicious root user, malicious package-signing infrastructure, and an intentionally malicious accepted wrapper are outside this service threat model.

## Required production control set

### Downstream source behavior

- Hayhooks production profile composes only the accepted positive route set.
- Deploy, undeploy, dashboard API/UI and trace capture, Chainlit, A2A, and MCP are absent.
- Startup is all-or-nothing against the exact manifest and readiness canary.
- Request logs contain no request values; errors are sanitized.
- Dotenv discovery is disabled for the production profile.
- Haystack telemetry is disabled when unset, while explicit true remains a reversible library opt-in.
- Exact serialized component classes are validated before deserialization; wildcard and unsafe modes are rejected.

### Package and artifact shape

- Pin the three source artifacts and hashes above and keep the Python 3.14 dependency closure honest.
- Do not depend on python-haystack-experimental or optional Hayhooks UI/protocol extras.
- Install one root-owned reviewed pipeline artifact plus its exact manifest.
- Keep /etc/hayhooks/hayhooks.env non-secret and explicit about loopback, telemetry off, CORS off, tracing off, and production profile.
- Do not install or invoke runtime npm/pip/model bootstrap machinery.

### systemd boundary

- User and group dedicated to Hayhooks; NoNewPrivileges, ProtectSystem=strict, ProtectHome, PrivateTmp, kernel/control-group protections, MemoryDenyWriteExecute, native syscall architecture, restrictive umask.
- Root-owned working directory and pipeline artifact; no service-writable persistent pipeline or environment path.
- Bind explicitly to 127.0.0.1.
- IPAddressDeny=any and IPAddressAllow=localhost, verified on the installed host.
- PrivateDevices=true and no GPU/model dependencies.
- Finite MemoryMax, TasksMax, request concurrency, request/upload size, execution timeout, and temporary-disk policy, with exact numbers owned by #44.

The existing service already carries much of the generic hardening, but its writable StateDirectory/WorkingDirectory/pipeline layout and address-family-only network restriction do not meet this boundary. See the [systemd execution-path controls](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#ReadWritePaths=) and [resource-control network filters](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html#IPAddressAllow=ADDRESS%5B/PREFIXLENGTH%5D%E2%80%A6).

## Externally observable acceptance evidence

The implementation tickets should expose these seams as automated tests. Source-shape assertions alone are not sufficient.

| Seam | Required observation |
| --- | --- |
| Route composition | Direct backend requests to deploy, undeploy, every dashboard API route, Chainlit, A2A, and MCP fail closed; none appears in /openapi.json. Every accepted positive route succeeds or returns its documented application error. |
| Loopback | The only listening Hayhooks socket is 127.0.0.1 on the configured port; a non-loopback interface cannot connect. |
| Local caller policy | Wildcard CORS is absent. If same-host callers are not all trusted, an unauthenticated direct call fails while the chosen Open WebUI mediation succeeds. |
| Pipeline integrity | Missing, extra, renamed, modified, unreadable, unlisted-class, wildcard, unsafe, or setup-failing artifacts prevent readiness. Exact files, owners, modes, names, classes, and SHA-256 values pass. The service account cannot alter them. |
| Canary | Readiness becomes successful only after the exact deterministic fixture produces its expected answer and Qdrant scope behavior. |
| Egress | A loopback Qdrant request succeeds. External IPv4, IPv6, DNS, telemetry, model-provider, and arbitrary URL probes fail at the service boundary. |
| Telemetry | With the variable unset, Haystack creates no telemetry identity and calls no PostHog client. Explicit true activates a fake/sink client in the library test. The service always sets false unless a separately authorized override changes the whole policy. |
| Privacy | Unique prompt, upload, API-key, and exception sentinels are absent from journal output, HTTP error bodies, OpenAPI, process argv, environment-default files, and any trace endpoint. |
| Upload/request limits | A body or multipart file one byte above the accepted limit is rejected before the full payload is read or spooled; a boundary-size input succeeds. |
| Bootstrap and subprocess | Starting the service and running the fixture with empty caches does not launch npm, pip, model downloaders, shells, A2A, MCP, or extra worker processes and performs no network access beyond loopback. |
| Filesystem and devices | Reads and writes outside the exact allowed paths fail; persistent pipeline and .env writes fail; transient upload handling still works; GPU/device nodes are unavailable. |
| Secrets | The service starts only with the selected credential mechanism and fails closed when it is absent or malformed. Rotation and restart behavior match #41. No secret value is serialized. |
| Resource bounds | Concurrent, slow, cyclic, oversized, memory-heavy, and temp-disk-heavy requests hit the accepted finite limits without leaving the service falsely ready. |

G0 source and provenance, G1 package build/payload, G2 installed import/config, G3 installed service/integration, and G4 Open WebUI-visible behavior remain separate evidence. A passing source-level test does not prove the installed systemd controls, and a healthy socket does not prove the interactive path.

## Decisions and issue projection

### New decision fog

The [#37 map](https://github.com/nisavid/arch-pkgs/issues/37) did not explicitly assign two decisions revealed by the exact 1.23 route composition:

1. **Local peer identity:** Is every same-host process and browser origin trusted? If yes, loopback plus empty CORS and route minimization is the accepted boundary. If no, choose an authenticated reverse proxy, Unix-socket mediation, or another caller-identity control; loopback alone is insufficient.
2. **Positive route list:** Name the exact production routes, not only the excluded features. In particular decide whether /docs, /redoc, /draw, unversioned OpenAI aliases, and /v1/files are required by the Open WebUI fixture.

These are narrow policy decisions, not reasons to reopen the accepted architecture.

### Existing destinations

- [#40](https://github.com/nisavid/arch-pkgs/issues/40): exact pipeline files, names, hashes, component-class manifest, trusted wrapper shape, all-or-nothing load, deterministic canary identity.
- [#41](https://github.com/nisavid/arch-pkgs/issues/41): Qdrant credential file/adapter, collection scope, rotation, failure, and rollback behavior.
- [#42](https://github.com/nisavid/arch-pkgs/issues/42): deterministic provider-free retrieval fixture and expected results.
- [#43](https://github.com/nisavid/arch-pkgs/issues/43): reproducible G3/G4 measurements.
- [#44](https://github.com/nisavid/arch-pkgs/issues/44): exact request, upload, concurrency, timeout, memory, task, and temporary-disk limits plus readiness probes.
- [#45](https://github.com/nisavid/arch-pkgs/issues/45): implementation ordering and assignment of the downstream patches, service changes, and observable tests.

After the two decisions above are recorded, this audit is sufficient for normal issue projection. No additional exploratory research lane is required before implementation tickets are written.
