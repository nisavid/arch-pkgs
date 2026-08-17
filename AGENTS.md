# AGENTS.md

This repo is a personal Arch packaging workspace. Treat it as a packaging and policy repo first.

Your job is not to make a package build once. Your job is to leave behind package files, service assets, and documentation that a fresh agent can inspect and update without chat history.

## Repo shape

- Keep packages under `packages/<name>/`.
- Keep each package self-contained with the files needed to build it: `PKGBUILD`, `.SRCINFO`, patches, service files, config files, and short package-local notes when helpful.
- Treat `packages/chatgpt/` as the explicit immutable artifact-ingest exception.
  It does not carry a `PKGBUILD` or `.SRCINFO` and does not use `makepkg`.
  Ingest it only with `tools/ingest_chatgpt.zsh`; never pass it to
  `tools/update_pacman_repo.zsh`.
- Prefer repository-relative documentation over chat-only explanations.

## Rules

- Never commit private filesystem paths, private hostnames, private network addresses, machine-specific IDs, tokens, or keys.
- Prefer stable packaged defaults over host-specific runtime state.
- When packaging services, install service assets and defaults, but do not commit local secrets or environment overrides.
- When adding or updating packages, regenerate `.SRCINFO`.
- Validate package changes with fresh evidence before claiming success.
- Use Conventional Commits for all commits.

## Package maintenance expectations

- For the package-change workflow and discovery sequence, use `.agents/skills/maintaining-arch-packages/`.
- When adding a new maintained package or changing a package baseline, follow
  `docs/policies/reference-packages.md` before writing local package files.
- Review upstream release notes and installation docs before changing package behavior.
- Follow Arch naming and layout conventions where practical, especially for Python packages and `systemd` assets.
- Keep one-off installation guidance simple for now: build and install directly from the package directory with `makepkg -si`.
- When a package change also changes install or service behavior, document the operator command needed to use it.
- When packaging software with telemetry or other outbound reporting, prefer privacy-respecting defaults that remain easy for users to understand and choose in the normal UX. Favor discoverable, reversible consent flows that fit upstream architecture and could plausibly be upstreamed, rather than packaging-only opt-ins hidden in docs, patches, or environment variables.

## Verification

Before claiming a package update is complete, run the relevant checks for the changed package:

- `makepkg --verifysource`
- `makepkg -f` or `makepkg -si`
- inspect package contents when install payload changed

The `makepkg` checks do not apply to `packages/chatgpt/`. Verify that lane by
ingesting the exact accepted artifact and provenance tuple with
`tools/ingest_chatgpt.zsh` and inspecting the staged repository output.

## Scripts

- Prefer Zsh for repo helper scripts unless Bash or POSIX `sh` is explicitly required.
