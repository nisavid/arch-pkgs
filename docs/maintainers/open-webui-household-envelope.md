# Disposable Open WebUI household-service envelope

## Disposition

Incomplete. The run establishes useful behavior and provisional measurements,
but it does not define production limits, make the package publication
eligible, or make the service deployable. Issue
[#68](https://github.com/nisavid/arch-pkgs/issues/68) remains open.

## Scope and authority

This run measures the fresh native-RAG boundary accepted in
[#66](https://github.com/nisavid/arch-pkgs/issues/66#issuecomment-5327054348)
and
[#67](https://github.com/nisavid/arch-pkgs/issues/67#issuecomment-5332310242).
It does not import or upgrade the former Open WebUI database, configuration,
secret, uploads, cache, or Chroma state. Here, migration means fresh Alembic
initialization and a future versioned vector-generation rebuild, cutover, and
rollback.

## Exact measured subject

The disposable tuple used Open WebUI 0.11.0 at commit `f9590b8`, the accepted
Qdrant 1.19.0 package archive, Caddy 2.11.4, Valkey 9.1.0, and five precreated
2,560-dimensional cosine collections. Open WebUI used one Unix socket behind
one synthetic HTTPS origin and one collection-scoped `prw` Qdrant identity.

The embedding artifact was `zembed-1-Q4_K_M.gguf`, size `2497280960`, SHA-256
`3098f7963ca0563e8b39a55ee09a53697e57e49be5b9082892739bf24e075836`.
Its GGUF pooling value is `3`; llama.cpp was therefore run explicitly with
last-token pooling. The reranker artifact was `zerank-2.Q8_0.gguf`, size
`4280405664`, SHA-256
`7b9ba05a0509151c911582a4d62b14003f6a4fafa0e7ccdf572c7598cde1c100`.

The provider was a measurement-only sidecar around two loopback CPU-only
llama.cpp processes. The observed runtime was `llama.cpp-hip-gfx1151`
`b9442-1`, reported build `459 (baffb2e)`. Its executable SHA-256 was
`9d3b6e271548ec85a67951c86a48f131e306d152c22e79266d050a240a9f2f78`;
the server implementation SHA-256 was
`6c93a4a9bfaa11065d89760142bcf8ce5761147ebe0c65221e09a4ad9e99215b`.
The complete dynamic runtime closure was not bound. The sidecar exercised the
zembed framing and zerank selected `Yes`-token scoring contract, but it was
not the accepted integrated patched Lemonade service. Open WebUI ran from
pinned upstream artifacts rather than an accepted package candidate.

## Measurement method

The run used a fresh SQLite database, a dedicated persistent Valkey instance,
synthetic users and documents, five fresh Qdrant collections, and no former
application state. It exercised authentication, sharing, retrieval, citation,
upload boundaries, WebSocket and SSE transport, a 256 KiB response, provider
failures, quiesced backup, and a separately rooted restore.

Every provisionally recorded embedding result uses last-token pooling.
An incompatible exploratory pooling configuration and all results derived from
it were excluded. Query latency records are aggregate-only because the raw
per-request samples were not retained in a public, digest-bound form.

The temporary private run material remains available for current review, but
no public digest-bound execution recipe, raw sample set, backup manifest, or
per-obligation receipt was retained. The figures below are therefore
provisional observations rather than independently reproducible acceptance
evidence. Obligations without a corresponding durable public receipt are
marked inconclusive in the machine-readable record.

The checked-in plan now owns the required input names, sizes, and SHA-256
identities. This run predates that gate and did not execute through the plan,
so the stronger plan contract does not retroactively establish provenance for
these observations. The plan-only tool deliberately has no transition to a
`measured` disposition; that transition must arrive with an executable verifier
that checks real, durable receipts and integrated-provider identities.

## Observed envelope

| Surface | Provisional observation |
| --- | --- |
| Restart-like startup | 5 samples; median 15.126 s; p95 and max 17.309 s |
| Retrieval, concurrency 1 | 30 requests; median 128 ms; p95 138 ms; 6.72 requests/s |
| Retrieval, concurrency 3 | 30 requests; median 268 ms; p95 287 ms; 10.93 requests/s |
| Sustained retrieval, concurrency 3 | 300 requests; median 263 ms; p95 277 ms; 11.36 requests/s |
| Cited chat | 141 ms nonstreaming; 153 ms streaming; one exact citation |
| 256 KiB response | 17 ms total nonstreaming; 13 ms streaming; exact reconstruction |
| Authenticated Socket.IO | 4.76 ms upgrade; 6.52 ms authenticated round trip |
| 250 MiB upload | accepted in 1.04 s; approximately 261 MiB RSS increase |
| 250 MiB plus one byte | rejected with HTTP 413 in 660 ms |
| Five Qdrant snapshots | 2,820,608 bytes total; 50–58 ms per collection |
| Quiesced backup | 3,489,175 bytes across 20 files |
| One restore probe | 120–129 ms per Qdrant collection; exact cited retrieval in 241 ms |

The summed process RSS observation was about 11.18 GiB. It is not a production
limit: summed RSS can double-count shared pages, the run lacked a dedicated
cgroup, and unrelated host activity contaminated CPU sampling.

## Behavioral findings

- Exact last-token zembed canaries produced finite, unit-normalized 2,560-value
  vectors. Relevant cosine was `0.679498783`, unrelated cosine was
  `0.334305462`, for a `0.345193321` margin.
- A 250 MiB file is accepted and a file one byte larger is rejected. The
  configured 25-file count is only a frontend composition guard; raw API
  callers are not limited, and a persisted-chat edge can upload before submit
  rejects the 26th attachment.
- When embedding failed, the upload became visibly failed and nonqueryable,
  created no stale vector, and succeeded through the normal retry path after
  the provider recovered.
- When reranking failed, ordinary chat remained available, but native RAG also
  remained queryable and returned a citation with a null rerank score. This
  violates the accepted fail-closed RAG contract.
- The quiesced SQLite, Valkey data, uploads, Qdrant snapshots, and TLS
  continuity restored into a separate tuple. The provider key and Qdrant
  runtime token were present in the backup, but the stable Open WebUI keys and
  Valkey credential/configuration were not. The restore reused those external
  fixture inputs, so complete credential continuity was not proved. The
  restored application reached readiness over a new Unix socket and returned
  the exact cited fact.
- An authenticated session minted before backup remained valid after restore.
  The external monotonic session-epoch helper is therefore required for the
  accepted restore contract.

## Failed and incomplete gates

The run is not closure-complete because:

- the exact integrated patched Lemonade subject was absent;
- the five startup samples were restart-like, not five proven fresh starts;
- cgroup memory, isolated CPU, accelerated-provider, cache, corpus-growth, and
  compaction measurements are absent;
- heavy indexing, versioned generation rebuild, five restores, and five
  rollbacks remain below their declared sample floors;
- kernel-enforced no-egress evidence is absent;
- the complete llama.cpp dynamic runtime closure is not bound;
- public digest-bound execution receipts, raw samples, and per-obligation
  proofs are absent;
- measured finalization remains disabled until an executable verifier owns
  those durable inputs;
- the restore reused external fixture secrets and configuration rather than
  proving the complete credential tuple;
- reranker failure does not isolate RAG; and
- restored sessions are not invalidated.

## Production-boundary implications

Do not derive a production memory, CPU, startup, readiness, upload-count, or
storage-growth limit from this run. The package candidate now carries a
fail-closed semantic RAG gate and a root-owned, forward-only session-epoch
authority outside the restored application tuple, but neither remediation was
part of this measured subject. The production provider must also bind the exact
accepted Lemonade and patched llama.cpp artifacts before repeated measurements
can become candidate-acceptance evidence.

A later pkgrel-3 package checkpoint materialized both graphs as immutable
makepkg sources and passed a no-egress build and payload inspection. See
[`open-webui-offline-package-build-2026-08-19.md`](open-webui-offline-package-build-2026-08-19.md).
That later result does not retroactively change this run's unpackaged measured
subject or close the integrated provider and recovery gates.

## Durable evidence

The machine-readable record is
[`evidence/open-webui-household-envelope-2026-08-18.json`](evidence/open-webui-household-envelope-2026-08-18.json),
SHA-256
`6fd64b787e25d6dfba05151d79d9c1622ce57a229a6831c5ada1e5c4e6819652`.
It binds the measurement contract, fixture sources, exact artifact identities,
observations, obligation dispositions, limitations, cleanup, and public-safety
claims.

## Remaining work

1. Compose the built package set with the exact accepted patched Lemonade and
   llama.cpp provider in a dedicated cgroup with kernel-enforced no egress.
2. Prove the packaged fail-closed RAG gate and external session epoch across
   reranker failure and repeated whole-tuple restores.
3. Retain public-safe raw samples and meet every declared fresh-start, heavy
   indexing, generation-rebuild, restore, and rollback floor.
4. Measure cache behavior, cgroup memory, isolated CPU, corpus-size growth,
   compaction, accelerated-provider behavior, and the future v1-to-v2
   generation cutover.

## Cleanup and privacy

Runtime quiescence is complete: all fixture-owned processes, listeners, and
Unix socket files were removed. Full disposable-data cleanup is not complete;
the synthetic temporary evidence root remains retained for review. No live
application state or production data was copied, no live service was changed,
and the durable evidence contains no private paths, host identities, addresses,
credentials, headers, certificates, keys, or raw logs.
