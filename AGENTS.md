# AGENTS.md

This repo is a personal Arch packaging workspace. Treat it as a packaging and policy repo first.

Your job is not to make a package build once. Your job is to leave behind package files, service assets, and documentation that a fresh agent can inspect and update without chat history.

## Repo shape

- Keep packages under `packages/<name>/`.
- Keep each package self-contained with the files needed to build it: `PKGBUILD`, `.SRCINFO`, patches, service files, config files, and short package-local notes when helpful.
- Prefer repository-relative documentation over chat-only explanations.

## Rules

- Never commit private filesystem paths, private hostnames, private network addresses, machine-specific IDs, tokens, or keys.
- Prefer stable packaged defaults over host-specific runtime state.
- When packaging services, install service assets and defaults, but do not commit local secrets or environment overrides.
- When adding or updating packages, regenerate `.SRCINFO`.
- Validate package changes with fresh evidence before claiming success.
- Use Conventional Commits for all commits.

## Package maintenance expectations

- Review upstream release notes and installation docs before changing package behavior.
- Follow Arch naming and layout conventions where practical, especially for Python packages and `systemd` assets.
- Keep one-off installation guidance simple for now: build and install directly from the package directory with `makepkg -si`.
- When a package change also changes install or service behavior, document the operator command needed to use it.

## Verification

Before claiming a package update is complete, run the relevant checks for the changed package:

- `makepkg --verifysource`
- `makepkg -f` or `makepkg -si`
- inspect package contents when install payload changed

## Scripts

- Prefer Zsh for repo helper scripts unless Bash or POSIX `sh` is explicitly required.
