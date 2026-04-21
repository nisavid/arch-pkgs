---
name: idiomatic-zsh
description: Use when writing or reviewing shell scripts in this repo unless the task specifically requires Bash or POSIX sh.
---

# Idiomatic Zsh

Use Zsh features when writing repo-local helper scripts for this repository.

## Rules

- Prefer Zsh built-ins and parameter expansion over external processes when it improves clarity.
- Use `emulate -L zsh` in functions for predictable behavior.
- Prefer arrays over stringly-typed command construction.
- Keep scripts readable and operator-friendly.

## Good fit

- repo maintenance helpers
- package review helpers
- local operator scripts

## Not a fit

- scripts that must run as `/bin/sh`
- existing Bash entrypoints that must stay Bash-compatible
