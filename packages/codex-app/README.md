# codex-app

`codex-app` packages
[Codex App for Linux](https://github.com/nisavid/codex-app-linux), an unofficial
Linux adaptation of the OpenAI Codex desktop app. The source repo converts the
upstream macOS `Codex.dmg` into a Linux Electron app and builds native package
artifacts.

This repo does not rebuild `codex-app` through a second `PKGBUILD`; it ingests
the pacman package produced by
[nisavid/codex-app-linux](https://github.com/nisavid/codex-app-linux).

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
   [nisavid/codex-app-linux](https://github.com/nisavid/codex-app-linux) there,
   run `make pacman`, then ingest the newest package it produced.

For this workspace, `upstream/codex-app-linux` may be a local symlink to a
checkout of [nisavid/codex-app-linux](https://github.com/nisavid/codex-app-linux).
The contents of `upstream/` are ignored so source checkouts and symlinks stay
local.
