# ChatGPT fallback retirement

The locally maintained `chatgpt` fallback lane is retired. This repository no
longer ingests, builds, updates, or catalogs a ChatGPT package. The signed
`chatgpt-desktop-bin` package is the settled producer.

Do not add a `packages/chatgpt/` lane, a ChatGPT package-catalog row, a local
recipe for the official app, or a replacement for the retired one-off ingest
helper. `tools/check_repo_consistency.py` rejects those active maintenance
surfaces.

## Historical evidence

The path-free public acceptance record is retained unchanged at
[`evidence/chatgpt-fallback-baseline-2026-08-16.json`](evidence/chatgpt-fallback-baseline-2026-08-16.json).
Its SHA-256 is
`9002ee0c06f45c64f3fe08bd85fc4f7d74f962a8246f4ece9c6753477028f220`.
The record preserves the public source tag and revisions, package and payload
digests, payload entry count, accepted hosted checks, and their links. Its
`accepted-current` value records the fallback's disposition at acceptance; it
does not describe the current package catalog.

The retirement decisions and execution boundaries are recorded in
[`chatgpt-linux` #145](https://github.com/nisavid/chatgpt-linux/issues/145),
[`chatgpt-linux` #149](https://github.com/nisavid/chatgpt-linux/issues/149),
[`arch-pkgs` #74](https://github.com/nisavid/arch-pkgs/issues/74), and
[`arch-pkgs` #75](https://github.com/nisavid/arch-pkgs/issues/75).

## Repository withdrawal

`tools/retire_chatgpt.zsh` constructs a fresh candidate from a complete,
verified repository and its accepted manifest. It removes only `chatgpt`, the
recorded legacy `codex-app` and `codex-desktop` producers, their adjacent
signatures and index records, `chatgpt.provenance.json`, and stale `.old` index
backups that may still contain those retired records. Publication rollback is
provided by the complete repository snapshot, not by the stale index backups.
The source remains unchanged. Review the candidate before the existing
publisher promotes it.

The helper does not require a writer lock beside the source repository. That
location can be privileged. Instead, it binds the complete source to the
caller-approved manifest before copying, after copying, and again before
candidate promotion. Any concurrent source change rejects the candidate.

The live repository withdrawal and any redundant public copies belong to
[`arch-pkgs` #75](https://github.com/nisavid/arch-pkgs/issues/75). This source
change does not publish a candidate, uninstall a package, or alter host state.

## Private rollback evidence

Keep the designated private fallback package, its sidecars, and the recovery
snapshot through the first routine signed-upgrade gate in
[`arch-pkgs` #76](https://github.com/nisavid/arch-pkgs/issues/76). Their later
inventory, release authorization, deletion, and sanitized receipt belong only
to milestone M4 in
[`arch-pkgs` #77](https://github.com/nisavid/arch-pkgs/issues/77). Do not copy
private paths, credentials, executable artifacts, or the future M4 receipt into
this repository ahead of that review.
