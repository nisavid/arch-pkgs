#!/usr/bin/env zsh
set -euo pipefail

require_gpu=false

usage() {
  print "usage: validate.zsh [--require-gpu]"
}

while (( $# > 0 )); do
  case "$1" in
    --require-gpu)
      require_gpu=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      print -u2 "Unknown argument: $1"
      usage >&2
      exit 64
      ;;
  esac
  shift
done

exit_status=0

report() {
  print -- "$@"
}

missing_required() {
  print -u2 "missing: $1"
  exit_status=1
}

for package in cuda nvidia-utils; do
  if pacman -Q "${package}" >/dev/null 2>&1; then
    report "package ${package}: $(pacman -Q "${package}")"
  else
    print -u2 "package ${package}: missing"
    exit_status=1
  fi
done

if command -v nvcc >/dev/null 2>&1; then
  report "nvcc: $(nvcc --version | tail -n 1)"
else
  print -u2 "nvcc: missing"
  exit_status=1
fi

gpu_status=0

if [[ -e /dev/nvidiactl ]]; then
  report "/dev/nvidiactl: present"
else
  report "/dev/nvidiactl: missing"
  gpu_status=1
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  report "nvidia-smi: present"
  if nvidia-smi --query-gpu=name,driver_version,cuda_version --format=csv,noheader >/tmp/arch-cuda-nvidia-smi.txt 2>/tmp/arch-cuda-nvidia-smi.err; then
    report "GPU driver/CUDA:"
    sed 's/^/  /' /tmp/arch-cuda-nvidia-smi.txt
  else
    report "nvidia-smi query failed:"
    sed 's/^/  /' /tmp/arch-cuda-nvidia-smi.err
    gpu_status=1
  fi
else
  report "nvidia-smi: missing"
  gpu_status=1
fi

if command -v ldconfig >/dev/null 2>&1 && ldconfig -p 2>/dev/null | grep -q 'libcuda\.so'; then
  report "libcuda.so: present"
else
  report "libcuda.so: missing"
  gpu_status=1
fi

if [[ "${require_gpu}" == true && "${gpu_status}" != 0 ]]; then
  print -u2 "GPU is required but NVIDIA device/runtime visibility is incomplete."
  exit_status=1
elif [[ "${gpu_status}" != 0 ]]; then
  report "GPU visibility incomplete; continuing because --require-gpu was not set."
fi

exit ${exit_status}
