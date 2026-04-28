# codex-app

`codex-app` is the pacman package for
[Codex App for Linux](https://github.com/nisavid/codex-app-linux), an unofficial
Linux adaptation of the OpenAI Codex desktop app.

Use this package when you want the Codex desktop app installed and upgraded
through the local `nisavid` pacman repo.

## How This Package Is Produced

This repo does not rebuild `codex-app` through a second `PKGBUILD`; it ingests
the pacman package produced by
[nisavid/codex-app-linux](https://github.com/nisavid/codex-app-linux). That
source repo converts the upstream macOS `Codex.dmg` into a Linux Electron app
and builds native package artifacts.

Run the ingest helper from this repo's root:

```bash
tools/ingest_codex_app.zsh
```

The helper stages the package in `repo/x86_64/`. Publish the local repo and
install `codex-app` with pacman using the workflow in
[`docs/usage/local-repo.md`](../../docs/usage/local-repo.md).

After the local repo is published and enabled:

```bash
sudo pacman -S codex-app
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
