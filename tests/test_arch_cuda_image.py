import json
import os
import re
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ghcr.io/nisavid/arch-pkgs/arch-cuda"


class ArchCudaImageTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    def test_container_scaffold_uses_strict_context_and_expected_packages(self):
        containerfile = self.read("containers/arch-cuda/Containerfile")
        dockerignore = self.read("containers/arch-cuda/.dockerignore")

        self.assertIn("FROM ghcr.io/archlinux/archlinux:base-devel", containerfile)
        self.assertIn("ENV PATH=/opt/cuda/bin:", containerfile)
        self.assertIn("ENV LD_LIBRARY_PATH=/opt/cuda/lib64:", containerfile)
        self.assertRegex(containerfile, r"pacman\s+-Syu\s+--noconfirm")
        for package in (
            "base-devel",
            "cuda",
            "git",
            "jq",
            "nvidia-utils",
            "openssh",
            "python",
            "sudo",
            "which",
            "zsh",
        ):
            self.assertRegex(containerfile, rf"\b{re.escape(package)}\b")
        self.assertIn("EXPOSE 22/tcp", containerfile)
        self.assertIn("ENTRYPOINT [\"/usr/local/bin/entrypoint.zsh\"]", containerfile)
        self.assertRegex(containerfile, r"\n\s+zsh\s+\\")
        self.assertIn("**", dockerignore)
        self.assertIn("!Containerfile", dockerignore)
        self.assertIn("!entrypoint.zsh", dockerignore)
        self.assertIn("!validate.zsh", dockerignore)
        self.assertNotIn("\n!/\n", dockerignore)
        self.assertNotIn("packages/", containerfile)

    def test_entrypoint_hardens_ssh_and_fails_without_public_key(self):
        entrypoint = self.read("containers/arch-cuda/entrypoint.zsh")

        self.assertIn("set -euo pipefail", entrypoint)
        self.assertIn("PUBLIC_KEY", entrypoint)
        self.assertRegex(entrypoint, r"exit\s+64")
        for directive in (
            "PasswordAuthentication no",
            "KbdInteractiveAuthentication no",
            "PermitEmptyPasswords no",
            "PermitRootLogin prohibit-password",
            "PubkeyAuthentication yes",
        ):
            self.assertIn(directive, entrypoint)
        self.assertIn("ssh-keygen -l -f /root/.ssh/authorized_keys", entrypoint)
        self.assertIn("chmod 700 /root/.ssh", entrypoint)
        self.assertIn("chmod 600 /root/.ssh/authorized_keys", entrypoint)
        self.assertIn("/usr/sbin/sshd", entrypoint)
        self.assertIn("-D", entrypoint)
        self.assertIn("-e", entrypoint)

    def test_validate_script_has_off_gpu_and_required_gpu_modes(self):
        validate = self.read("containers/arch-cuda/validate.zsh")

        self.assertIn("--require-gpu", validate)
        self.assertIn("cuda", validate)
        self.assertIn("nvidia-utils", validate)
        self.assertIn("nvcc", validate)
        self.assertIn("nvidia-smi", validate)
        self.assertIn("/dev/nvidiactl", validate)
        self.assertRegex(validate, r"require_gpu=.*false")
        self.assertRegex(validate, r"require_gpu=.*true")
        self.assertIn("GPU is required", validate)
        self.assertNotRegex(validate, r"(?m)^status=")
        self.assertIn("exit ${exit_status}", validate)

    def test_zsh_scripts_parse(self):
        scripts = [
            "tools/arch_cuda_image.zsh",
            "containers/arch-cuda/entrypoint.zsh",
            "containers/arch-cuda/validate.zsh",
        ]
        subprocess.run(
            ["zsh", "-n", *scripts],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def test_runpod_template_targets_private_arch_cuda_ssh_pod(self):
        template = json.loads(self.read("containers/arch-cuda/runpod-template.json"))

        self.assertEqual(template["imageName"], f"{IMAGE}:rolling")
        self.assertEqual(template["containerDiskInGb"], 50)
        self.assertEqual(template["volumeInGb"], 20)
        self.assertEqual(template["volumeMountPath"], "/workspace")
        self.assertIn("22/tcp", template["ports"])
        self.assertFalse(template["isPublic"])
        self.assertNotIn("PUBLIC_KEY", json.dumps(template))

    def test_helper_generates_expected_tags_and_image_name(self):
        helper = REPO_ROOT / "tools" / "arch_cuda_image.zsh"
        self.assertTrue(os.access(helper, os.X_OK), "helper script must be executable")
        env = os.environ.copy()
        env["ARCH_CUDA_IMAGE_DATE"] = "20260424"
        result = subprocess.run(
            ["zsh", str(helper), "print-tags", "abcdef1234567890"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        self.assertEqual(
            result.stdout.splitlines(),
            [
                f"{IMAGE}:rolling",
                f"{IMAGE}:cuda-13",
                f"{IMAGE}:build-20260424-abcdef1",
            ],
        )

    def test_workflow_separates_pr_build_from_publish_and_cleanup(self):
        workflow = self.read(".github/workflows/arch-cuda-image.yml")

        self.assertIn("pull_request:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("schedule:", workflow)
        self.assertIn("context: containers/arch-cuda", workflow)
        self.assertIn("push: false", workflow)
        self.assertIn("packages: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("actions/attest@", workflow)
        self.assertIn(
            "actions/attest@59d89421af93a897026c735860bf21b6eb4f7b26",
            workflow,
        )
        self.assertNotIn(
            "actions/attest@281a49d4cbb0a72c9575a50d18f6deb515a11deb",
            workflow,
        )
        self.assertIn("Verify published image", workflow)
        self.assertIn("docker buildx imagetools inspect", workflow)
        self.assertIn("${IMAGE_NAME}@${DIGEST}", workflow)
        self.assertIn("cleanup", workflow.lower())
        self.assertIn("needs.publish.result == 'success'", workflow)
        self.assertIn("build-*", workflow)
        self.assertIn("rolling", workflow)
        self.assertIn("cuda-*", workflow)
        self.assertIn("keep=10", workflow)
        self.assertIn("arch-pkgs%2Farch-cuda", workflow)
        self.assertIn("known-good-", workflow)

        for action_ref in re.findall(r"uses:\s+([^\s]+)", workflow):
            self.assertRegex(
                action_ref,
                r"@[0-9a-f]{40}$",
                msg=f"Action must be pinned by full SHA: {action_ref}",
            )

    def test_maintainer_docs_cover_rollout_rollback_and_validation(self):
        docs = self.read("docs/maintainers/arch-cuda-image.md")
        readme = self.read("README.md")
        rig = self.read("docs/maintainers/utilyze-nvidia-validation-rig.md")

        for phrase in (
            "Preflight Checks",
            "Step-by-Step Rollout",
            "Verification Signals",
            "Rollback Procedure",
            "Cleanup",
            "validate.zsh --require-gpu",
            "known-good digest",
            "known-good-*",
            "admin permission",
            "driver version",
        ):
            self.assertIn(phrase, docs)
        self.assertIn("docs/maintainers/arch-cuda-image.md", readme)
        self.assertIn("arch-cuda", rig)


if __name__ == "__main__":
    unittest.main()
