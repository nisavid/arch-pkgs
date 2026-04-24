# Arch CUDA Image

This document is the rollout note for the reusable Arch CUDA container image at
`containers/arch-cuda/`. The image is for short-lived GPU validation pods, with
SSH key access and an Arch userland containing `cuda` and `nvidia-utils`.

## Preflight Checks

- Confirm the GitHub Actions workflow has permission to write GHCR packages and
  artifact attestations for `ghcr.io/nisavid/arch-pkgs/arch-cuda`.
- Confirm the repository has admin permission on the GHCR package before relying
  on cleanup. GitHub grants this automatically for workflow-published packages
  and for packages explicitly connected to the repository.
- Confirm GHCR visibility and auth: the package can remain private, but the
  RunPod account must be able to pull it or a deliberate visibility change must
  be recorded.
- Review the action run inputs and verify no `PUBLIC_KEY`, token, or provider
  secret is committed to the repo or copied into the image context.
- For GPU validation, choose an on-demand RunPod pod first, attach an SSH public
  key through the provider UX, and record the selected GPU and driver version.
- Capture the current known-good digest before changing a template or asking a
  provider to pull `:rolling`.

## Step-by-Step Rollout

1. Open a PR and let the PR build run with `push: false`.
2. Merge to `main` or dispatch the workflow manually when the PR build is clean.
3. Record the published tags from `tools/arch_cuda_image.zsh print-tags <sha>`.
4. Verify the workflow produced a container digest and a registry attestation.
5. Create a private RunPod template from
   `containers/arch-cuda/runpod-template.json`.
6. Start one on-demand pod from the `:rolling` image with a temporary
   `PUBLIC_KEY` value supplied through RunPod secrets or environment settings.
7. SSH into the pod and run:

   ```bash
   validate.zsh --require-gpu
   ```

8. Save the image digest, RunPod template revision, GPU model, driver version,
   CUDA visibility, and validation output in the worklog for that validation
   run.

## Verification Signals

- PR build completes without publishing an image.
- Publish job pushes `rolling`, `cuda-13`, and `build-YYYYMMDD-<short7>` tags.
- GHCR shows an artifact attestation for the published digest.
- RunPod can pull the private image using the configured auth path.
- SSH accepts the injected public key and rejects password login.
- `validate.zsh --require-gpu` reports installed `cuda` and `nvidia-utils`
  packages, `nvcc`, `nvidia-smi`, GPU name, driver version, and CUDA visibility.

## Rollback Procedure

Use digest pinning for rollback. If `:rolling` is bad, update the RunPod template
to the last known-good digest instead of another mutable tag. If the image
itself is unusable, republish from the known-good commit and verify the new
digest before returning the template to `:rolling`.

Rollback evidence should include the failing digest, the known-good digest, the
RunPod template revision before and after the change, and a fresh
`validate.zsh --require-gpu` result from the restored pod.

If a rollback digest must remain available beyond normal retention, add a
`known-good-*` tag to that digest. Cleanup protects `known-good-*` tags as well
as `rolling` and `cuda-*`.

## Cleanup

- Destroy on-demand RunPod pods after evidence capture.
- Confirm no detached volume, stopped pod, template test pod, or provider
  storage charge remains.
- Keep GHCR tags `rolling`, `cuda-*`, and `known-good-*`; cleanup automation
  only considers old `build-*` versions and requires package admin permission.
- Remove temporary SSH keys from the provider account or secret store after the
  validation window.

## Notes
