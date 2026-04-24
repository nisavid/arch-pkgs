#!/usr/bin/env zsh
set -euo pipefail

image="ghcr.io/nisavid/arch-pkgs/arch-cuda"

usage() {
  print -u2 "usage: arch_cuda_image.zsh print-tags <sha>"
}

print_tags() {
  emulate -L zsh
  set -euo pipefail

  local sha="$1"
  local short_sha="${sha[1,7]}"
  local date_tag="${ARCH_CUDA_IMAGE_DATE:-}"

  if [[ -z "${sha}" ]]; then
    usage
    return 64
  fi

  if [[ -z "${date_tag}" ]]; then
    date_tag="$(TZ=UTC date +%Y%m%d)"
  fi

  print "${image}:rolling"
  print "${image}:cuda-13"
  print "${image}:build-${date_tag}-${short_sha}"
}

case "${1:-}" in
  print-tags)
    if (( $# != 2 )); then
      usage
      exit 64
    fi
    print_tags "$2"
    ;;
  *)
    usage
    exit 64
    ;;
esac
