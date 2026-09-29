#!/usr/bin/bash
set -Eeuo pipefail

for argument in "$@"; do
  case $argument in
    --with-colons)
      printf 'fpr:::::::::8F17777118A33DDA9BA48E62AACB3243630052D9:\n'
      exit 0
      ;;
    --export)
      printf 'synthetic exported public key\n'
      exit 0
      ;;
  esac
done
exit 0
