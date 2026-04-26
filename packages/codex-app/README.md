# codex-app

`codex-app` is maintained in
[`../codex-app-linux`](../../../codex-app-linux/). This repo does not rebuild it
through a second `PKGBUILD`; it ingests the pacman package produced by that
source repo.

Use:

```bash
tools/ingest_codex_app.zsh
```

## Update Policy

The ingestion policy is:

1. If `upstream/codex-app-linux` is present and its `dist/` directory
   contains a `codex-app-*.pkg.tar.*` package built in the past 24 hours, ingest
   that package.
2. If `upstream/codex-app-linux` is present but has no package built in
   the past 24 hours, run `make pacman` in that repo, then ingest the newest
   package it produced.
3. If `upstream/codex-app-linux` is absent, clone
   `https://github.com/nisavid/codex-app-linux.git` there, run `make pacman`,
   then ingest the newest package it produced.

For this workspace, `upstream/codex-app-linux` is a local symlink to the sibling
`../codex-app-linux` checkout. The contents of `upstream/` are ignored so source
checkouts and symlinks stay local.
