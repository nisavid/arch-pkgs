#!/usr/bin/bash
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
receipt="$root/output/receipts/prebuild-environment.txt"
[[ ! -e "$receipt" ]] || { printf 'prebuild receipt already exists\n' >&2; exit 2; }
mkdir -p "$root/output/receipts"
{
  printf 'schema=arch-pq-prebuild-environment-v1\nstarted_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'inherited_environment_enumerated=false\nprivate_configuration_inspected=false\n'
  printf 'classification=cybersecurity-related build-procedure and evidence-integrity work, xhigh effort\n'
  printf 'source_configuration=/etc/makepkg.conf\n'
  sha256sum /etc/makepkg.conf "$root/procedure/makepkg.conf"
  printf 'targeted_installed_identities_begin\n'
  pacman -Q sequoia-sq sequoia-sqv capnproto rustup clang git openssl glibc libgcc sqlite
  printf 'targeted_installed_identities_end\n'
  printf 'tool_versions_begin\n'
  makepkg --version
  bwrap --version
  bsdtar --version
  zstd --version
  sha256sum --version
  gpg --version
  curl --version
  git --version
  openssl version
  uname -m
  printf 'tool_versions_end\n'
  printf 'resolver_target=%s\n' "$(readlink /etc/resolv.conf)"
  findmnt -n -o TARGET,SOURCE,FSTYPE,OPTIONS -T /run/systemd/resolve/stub-resolv.conf
  printf 'completed_utc=%s\nprebuild_capture_exit=0\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"$receipt"
