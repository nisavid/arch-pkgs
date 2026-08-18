# qdrant-web-ui

Static Qdrant dashboard assets packaged from the upstream release archive. The
package has no runtime dependencies, install hook, Node runtime, or networked
bootstrap. Qdrant serves the read-only files from
`/usr/share/qdrant/web-ui`.

## Maintenance Baseline

- `authoritative_reference`: upstream Qdrant Web UI
  [`v0.2.16`](https://github.com/qdrant/qdrant-web-ui/releases/tag/v0.2.16)
  tagged source and the release workflow's official `dist-qdrant.zip` binary
  asset; no matching Arch, CachyOS, or AUR static-asset package exists.
- `advisory_references`: upstream's exact-tag
  [`publish-dist-packages.yml`](https://github.com/qdrant/qdrant-web-ui/blob/d3f7a1174933ab637d9711ea45456d32b878b50e/.github/workflows/publish-dist-packages.yml),
  the AUR [`qdrant`](https://aur.archlinux.org/packages/qdrant) server recipe,
  and Qdrant's
  [Web UI integration](https://github.com/qdrant/qdrant/blob/v1.19.0/src/actix/web_ui.rs).
- `divergence_notes`: install the official prebuilt dashboard instead of
  rebuilding it with Node; package it separately as architecture-independent,
  root-owned read-only data; replace automatic external Web UI information and
  sample-dataset paths with inert package-owned resources while preserving
  documentation links, Monaco workers, graph-layout WASM, and the upstream SPDX
  SBOM.
- `update_notes`: verify the tag object, resolved commit, release-asset digest,
  tagged-source digest, and exact license digest; update the fail-closed string
  replacements; regenerate `.SRCINFO`; run `makepkg --verifysource` and a clean
  build; then run `verify-package.py` and inspect the complete archive before
  testing Qdrant's dashboard route and response headers.

## Pinned Identity

| Input | Accepted identity |
| --- | --- |
| Version | `0.2.16` |
| Annotated tag object | `018e83a869a3d2b831e92664e8d33f51ec7981b1` |
| Resolved commit | `d3f7a1174933ab637d9711ea45456d32b878b50e` |
| `dist-qdrant.zip` SHA-256 | `4446f0cea024078011c78cd24a592c9b563656d15205818563fa6b22d394dd29` |
| Tagged source SHA-256 | `be85d9cffc5d5ad8122c4fe332cd6731cddcd508a61d77ee918626fc4d977577` |
| Exact-tag `LICENSE` SHA-256 | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |

GitHub resolves the annotated tag to the accepted commit but reports the tag's
SSH signature as unverified because of its tagger email. The pinned identities
and independently reproduced digests are therefore the acceptance boundary.

## Runtime Data Policy

`patch-runtime-urls.py` fails unless each accepted upstream string occurs
exactly once. It changes only the main compiled application bundle:

- the external Web UI information feed becomes the package-owned
  `/dashboard/web-ui-info.json`, whose empty object disables banners and update
  notices;
- the external sample manifest becomes `/dashboard/datasets.json`, whose empty
  array disables the sample list;
- the dashboard's optional cloud metadata request resolves locally at
  `/dashboard/cloud/data.json` to JSON `null`, preserving non-cloud behavior
  without a failed request or a truthy empty cloud object;
- snapshot download and tutorial sample URLs use an invalid `disabled:` scheme,
  consistent with the maintained server's disabled URL snapshot recovery.

Ordinary user-selected documentation links remain unchanged. Qdrant's package
owns loopback binding, authentication, static-content routing, and response
headers; this package only provides assets.

## Build And Inspect

```bash
makepkg --verifysource
makepkg -f
python3 verify-package.py qdrant-web-ui-0.2.16-1-any.pkg.tar.zst
bsdtar -tvf qdrant-web-ui-0.2.16-1-any.pkg.tar.zst
```

The verifier checks package metadata, exact license bytes, asset placement,
numeric UID/GID 0 ownership, read-only modes, the absence of runtime dependencies and an
install hook, the SPDX SBOM, Monaco workers, graph-layout WASM, and the absence
of the automatic external runtime paths. Archive names must be canonical and
unique after directory suffixes are normalized, so a file and directory cannot
claim the same installed path.

The metadata gate requires regular `.PKGINFO`, `.BUILDINFO`, and `.MTREE`
members, one exact package identity, and only the reviewed static-package
fields. Duplicate identities and transaction-affecting dependency, conflict,
provide, replace, install, backup, or group fields are rejected.
