"""FakeSandboxProvider — deterministic test-only provider.

This provider MUST NEVER be selectable through any production HTTP endpoint.
It exists solely so unit tests can exercise the kernel and orchestration
layer without a real sandbox or network connection.

Fake behaviour contract:
- create_sandbox: returns a deterministic SandboxInfo with a reproducible ID.
- run_command: executes runner argv as a real subprocess in the host OS,
  inside a temporary fixture directory. For repository reset/clean commands,
  restores the fixture snapshot because the test directory has no Git metadata.
  It does NOT execute remote code or call any external service.
- destroy_sandbox: removes the temp directory.
- write_file / read_file: operate on the temp directory.

All fake behaviour is transparent and test-controlled. Runner results come
from actual local subprocesses; cleanup restores the fixture snapshot.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from sandbox.base import (
    SandboxInfo,
    SandboxResult,
    SandboxUnavailableError,
)

# Maximum output bytes captured per command.
_MAX_OUTPUT_BYTES = 65_536


class FakeSandboxProvider:
    """Deterministic local-process sandbox for unit tests only."""

    name = "fake"

    def __init__(self, fixture_root: Path | None = None) -> None:
        """
        Parameters
        ----------
        fixture_root:
            When provided, the sandbox temp dir is pre-seeded with a copy
            of this directory tree (allowing runner tests to work offline).
        """
        self._fixture_root = fixture_root
        self._sandboxes: dict[str, Path] = {}
        self._counter = 0

    @property
    def available(self) -> bool:
        return True

    def create_sandbox(self, repo_url: str, commit_sha: str) -> SandboxInfo:
        self._counter += 1
        sandbox_id = f"fake-{self._counter:04d}"
        tmp = Path(tempfile.mkdtemp(prefix="sp_fake_"))
        if self._fixture_root is not None:
            # Copy fixture tree into the sandbox workspace directory.
            workspace = tmp / "workspace"
            shutil.copytree(str(self._fixture_root), str(workspace))
        else:
            workspace = tmp / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
        self._sandboxes[sandbox_id] = tmp
        return SandboxInfo(
            sandbox_id=sandbox_id,
            provider_name="fake",
            workspace_path=str(workspace),
        )

    def run_command(
        self,
        sandbox_info: SandboxInfo,
        argv: list[str],
        env: dict[str, str],
        timeout_seconds: int,
    ) -> SandboxResult:
        """Run runner argv locally; restore the fixture for cleanup commands."""
        workspace = sandbox_info.workspace_path
        full_env = {**os.environ}
        # Override with sandbox env but redact any host secrets that would
        # normally be blocked. Tests may pass whatever env they need.
        full_env.update(env)
        # Never let host API keys reach the subprocess.
        for key in ("DAYTONA_API_KEY", "GITHUB_TOKEN"):
            full_env.pop(key, None)

        t0 = time.monotonic()
        # The fixture is a directory snapshot, not a Git checkout. Recreate it
        # for reset so each replay starts clean; clean is already satisfied.
        if len(argv) == 4 and argv[:3] == ["git", "reset", "--hard"]:
            shutil.rmtree(workspace)
            if self._fixture_root is not None:
                shutil.copytree(self._fixture_root, workspace)
            else:
                Path(workspace).mkdir(parents=True)
            return SandboxResult(0, "", "", time.monotonic() - t0)
        if argv == ["git", "clean", "-fdx"]:
            return SandboxResult(0, "", "", time.monotonic() - t0)

        timed_out = False
        try:
            proc = subprocess.run(
                argv,
                cwd=workspace,
                env=full_env,
                capture_output=True,
                timeout=timeout_seconds,
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
                stderr="",
                duration_seconds=duration,
                timed_out=True,
            )

    def destroy_sandbox(self, sandbox_info: SandboxInfo) -> None:
        tmp = self._sandboxes.pop(sandbox_info.sandbox_id, None)
        if tmp is not None and tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

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
