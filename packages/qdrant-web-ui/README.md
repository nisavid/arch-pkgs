# qdrant-web-ui

Static Qdrant dashboard assets packaged from the upstream release archive. The
package has no runtime dependencies, install hook, Node runtime, or networked
bootstrap. Qdrant serves the read-only files from
`/usr/share/qdrant/web-ui`.

## Maintenance Baseline

- `authoritative_reference`: upstream Qdrant Web UI
  [`v0.2.18`](https://github.com/qdrant/qdrant-web-ui/releases/tag/v0.2.18)
  tagged source and the release workflow's official `dist-qdrant.zip` binary
  asset; no matching Arch, CachyOS, or AUR static-asset package exists.
- `advisory_references`: upstream's exact-tag
  [`publish-dist-packages.yml`](https://github.com/qdrant/qdrant-web-ui/blob/6f8536529934672a0d2631cfaa0d0779967922bc/.github/workflows/publish-dist-packages.yml),
  the AUR [`qdrant`](https://aur.archlinux.org/packages/qdrant) server recipe,
  and Qdrant's
  [Web UI integration](https://github.com/qdrant/qdrant/blob/v1.19.1/src/actix/web_ui.rs).
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
| Version | `0.2.18` |
| Annotated tag object | `c904d06ed0f5983ab412ddf558b3e47ceb166689` |
| Resolved commit | `6f8536529934672a0d2631cfaa0d0779967922bc` |
| `dist-qdrant.zip` SHA-256 | `fdce24c04ec1627d2369cb8fe610ee06ad9236f82aad214aa7f294ac37372859` |
| Tagged source SHA-256 | `3fa78da022fdee695469c3a35fb41124955250a1b1e4f066831229bbea701874` |
| Exact-tag `LICENSE` SHA-256 | `210b508429e913d9de5301f90508bc2cbf5b2281de5b45e607c04d58f0f3bd8f` |

GitHub resolves the annotated tag to the accepted, GitHub-verified commit, but
the tag itself is unsigned. The release asset digest matches the digest GitHub
publishes for it, and the tagged source archive's contents match the commit
tree. The pinned identities and digests are therefore the acceptance boundary.

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
python3 verify-package.py qdrant-web-ui-0.2.18-1-any.pkg.tar.zst
bsdtar -tvf qdrant-web-ui-0.2.18-1-any.pkg.tar.zst
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
