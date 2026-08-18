# Haystack G4 package and Python 3.14 closure

Research snapshot: 2026-08-18. This record answers
[`#38`](https://github.com/nisavid/arch-pkgs/issues/38) without changing any
package recipe, service, runtime, or host state.

## Conclusion

The upstream release set, source bytes, Arch package names, direct Python 3.14
runtime closure, build backends, package order, privacy patch boundary, and
currently available rollback bytes are identified below. All selected upstream
packages declare Python 3.14-compatible interpreter ranges; the only
interpreter-specific dependency is Qdrant Client's `numpy>=2.3.0` requirement,
which the current Arch `python-numpy` satisfies.

One dependency-shape decision is explicit: translate Hayhooks'
`fastapi[standard]` requirement to the bounded service providers listed below,
and do not add FastAPI project-generation, `fastar`, or cloud-CLI packages. That
deliberate Arch divergence follows the already accepted non-cloud,
non-dashboard service surface instead of silently growing the maintained lane.

The exact reviewed production pipeline manifest and the durable retention
destination for rollback archives remain execution inputs. A package build or
a pacman cache is not durable retention. This inventory is not authority to
implement, publish, deploy, delete, or close the rollback window.

## Frozen upstream source set

The source distribution is the package input. Git identities are additional
provenance, not substitutes for the independently verified source-distribution
digest. PyPI metadata supplies the interpreter and dependency contract for
each exact release.

| Arch package | Upstream release and source distribution | SHA-256 | Git identity | Python |
| --- | --- | --- | --- | --- |
| `python-haystack-ai` | [`haystack-ai 3.0.0`](https://pypi.org/project/haystack-ai/3.0.0/), [`haystack_ai-3.0.0.tar.gz`](https://files.pythonhosted.org/packages/19/74/f5b82c7bd90345abfff69a76445ee63e9b42f362303946a97bfd5cf49e08/haystack_ai-3.0.0.tar.gz) | `c948a337e7a53d9bc47f3c08c2ad5e52ca6bd44956ad6d9e3512209a056493b4` | tag object `49ae27e14874ebdb2bf300d798360fcd520ef3fe`, commit [`86e06ee1f0b6a5301a82263bdb01118ebd76af73`](https://github.com/deepset-ai/haystack/commit/86e06ee1f0b6a5301a82263bdb01118ebd76af73) | `>=3.10` |
| `hayhooks` | [`hayhooks 1.23.0`](https://pypi.org/project/hayhooks/1.23.0/), [`hayhooks-1.23.0.tar.gz`](https://files.pythonhosted.org/packages/9e/d1/3e78fa4115908e6d7af880c09474715ae7c7a5c6151d776cb8c6ec22175f/hayhooks-1.23.0.tar.gz) | `98e70929844ce4adc11eef8853e05dc95ee39d49d8dd558d8d2abfad46dae403` | lightweight tag and commit [`80276610cb92eab74d623482f24226a2308ff609`](https://github.com/deepset-ai/hayhooks/commit/80276610cb92eab74d623482f24226a2308ff609) | `>=3.10,<3.15` |
| `python-posthog` | [`posthog 7.38.4`](https://pypi.org/project/posthog/7.38.4/), [`posthog-7.38.4.tar.gz`](https://files.pythonhosted.org/packages/b1/c8/73ad89833953426b150462c3f3ea5ffda917f65e537acf47849ad61765e9/posthog-7.38.4.tar.gz) | `ec8f46255a7c30629e7fec6aef04ce79e157dbfff4e1d8ca0e0612e0abe16a68` | tag object `39d7f3a2c40175c5e9e59355b4d17715195d277b`, commit [`8ffe1ba8d33157afa3d256fa115bc206cf9027bc`](https://github.com/PostHog/posthog-python/commit/8ffe1ba8d33157afa3d256fa115bc206cf9027bc) | `>=3.10` |
| `python-qdrant-haystack` | [`qdrant-haystack 10.5.0`](https://pypi.org/project/qdrant-haystack/10.5.0/), [`qdrant_haystack-10.5.0.tar.gz`](https://files.pythonhosted.org/packages/3e/02/f03b5363e7e1d2be6aeb90e4295f80b99ab025ad018e982392421ad1163f/qdrant_haystack-10.5.0.tar.gz) | `19a0fb767520fbacdc2bd94594ee4c4e75cfbd0f5cc161203c6eb78cc8741206` | lightweight tag and commit [`3d1764b63e1c4d0e842d0dd248e09d20f0e3746a`](https://github.com/deepset-ai/haystack-core-integrations/commit/3d1764b63e1c4d0e842d0dd248e09d20f0e3746a) | `>=3.10` |
| `python-qdrant-client` | [`qdrant-client 1.19.0`](https://pypi.org/project/qdrant-client/1.19.0/), [`qdrant_client-1.19.0.tar.gz`](https://files.pythonhosted.org/packages/3a/33/c6e4ec45b4fca5a0b808e8804e60be54a6d7505b68b53c0b1d0d62ba86c1/qdrant_client-1.19.0.tar.gz) | `365395a04b0a26c309b25b7d8b1c99ef2071ec9a2b74bc8a5fd3b7a3642fe963` | tag object `75cc00b98ba205e65b8280dff58dc966b9d313a9`, commit [`425840be987cd470d19bbb4e2363e87754fbc914`](https://github.com/qdrant/qdrant-client/commit/425840be987cd470d19bbb4e2363e87754fbc914) | `>=3.10` |
| `python-portalocker` | [`portalocker 3.2.0`](https://pypi.org/project/portalocker/3.2.0/), [`portalocker-3.2.0.tar.gz`](https://files.pythonhosted.org/packages/5e/77/65b857a69ed876e1951e88aaba60f5ce6120c33703f7cb61a3c894b8c1b6/portalocker-3.2.0.tar.gz) | `1f3002956a54a8c3730586c5c77bf18fae4149e07eaf1c29fc3faf4d5a3f89ac` | signed tag object [`ae27490205d709a55dabc7f9bf103143bc5be2cc`](https://github.com/wolph/portalocker/releases/tag/v3.2.0), commit [`7415a5d20aa64ac347b0c734915ddbe49ce844f3`](https://github.com/wolph/portalocker/commit/7415a5d20aa64ac347b0c734915ddbe49ce844f3) | `>=3.9` |
| `python-lazy-imports` | [`lazy-imports 1.2.0`](https://pypi.org/project/lazy-imports/1.2.0/), [`lazy_imports-1.2.0.tar.gz`](https://files.pythonhosted.org/packages/25/67/04432aae0c1e2729bff14e1841f4a3fb63a9e354318e66622251487760c3/lazy_imports-1.2.0.tar.gz) | `3c546b3c1e7c4bf62a07f897f6179d9feda6118e71ef6ecc47a339cab3d2e2d9` | sdist boundary | `>=3.10` |
| `python-docstring-parser` | [`docstring-parser 0.18.0`](https://pypi.org/project/docstring-parser/0.18.0/), [`docstring_parser-0.18.0.tar.gz`](https://files.pythonhosted.org/packages/e0/4d/f332313098c1de1b2d2ff91cf2674415cc7cddab2ca1b01ae29774bd5fdf/docstring_parser-0.18.0.tar.gz) | `292510982205c12b1248696f44959db3cdd1740237a968ea1e2e7a900eeb2015` | sdist boundary | `>=3.8` |
| `python-fastapi-openai-compat` | [`fastapi-openai-compat 1.2.0`](https://pypi.org/project/fastapi-openai-compat/1.2.0/), [`fastapi_openai_compat-1.2.0.tar.gz`](https://files.pythonhosted.org/packages/51/1d/529d4ed39cc4b3936d7ad24161a614b420f784cf2109c137937184eeca98/fastapi_openai_compat-1.2.0.tar.gz) | `0cb5a545e6e65c67172c0b98531cac9949dd5ff614893007789470f3dc096956` | sdist boundary | `>=3.10` |
| `python-backoff` | [`backoff 2.2.1`](https://pypi.org/project/backoff/2.2.1/), [`backoff-2.2.1.tar.gz`](https://files.pythonhosted.org/packages/47/d7/5bbeb12c44d7c4f2fb5b56abce497eb5ed9f34d85701de869acedd602619/backoff-2.2.1.tar.gz) | `03f829f5bb1923180821643f8753b0502c3b682293992485b0eef2807afa5cba` | sdist boundary | `>=3.7,<4.0` |

The accepted issue text called `ae274902...` the portalocker commit. Primary Git
metadata shows that it is the signed annotated tag object; the peeled commit is
`7415a5d...`. This corrects the object type without changing the selected
version or source-distribution hash.

## Arch-facing references

The reference choice follows `docs/policies/reference-packages.md`: exact lane
before source rank, with Arch, then CachyOS, then AUR preferred inside the same
lane. Searches were refreshed on 2026-08-18; absence findings are time-bound.

| Package | Authoritative reference for implementation | Advisory references and deliberate divergence |
| --- | --- | --- |
| `python-portalocker` | Exact-lane AUR [`3.2.0-1` at `e386a351`](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=python-portalocker&id=e386a35168ac1111894ef60f15bb22be5bf969f2). | Keep the AUR dependency and setuptools-scm shape; do not enable Redis or Windows extras. |
| `python-backoff` | Same-version AUR [`2.2.1-4` at `309b1fc0`](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=python-backoff&id=309b1fc0429810c16b440e5954a200f711e2b8b9). | Use `python-poetry-core`, which the sdist's `pyproject.toml` requires; the current local recipe's setuptools build input is not the declared backend. |
| `python-docstring-parser` | Exact-lane AUR [`0.18.0-1` at `a0a331bb`](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=python-docstring-parser&id=a0a331bb52a7e0ce4008ebac978371b3d0217a17). | Do not copy the AUR recipe's `python-pytest` runtime dependency; upstream has no runtime dependency beyond Python. |
| `python-qdrant-client` | Upstream PyPI 1.19.0 source and metadata. | AUR [`1.18.0-1` at `3d547799`](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=python-qdrant-client&id=3d5477993fc3d8c2d5889b946fc5b5d448742636) is the closest Arch packaging shape, but not the target version. Preserve its explicit `python-h2` expansion for `httpx[http2]`; omit FastEmbed extras. |
| `python-posthog` | Upstream 7.38.4 source and metadata. | AUR [`6.7.9-1` at `621f2a53`](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=python-posthog&id=621f2a533e2c0066e62f645f5e095d4a262b81a8) is older and advisory only. Do not carry dependencies removed from 7.38.4 metadata. |
| Remaining target packages | Exact PyPI source and upstream Git identities in the source table. | No exact Arch or CachyOS package was found. AUR also had no exact package for `python-haystack-ai`, `hayhooks`, `python-qdrant-haystack`, `python-fastapi-openai-compat`, or `python-lazy-imports`; re-run [Arch](https://archlinux.org/packages/), [CachyOS](https://dashboard.cachyos.org/), and [AUR](https://aur.archlinux.org/packages) searches immediately before implementation. |

## Python 3.14 runtime closure

### Upstream requirements mapped to Arch names

Version operators below come from the exact PyPI metadata linked in the source
table. Unversioned entries have no upstream bound.

| Consumer | Arch runtime dependencies |
| --- | --- |
| `python-haystack-ai` | `python`, `python-docstring-parser`, `python-filetype`, `python-httpx`, `python-jinja`, `python-jsonschema`, `python-lazy-imports`, `python-markupsafe`, `python-more-itertools`, `python-networkx`, `python-numpy`, `python-openai>=1.99.2`, `python-posthog` with upstream exclusion `!=3.12.0`, `python-pydantic`, `python-dateutil`, `python-yaml`, `python-tenacity` with upstream exclusion `!=8.4.0`, `python-tqdm`, `python-typing_extensions>=4.7` |
| `hayhooks` | `python`, `python-haystack-ai` with upstream exclusion `!=2.18.0`, `python-docstring-parser`, `python-fastapi-openai-compat>=1.2.0`, `python-fastapi`, `python-httpx`, `python-jinja`, `python-email-validator`, `python-loguru`, `python-pydantic-settings`, `python-pydantic-extra-types`, `python-dotenv`, `python-python-multipart`, `python-requests`, `python-rich`, `python-typer`, `uvicorn`, `python-httptools`, `python-uvloop`, `python-watchfiles`, `python-websockets` |
| `python-posthog` | `python`, `python-requests>=2.7,<3`, `python-backoff>=1.10`, `python-distro>=1.5`, `python-typing_extensions>=4.2` |
| `python-qdrant-haystack` | `python`, `python-haystack-ai>=2.29.0`, `python-qdrant-client>=1.17.0` |
| `python-qdrant-client` | `python`, `python-grpcio>=1.41`, `python-httpx>=0.20`, `python-h2` for the HTTP/2 extra, `python-numpy>=2.3.0` on Python 3.14, `python-portalocker>=2.7,<4`, `python-protobuf>=3.20`, `python-pydantic>=1.10.8` excluding `2.0.*`, `2.1.*`, and `2.2.0`, `python-urllib3>=1.26.14,<3` |
| `python-portalocker` | `python`; `pywin32` is Windows-only and Redis is an excluded extra |
| `python-fastapi-openai-compat` | `python`, `python-fastapi`, `python-pydantic`, `python-python-multipart`; its `haystack` extra is excluded to avoid a duplicate dependency edge |
| `python-lazy-imports`, `python-docstring-parser`, `python-backoff` | `python` only |

The current official Arch snapshot provides Python `3.14.7-1`, NumPy
`2.5.2-1`, OpenAI `2.53.0-1`, Pydantic `2.13.4-1`, Tenacity `9.2.0-1`,
typing-extensions `4.16.0-1`, gRPC `1.83.0-1`, protobuf `35.1-1`, HTTPX
`0.28.1-7`, H2 `4.4.1-1`, and urllib3 `2.7.0-1`. Those values satisfy every
explicit bound above. The public Arch package API is the refresh source for
the [Python](https://archlinux.org/packages/search/json/?name=python),
[NumPy](https://archlinux.org/packages/search/json/?name=python-numpy), and
[OpenAI](https://archlinux.org/packages/search/json/?name=python-openai)
snapshots; this repo should express upstream bounds rather than equality-pin
rolling official packages.

### The `fastapi[standard]` translation

Hayhooks 1.23.0 explicitly depends on `fastapi[standard]`. At the current
official FastAPI `0.141.1`, that extra includes `fastapi-cli[standard]`,
`fastar`, HTTPX, Jinja, multipart, email validation, `uvicorn[standard]`,
Pydantic settings, and Pydantic extra types in
[the exact PyPI metadata](https://pypi.org/pypi/fastapi/0.141.1/json).
Arch's [`python-fastapi`](https://archlinux.org/packages/extra/any/python-fastapi/)
does not make the CLI or `fastar` hard dependencies. AUR has
[`python-fastapi-cli 0.0.32-1`](https://aur.archlinux.org/packages/python-fastapi-cli),
but neither official Arch nor AUR had `python-fastar` on the research date.

The accepted service does not use FastAPI's project-generation/cloud CLI or
`fastar`. The frozen bounded service-only translation adds the standard runtime
pieces the service can exercise—`python-httpx`, `python-jinja`,
`python-email-validator`, `python-python-multipart`, `uvicorn`,
`python-pydantic-extra-types`, `python-httptools`, `python-uvloop`, `python-watchfiles`, and
`python-websockets`—while explicitly excluding `python-fastapi-cli`,
`python-fastar`, and the FastAPI cloud CLI. This is a recorded packaging
divergence, not a claim that Arch's `python-fastapi` satisfies the full PyPI
extra.

### Excluded optional surfaces

The base package set does not include:

- Qdrant Client FastEmbed dependencies, model assets, or enabled local-embedding
  behavior; the upstream guarded integration modules remain in the wheel;
- Hayhooks A2A, MCP, Chainlit, or tracing extras;
- FastAPI project-generation or cloud CLI tooling if the bounded service
  translation is accepted;
- PostHog LangChain, zstd, OpenTelemetry, development, or test extras;
- portalocker Redis or the Windows-only `pywin32` dependency; or
- `haystack-experimental` in the Haystack 3 dependency graph.

No package may replace those omissions with a runtime `pip`, model, frontend,
or dependency download.

## Package manifests and build inputs

These manifests are the implementation boundary. Every Python build uses the
exact sdist above with `python -m build --wheel --no-isolation`, followed by
`python -m installer`; package-specific service assets remain normal pacman
payloads.

| Package | Build backend and `makedepends` | Payload and patch intent |
| --- | --- | --- |
| `python-backoff` | Poetry Core; `python-build`, `python-installer`, `python-poetry-core`, `python-wheel` | Python module and license only. |
| `python-docstring-parser` | Hatchling; `python-build`, `python-hatchling`, `python-installer`, `python-wheel` | Python module and license only. |
| `python-lazy-imports` | legacy setuptools; `python-build`, `python-installer`, `python-setuptools`, `python-wheel` | Python module and license only. |
| `python-fastapi-openai-compat` | Hatchling plus Hatch VCS; `python-build`, `python-hatchling`, `python-hatch-vcs`, `python-installer`, `python-wheel` | Python module and license only. |
| `python-portalocker` | setuptools plus setuptools-scm; `python-build`, `python-installer`, `python-setuptools`, `python-setuptools-scm`, `python-wheel` | Python module, typing data, and BSD license; no Redis or Windows-only dependency. |
| `python-posthog` | setuptools `>=83` plus wheel; `python-build`, `python-installer`, `python-setuptools`, `python-wheel` | Python module and MIT license. No package patch should pretend that the client is harmless when imported by an opt-out consumer; the Haystack caller owns the fail-closed default. |
| `python-haystack-ai` | Hatchling `>=1.8`; `python-build`, `python-hatchling`, `python-installer`, `python-wheel` | Python module and Apache license. Carry a small auditable patch that changes telemetry's unset default from enabled to disabled while preserving explicit opt-in. Do not widen the deserialization allowlist. |
| `python-qdrant-client` | Poetry Core; `python-build`, `python-installer`, `python-poetry-core`, `python-wheel` | Python module and Apache license. Expand HTTPX's HTTP/2 dependency to `python-h2`; retain upstream guarded FastEmbed integration modules but package no FastEmbed dependency or model asset. |
| `python-qdrant-haystack` | Hatchling plus Hatch VCS; `python-build`, `python-hatchling`, `python-hatch-vcs`, `python-installer`, `python-wheel` | Python integration and Apache license. It depends on the client, not on the local Qdrant server package. |
| `hayhooks` | Hatchling plus Hatch VCS; `python-build`, `python-hatchling`, `python-hatch-vcs`, `python-installer`, `python-wheel` | Python application, `/etc/hayhooks/hayhooks.env`, systemd unit, sysusers entry, and tmpfiles entry. Exclude the upstream force-included `hayhooks/dashboard/` tree from the installed wheel. Preserve loopback-only service operation and package-owned startup pipelines. Add an upstream-shaped setting that omits runtime deploy and undeploy routers by default; keep dashboard, A2A, MCP, Chainlit, and tracing disabled; forbid runtime dashboard builds and dependency bootstrap; set Haystack telemetry explicitly off in the service default; retain narrow deserialization policy and access logging that does not record prompts, uploads, or secrets. |

Upstream Haystack currently enables telemetry when
`HAYSTACK_TELEMETRY_ENABLED` is unset
([exact source](https://github.com/deepset-ai/haystack/blob/86e06ee1f0b6a5301a82263bdb01118ebd76af73/haystack/telemetry/_telemetry.py#L191-L193)).
Its default deserialization allowlist is narrow, although `unsafe=True` can
bypass it
([exact source](https://github.com/deepset-ai/haystack/blob/86e06ee1f0b6a5301a82263bdb01118ebd76af73/haystack/core/serialization_security.py#L8-L40)).
Hayhooks keeps that default but unconditionally mounts deploy and undeploy
routers today
([exact source](https://github.com/deepset-ai/hayhooks/blob/80276610cb92eab74d623482f24226a2308ff609/src/hayhooks/server/app.py#L328-L336)).
Those are observed upstream facts; the package behavior in the table is the
accepted downstream intent from #27, not behavior already present in the
unmodified releases.

### Build and installation order

1. `python-backoff`, `python-docstring-parser`, `python-lazy-imports`, and the
   accepted FastAPI-standard providers.
2. `python-posthog`, `python-fastapi-openai-compat`, and `python-portalocker`.
3. `python-haystack-ai` and `python-qdrant-client`.
4. `python-qdrant-haystack`.
5. `hayhooks`.
6. Compose these artifacts with the already selected `qdrant 1.19.0`, retained
   `qdrant-migration 1.18.3`, and `qdrant-web-ui 0.2.16` packages.

All updated or new recipes require regenerated `.SRCINFO`, source
verification, a clean Python 3.14 build, complete archive inspection, and a
fresh import test before the higher G2–G4 gates.

## Retained rollback set

### Exact package bytes presently observed

The following package archives were byte-inspected on 2026-08-18. This is a
local availability observation, not proof that they were built from the source
anchors below, not a statement that they were accepted by #38, and not a
durable retention guarantee. Copying them to a checksum-verified retention
location is a separate authorized action.

| Package archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `python-haystack-ai-2.28.0-1-any.pkg.tar.zst` | 452714 | `2dc00018c2b9a26fac416d1c49fd531257a19601f56de760829da6799fa12031` |
| `hayhooks-1.18.0-1-any.pkg.tar.zst` | 121576 | `968c3df44167712f17659f8ba1896a8da4a9b287090e27f52dd06a484fcb3b27` |
| `python-posthog-7.14.0-1-any.pkg.tar.zst` | 211867 | `039b72cf5bbc9be63ae54f5e9b4243d04f9e4e335d8abb861206ab5802e81eae` |
| `python-haystack-experimental-0.19.0-1-any.pkg.tar.zst` | 71067 | `b95c82c831993bea918c08e576ac66fd4f57795e1cac9ed6fcfaef4110eb48be` |
| `python-backoff-2.2.1-1-any.pkg.tar.zst` | 40090 | `e4ea5547eb9b03e42f568980e34f8af4daf9415de133ee1609b5311cb3b4cf53` |
| `python-docstring-parser-0.18.0-1-any.pkg.tar.zst` | 44841 | `80fb65b1ab3128fc9cfb992480cc8a511a4c978e7a93d465eee536093ca2cdc4` |
| `python-fastapi-openai-compat-1.2.0-1-any.pkg.tar.zst` | 55209 | `8fe8bf0fa6274c7099475adf840af1be0db7dcb645416f57929e5ddc4a222a19` |
| `python-lazy-imports-1.2.0-1-any.pkg.tar.zst` | 42059 | `0a0a797e296e13986134586ded374840fd2129d6218010670e52c684f77a602d` |

These are the last observed published rollback bytes. The newer recipes on the
research base—Haystack AI `2.29.0-1`, Hayhooks `1.19.2-1`, and PostHog
`7.16.2-1`—remain deferred source state and must not be mislabeled as the last
published rollback set.

### Reproducible source anchors

| Rollback component | Exact source | SHA-256 |
| --- | --- | --- |
| Haystack AI 2 | [`haystack_ai-2.28.0.tar.gz`](https://files.pythonhosted.org/packages/4b/1c/0d117fd368718eda2cfbfbbf5b31390e230152cd7bfe703661df5fcd929c/haystack_ai-2.28.0.tar.gz) | `723d8e1ba06b214d5dcba8712d2dd7f9134b949b1d3e91dc92a14af33c893823` |
| Hayhooks | [`hayhooks-1.18.0.tar.gz`](https://files.pythonhosted.org/packages/42/bd/85917f58d106fc1f4272c6d5a3ad03df69e034ac01e63fdd4c83c6d2c077/hayhooks-1.18.0.tar.gz) | `cf2e0f33a793e72fef537a515aea101eb4895f1ecf130c37e6cc296a279a15fd` |
| PostHog | [`posthog-7.14.0.tar.gz`](https://files.pythonhosted.org/packages/c4/0f/0e6578feaf0d4e670bc517b6da09ec147a65421c44e0cd687eba12f08743/posthog-7.14.0.tar.gz) | `3be5e513f07e4ee5119f98b0458cb640739b49cef7c96c3e18b1d65076b18239` |
| Haystack Experimental | [`haystack_experimental-0.19.0.tar.gz`](https://files.pythonhosted.org/packages/71/a3/02eb86716f4856072feb852555f2d23855bb20c993264dcf4e83dfe87a8a/haystack_experimental-0.19.0.tar.gz) | `194f9074f9184a20d2f4efa7b5082dd33118bc886f87937d13e33616cd549067` |

Upstream later published archived `haystack-experimental 0.19.0.post1`, with
sdist SHA-256
`898a6974567655b345d0088900bbb6ac539124faec6e209d37307ee7aa6ec652`.
It was not the source of the retained `0.19.0-1` package and must not silently
replace that rollback anchor. Haystack 3 removes experimental from its runtime
dependency graph; the package can be retired only after migration acceptance
explicitly releases the retained artifact.

The composed rollback boundary also inherits the exact Qdrant anchors from
[`#28`](https://github.com/nisavid/arch-pkgs/issues/28#issuecomment-5259788912):
the old `1.17.1` package and untouched state, the validated versioned
`qdrant-migration 1.18.3` artifact and matching recovery state, and the final
`qdrant 1.19.0` plus `qdrant-web-ui 0.2.16` artifacts. An older binary must
never open storage migrated by a newer minor.

## Evidence still required before publication

The inventory above freezes what must be built; it does not satisfy the gates.

- **G0:** re-fetch every source, verify every digest and Git object type,
  regenerate `.SRCINFO`, and bind the
  expected pipeline manifest and rollback-retention manifest.
- **G1:** build every archive in a clean Python 3.14 Arch environment, inspect
  metadata, payloads, ownership, modes, licenses, service assets, and dependency
  fields, and prove there is no runtime package, model, or frontend bootstrap.
- **G2:** prove offline imports and deterministic sync/async Haystack behavior;
  serialization lifecycle; rejection of unapproved deserialization; startup of
  only the expected YAML and wrapper pipelines; disabled runtime mutation and
  dashboard build; loopback binding; telemetry off when unset; explicit opt-in;
  and request logs without prompt, upload, or secret values.
- **G3/G4:** use the already accepted disposable Qdrant route and a real
  `1.19.0` server over HTTP and gRPC. Prove explicit document IDs,
  dense/sparse/hybrid retrieval, duplicate policy, restart persistence,
  snapshot/restore to a separate target, post-restore equivalence, versioned
  collection and alias cutover where schema or IDs change, and a complete
  Haystack 2-to-3 rollback drill. Never use `recreate_index=True` on retained
  data.

Any failed gate leaves the production lane deferred and preserves every
rollback anchor.
