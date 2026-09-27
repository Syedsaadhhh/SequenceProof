"""DockerSandboxProvider — local sandbox using Docker.

This provider is available only when Docker is installed and accessible.
If Docker is absent, available returns False and the kernel reports
SANDBOX_UNAVAILABLE — it never simulates a Docker run.

Security boundaries:
    --rm                       container is removed after run
    --network none             replay containers have no network
    --read-only                read-only root filesystem
    --tmpfs /tmp               writable scratch only inside container
    --user 1000:1000           non-root user
    --cpus 0.5                 CPU limit
    --memory 256m              memory limit
    --pids-limit 64            PID limit
    No --privileged
    No Docker socket mounts
    No host credential mounts

The repo is cloned/fetched on the host (with network), pinned to the
exact commit SHA, then mounted read-only into the replay container.
This means replay commands execute with network disabled.

If Docker is missing or the daemon is unreachable, the provider
reports itself as unavailable without simulating results.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from sandbox.base import (
    SandboxInfo,
    SandboxResult,
    SandboxUnavailableError,
)

_DOCKER_IMAGE = "python:3.11-slim"
_MAX_OUTPUT_BYTES = 65_536


def _docker_available() -> bool:
    """Return True if docker is in PATH and the daemon responds."""
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


class DockerSandboxProvider:
    """Local Docker sandbox provider."""

    name = "docker"

    def __init__(self) -> None:
        self._available = _docker_available()
        self._sandboxes: dict[str, dict[str, Any]] = {}

    @property
    def available(self) -> bool:
        return self._available

    def create_sandbox(self, repo_url: str, commit_sha: str) -> SandboxInfo:
        if not self.available:
            raise SandboxUnavailableError(
                "Docker is not available on this host"
            )
        sandbox_id = f"docker-{uuid.uuid4().hex[:12]}"
        # Clone onto the host (needs network).
        tmp = Path(tempfile.mkdtemp(prefix="sp_docker_"))
        try:
            result = subprocess.run(
                ["git", "clone", "--no-local", repo_url, str(tmp / "repo")],
                capture_output=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise SandboxUnavailableError(
                    f"git clone failed: {result.stderr[:200].decode(errors='replace')}"
                )
            result = subprocess.run(
                ["git", "-C", str(tmp / "repo"), "checkout", commit_sha],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise SandboxUnavailableError(
                    f"git checkout {commit_sha} failed: "
                    f"{result.stderr[:200].decode(errors='replace')}"
                )
            self._sandboxes[sandbox_id] = {
                "tmp": tmp,
                "repo_path": str(tmp / "repo"),
            }
            return SandboxInfo(
                sandbox_id=sandbox_id,
                provider_name="docker",
                workspace_path=str(tmp / "repo"),
            )
        except SandboxUnavailableError:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(tmp, ignore_errors=True)
            raise SandboxUnavailableError(
                f"Docker sandbox creation failed: {exc}"
            ) from exc

    def run_command(
        self,
        sandbox_info: SandboxInfo,
        argv: list[str],
        env: dict[str, str],
        timeout_seconds: int,
    ) -> SandboxResult:
        if not self.available:
            raise SandboxUnavailableError("Docker provider is unavailable")
        repo_path = sandbox_info.workspace_path
        env_args: list[str] = []
        for k, v in env.items():
            # Redact any host secrets.
            if k in ("DAYTONA_API_KEY", "GITHUB_TOKEN"):
                continue
            env_args += ["-e", f"{k}={v}"]

        docker_cmd = [
            "docker", "run",
            "--rm",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:size=64m",
            "--user", "1000:1000",
            "--cpus", "0.5",
            "--memory", "256m",
            "--pids-limit", "64",
            "-v", f"{repo_path}:/workspace:ro",
            "--workdir", "/workspace",
            *env_args,
            _DOCKER_IMAGE,
            *argv,
        ]
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                timeout=timeout_seconds + 5,  # +5 for Docker overhead.
            )
            duration = time.monotonic() - t0
            stdout_bytes = proc.stdout[:_MAX_OUTPUT_BYTES]
            stderr_bytes = proc.stderr[:_MAX_OUTPUT_BYTES]
            return SandboxResult(
                exit_code=proc.returncode,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_seconds=duration,
                timed_out=False,
                truncated=(
                    len(proc.stdout) > _MAX_OUTPUT_BYTES
                    or len(proc.stderr) > _MAX_OUTPUT_BYTES
                ),
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - t0
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr="timed out",
                duration_seconds=duration,
                timed_out=True,
            )

    def destroy_sandbox(self, sandbox_info: SandboxInfo) -> None:
        meta = self._sandboxes.pop(sandbox_info.sandbox_id, None)
        if meta:
            tmp = meta["tmp"]
            shutil.rmtree(str(tmp), ignore_errors=True)

    def write_file(
        self,
        sandbox_info: SandboxInfo,
        relative_path: str,
        content: bytes,
    ) -> str:
        dest = Path(sandbox_info.workspace_path) / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return str(dest)

    def read_file(
        self,
        sandbox_info: SandboxInfo,
        relative_path: str,
    ) -> bytes:
        path = Path(sandbox_info.workspace_path) / relative_path
        return path.read_bytes()
