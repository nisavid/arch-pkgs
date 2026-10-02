# Open WebUI household candidate set

The candidate manifest
[`evidence/open-webui-household-candidate-set-2026-10-02.json`](evidence/open-webui-household-candidate-set-2026-10-02.json)
names the exact archives bound for the household acceptance trial. It fulfils
Remaining scope 2-4 of
[Build the Open WebUI household candidate set from main](https://github.com/nisavid/arch-pkgs/issues/88).

Only these bytes may enter
[Acceptance-deploy the Open WebUI household candidate set](https://github.com/nisavid/arch-pkgs/issues/89),
and only the `role: deployed` archives are installed in the trial. The
`publication-identity-only` archives are bound but never installed on the host.
#89 and
[Promote or defer the Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/90)
carry each archive's source commit and the external-input records from this
file. Binding a candidate accepts nothing: every household-stack catalog row
stays `deferred` until #90 decides it.

## What the manifest binds

| Package | Version | Role | Source commit | Basis | Evidence |
| --- | --- | --- | --- | --- | --- |
| `open-webui` | 0.11.4-2 | deployed | `2059571` | recorded | [#88 candidate build](https://github.com/nisavid/arch-pkgs/issues/88#issuecomment-5957006596) |
| `python-rapidocr` | 3.9.2-1 | deployed | `f25fd53` | recorded | #88 reference-build table; [adoption](https://github.com/nisavid/arch-pkgs/issues/88#issuecomment-5789540457) |
| `qdrant` | 1.19.1-1 | deployed | `41208bd` | recorded | [cutover identities](qdrant-production-cutover.md#candidate-identities); [1.19.1 G0-G1](evidence/qdrant-1.19.1-1/g0-g1.json) |
| `qdrant-migration` | 1.18.3-1 | deployed | `51a55e7` | recorded | [cutover identities](qdrant-production-cutover.md#candidate-identities); [1.19.1 G0-G1](evidence/qdrant-1.19.1-1/g0-g1.json); [rebind rebuild](evidence/qdrant-1.19.0-1-rebind-2026-09-22/g0-g1-rebuild.json) |
| `qdrant-web-ui` | 0.2.18-1 | deployed | `41208bd` | recorded | [cutover identities](qdrant-production-cutover.md#candidate-identities); [1.19.1 G0-G1](evidence/qdrant-1.19.1-1/g0-g1.json) |
| `python-faster-whisper` | 1.2.1-1 | deployed | `9b41578` | derived | [speech G0-G2](evidence/speech-providers-4.8.2-1.2.1/) |
| `ctranslate2` | 4.8.2-1 | publication identity only | `0b4b327` | recorded | [speech G0-G2](evidence/speech-providers-4.8.2-1.2.1/) |
| `python-ctranslate2` | 4.8.2-1 | publication identity only | `0b4b327` | recorded | [speech G0-G2](evidence/speech-providers-4.8.2-1.2.1/) |

The manifest holds the full sizes, SHA-256 digests, and 40-character commits.
Each size and digest equals its cited source. #88's table gives the
`python-rapidocr` size, and #88's speech table repeats the speech evidence.
Every bound archive was re-hashed in the candidate store on 2026-10-02, and
each `.BUILDINFO` `pkgbuild_sha256sum` matched the `PKGBUILD` at the record's
source commit.

`open-webui` 0.11.4-2 records its two offline closures as build inputs. The
asset names, releases, and digests are the ones its `PKGBUILD` pins at the
source commit:

- npm: `open-webui-0.11.4-offline-closures-v1`, SHA-256 `617abc7d…9438`.
- Python: `open-webui-0.11.4-python-closure-185b40a6`, SHA-256
  `65b62d21…e704`. This closure selects AnyIO 4.14.2, the fix for
  [open-webui: decide the pinned AnyIO advisory disposition](https://github.com/nisavid/arch-pkgs/issues/118).
  Its identity comes from
  [#118's source-correction comment](https://github.com/nisavid/arch-pkgs/issues/118#issuecomment-5955992404).

`ctranslate2` and `python-ctranslate2` are bound for publication only. The
host keeps its gfx1151 provider and does not install them; see
[External inputs](#external-inputs).

## Schema

The manifest uses its own schema, `arch-pkgs-candidate-set/v1`. Its archive
record is the accepted-only stager's record: each `archives[].archive` object is
an `arch-pkgs-accepted-publication/v1` archive record, as documented under
[Accepted-Only Staging](../usage/local-repo.md#accepted-only-staging). Two rules
are stricter than the stager's: `source_commit` is required, and `promotion` is
absent. A later accepted manifest can therefore copy the `archive` objects
without change. The test feeds them through `tools/stage_accepted_repo.py`'s
validator.

The schema does not reuse the stager's manifest as a whole. A candidate set has
no repository, no publication dispositions, and no catalog commit, and its
non-stager keys sit beside the `archive` object, never inside it:

- `source_commit_basis`: `recorded-build-commit` or `derived-tree-equal`; see
  [Per-archive source commit](#per-archive-source-commit).
- `role`: `deployed`, or `publication-identity-only` for an archive that is
  bound but not installed on the host.
- `package_directory` and `package_tree`: the recipe directory and its Git tree
  id at `source_commit`.
- `main_tree_delta`: the package-relative paths that differ between that tree
  and the same directory at `adoption_main_commit`.
- `evidence`: the primary sources for the record's values.
- `build_inputs` (`open-webui` only): the pinned offline closures.

At the top level, `adoption_main_commit` is the merged `main` commit that the
tree comparison used. It is not a source commit.

## Per-archive source commit

Every archive carries its own `source_commit`, and `source_commit_basis` says
where it comes from:

- **`recorded-build-commit`:** a build or evidence record names the commit
  whose `package_directory` tree the archive was built from.
- **`derived-tree-equal`:** no record names a committed build tree. The
  `source_commit` is then the earliest commit on `main` whose
  `package_directory` tree equals the built tree. The built tree is fixed by the
  archive's `.BUILDINFO` `pkgbuild_sha256sum` and the evidence's recipe digests.

The records:

- **`open-webui`:** built from merged `main` at `2059571`, so its tree is the
  merged tree by construction.
- **`python-rapidocr`:** #88 records the build at `f25fd53`, a pre-merge commit
  of [#87](https://github.com/nisavid/arch-pkgs/pull/87).
- **`qdrant` and `qdrant-web-ui`:** the 1.19.1 G0-G1 record names `41208bd` as
  the `recipe_commit` of both lanes. Recomputing its `package_input_manifest`
  digest from `41208bd`'s committed trees reproduces both recorded values.
- **`qdrant-migration`:** not rebuilt for 1.19.1. The original final3 build was
  an uncommitted review candidate on `6f0dc14` (`qdrant-1.19.0-1/g0-g1.json`).
  The retained archive comes from the 2026-09-22 rebind rebuild, whose record
  names `51a55e7` as its recipe base. That rebuild is byte-identical to final3,
  and `51a55e7` holds the recorded `PKGBUILD` and `.SRCINFO` digests.
- **`ctranslate2` and `python-ctranslate2`:** clean-built from `0b4b327`, the
  speech evidence's `source_commit`.
- **`python-faster-whisper`:** derived. The speech evidence records `0b4b327`
  as its source commit and `51a55e7` as that commit's base. It records no
  build commit for the reused faster-whisper bytes, which come from the
  superseded 4.8.1 candidate run; that run also built a ctranslate2 4.8.1
  recipe that was never committed. The faster-whisper `PKGBUILD` and
  `.SRCINFO` match the archive and the evidence. Tree `0746eed` holds exactly
  those files, and `main` carried that tree from `9b41578` (2026-08-17) until
  the README-only `e0d5b2b` (2026-09-23), a window that covers the 2026-09-22
  build. `9b41578` is the earliest such commit.

### Which ref keeps each commit reachable

`2059571`, `51a55e7`, and `9b41578` are on `main`. The other three are not:

- `f25fd53` is reachable through `refs/pull/87/head`.
- `41208bd` is reachable through the tag `open-webui-0.11.4-offline-closures-v1`.
- `0b4b327` is reachable from no ref. GitHub serves the commit today, but no
  clone fetches it and it may be garbage-collected. For the two CTranslate2
  archives, the durable binding is the in-repo evidence: the `PKGBUILD` and
  `.SRCINFO` digests in
  [`g0-g2.json`](evidence/speech-providers-4.8.2-1.2.1/g0-g2.json), which
  equal the blobs on `main`, together with the archive bytes and each
  `.BUILDINFO` `pkgbuild_sha256sum`.

## Adoption

#88's tree-equality rule governs the two Open WebUI builds. It admits an
archive only if its package tree equals the merged tree of that package on
`main`. Against `main` at `2059571`, `open-webui` and `python-rapidocr` are both
tree-equal, and their `main_tree_delta` is empty.

The Qdrant trio and the speech archives are not adopted under that rule. They
are bound from their accepted evidence, under #88's Inputs and Remaining
scope 2. Their `main_tree_delta` of `README.md` is informational: `makepkg`
does not read it, and no `PKGBUILD` references it.

## Archives stay outside git

The archives stay in the maintainer candidate store, outside git. The manifest
records only file names, sizes, digests, commits, and each archive's `source`,
a store subdirectory relative to the store root. The store holds same-named
archives with different bytes; for example, it keeps two
`python-rapidocr-3.9.2-1` archives. The digest selects the bytes, and `source`
selects the directory. Do not add store paths or archives to the repository.

## External inputs

`external_inputs` records the two foreign providers that #88 names. They are
evidence, not gates. They are not arch-pkgs candidate identities, and the
accepted-only publication manifest never includes them. The list is not the
host's full provider set: the trial also runs on other host-provided packages
that this file does not record.

- **`python-ctranslate2-gfx1151` 4.7.2-1:** the host speech provider from
  arch-strix-halo-pkgs. It provides and conflicts with `python-ctranslate2`.
  The version comes from that repository's public `PKGBUILD` at `ac51a22`
  (2026-10-02) and the speech evidence's
  [host provider seam](evidence/speech-providers-4.8.2-1.2.1/README.md#host-provider-seam).
  The seam notes that arch-strix-halo-pkgs plans a CTranslate2 4.8.2 rebuild.
  Because this record is evidence and not a gate, a different installed
  version at trial time is an observation for #89, not a candidate change.
- **`python-sentence-transformers` 5.7.0-1:** the AUR package, recorded by
  the owner as a knowingly foreign provider of record in the
  [amendment on #63](https://github.com/nisavid/arch-pkgs/issues/63#issuecomment-5789382398).
  Open WebUI only imports it.

## Catalog change

The same change retires the arch-pkgs `python-sentence-transformers` row in
[`packages/README.md`](../../packages/README.md), as the #63 amendment
requires. The row is not publication eligible.
[Release retained rollback anchors and clean target-local state](https://github.com/nisavid/arch-pkgs/issues/62)
owns its preservation-aware source and artifact cleanup. The host's AUR
package is not a cleanup target.

The `open-webui` row now points at this candidate set and says not to rebuild
0.11.4-2.

## Checks

`tests/test_open_webui_household_candidate_set.py` checks:

- the manifest's shape, the `source_commit_basis` of each record, and the
  literal `open-webui` and `python-rapidocr` records;
- the stager's archive-record validation;
- the Qdrant and speech records against their in-repo evidence;
- the external-input records;
- the catalog rows.

The catalog assertions record today's state on purpose. #90's promotion PR
changes the household rows, and #62's cleanup changes or removes the
`python-sentence-transformers` row, so each of those changes must also update
this test.

The Git checks run only where the commit objects exist. They cover each
`package_tree`, each `main_tree_delta`, the derived commit, and the
`PKGBUILD` pins of the open-webui build inputs. CI's depth-1 checkout skips
them all. A plain full clone skips the `python-rapidocr` and CTranslate2
records, unless `refs/pull/87/head` and `0b4b327` are fetched. Run the test in
a maintainer clone that has those objects before changing the manifest.
