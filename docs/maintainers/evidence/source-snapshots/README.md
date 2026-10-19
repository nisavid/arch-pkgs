# Historical source snapshots

These non-executable text files retain the exact source bytes bound by existing
evidence after their maintained counterparts changed. Do not install them or
copy them back into the active source tree. Never execute the former cutover
helper: it uses unauthenticated loopback HTTP. The sole execution exception is
the archived Open WebUI v1 inspector, after verifying its bound SHA-256, for
read-only reproduction of a historical receipt as documented in
[Package Verification](../../../../packages/open-webui/README.md#package-verification).
It reads the supplied archive without extracting or executing its payload and
writes only the requested receipt. It must not validate a current candidate.

The files were recovered without modification from repository commit
`5f21b1cb3870867401721acddeef7e919adfe656`, the parent of the authenticated
service transport change. That is their recovery source, not a new acceptance
commit. The source SHA-256 values and supporting provider list match the
bindings in the original, unchanged evidence records.
The snapshot paths retain the original repository-relative paths below that
commit directory. Executable source names append `.txt`; the inspector's
supporting text manifest retains its name for relative lookup. Every file has
mode `0644`.

| Original path | Size, bytes | SHA-256 | Existing binding |
| --- | ---: | --- | --- |
| `tools/qdrant_production_cutover.zsh` | 41797 | `78ab3ca88ec7e9936b6bb01d04c580fa249199659444f7eb326d206090ff564d` | [`qdrant-1.19.1-1/acceptance.json`](../qdrant-1.19.1-1/acceptance.json), `repository_source.frozen_files` |
| `tests/test_qdrant_evidence.py` | 33331 | `e206280899859b8459028ad4714cd5725eaff9d215f94c822c927f0615b87a86` | The same frozen-file set; the historical test itself was source-bound |
| `packages/open-webui/inspect-open-webui-package.py` | 27592 | `a49f63893fd0dd7d07b3215b7175cf86ee3cf815fde016f7fa6e67554e235cc5` | [`open-webui-offline-package-build-2026-08-19.json`](../open-webui-offline-package-build-2026-08-19.json), `inspection_receipt.verifier_sha256` |
| `packages/open-webui/open-webui-system-providers.txt` | 230 | `fdf91cf245d0f5050229b5ea8ef4067c997f79f012e06a16b18e740981b395a3` | The inspector's relative input; its exact 21-name list matches the original inspection receipt's `payload.server_provider_boundary.providers_absent` |

Reconstruct any one snapshot from a clone containing the recovery commit with
`git show 5f21b1cb3870867401721acddeef7e919adfe656:<original-path>` and compare
its bytes and digest with the retained `.txt` file. No Git history is needed to
validate the snapshot against the original record, so shallow CI checkouts can
still verify the historical evidence.

The historical tests compare these explicit snapshots to the original digest
bindings. They continue checking every other frozen source and the complete
Qdrant package inventory against the maintained checkout. There is no general
fallback from changed source to historical source. Tests for the current TLS
clients and package inspector run against their maintained implementations.

## Acceptance boundary

Passing the historical-evidence tests establishes internal consistency of the
dated records. It does not establish acceptance of replacement source, new
package archives, or a deployment. The old Open WebUI inspection receipt covers
`0.11.0-3`; the household candidate-set binding covers `0.11.4-2`. Neither covers
the unbuilt `0.11.4-3` candidate or its newly required TLS helper. The Qdrant
G0-G3 records retain their exact package identities, but their source binding
does not cover the maintained TLS-enabled cutover helper.

Before promotion, the current Open WebUI candidate still requires clean Arch
source verification, a build, inspection with the current inspector, an exact
candidate-set binding, and the complete TLS-enabled integrated provider,
restore, and rollback trial. The current Qdrant cutover helper must participate
in that acceptance route. The catalog remains deferred and publication-
ineligible. Source review and CI completion do not satisfy those artifact or
deployment gates.
