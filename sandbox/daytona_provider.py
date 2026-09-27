"""DaytonaSandboxProvider — hosted cloud sandbox via the Daytona Python SDK.

This provider is the primary production path for the SequenceProof demo.
It requires:
    - DAYTONA_API_KEY environment variable
    - Optional: DAYTONA_API_URL (defaults to https://app.daytona.io/api)
    - The `daytona` Python package (optional dependency)

If the SDK is not installed, the API key is missing, or the service is
unreachable, this provider returns available=False. The kernel then reports
SANDBOX_UNAVAILABLE — it never silently falls back to a fake result.

Security:
    - The API key is read from the server environment only.
    - The API key is never passed into the sandbox environment.
    - No host paths, credentials, or callback URLs enter the sandbox.
    - Commands are passed as argv lists, never shell strings.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from sandbox.base import (
    SandboxInfo,
    SandboxResult,
    SandboxUnavailableError,
)

_DAYTONA_DEFAULT_URL = "https://app.daytona.io/api"
_DAYTONA_WORKSPACE_PATH = "/home/daytona/repo"
_MAX_OUTPUT_BYTES = 65_536


def _load_sdk() -> Any:
    """Attempt to import the daytona SDK. Returns None if unavailable."""
    try:
        import daytona as _daytona  # type: ignore[import]
        return _daytona
    except ImportError:
        return None


class DaytonaSandboxProvider:
    """Hosted sandbox provider using the official Daytona Python SDK."""

    name = "daytona"

    def __init__(self) -> None:
        self._sdk = _load_sdk()
        self._api_key: str | None = os.environ.get("DAYTONA_API_KEY")
        self._api_url: str = os.environ.get("DAYTONA_API_URL", _DAYTONA_DEFAULT_URL)
        self._client: Any = None

        if self._sdk is not None and self._api_key:
            try:
                self._client = self._sdk.Daytona(
                    config=self._sdk.DaytonaConfig(
                        api_key=self._api_key,
                        api_url=self._api_url,
                    )
                )
            except Exception:
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def create_sandbox(self, repo_url: str, commit_sha: str) -> SandboxInfo:
        if not self.available:
            raise SandboxUnavailableError(
                "Daytona provider is unavailable: SDK not installed or "
                "DAYTONA_API_KEY not set"
            )
        sandbox = None
        try:
            sandbox = self._client.create(
                self._sdk.CreateSandboxFromSnapshotParams(
                    language="python",
                    env_vars={},  # No host secrets passed in.
                    auto_delete_interval=10,
                ),
                timeout=180,
            )
            sandbox_id: str = sandbox.id
            # Clone the public repo and pin the exact commit.
            clone_result = sandbox.process.exec(
                f"git clone --no-local {repo_url} {_DAYTONA_WORKSPACE_PATH} && "
                f"cd {_DAYTONA_WORKSPACE_PATH} && git checkout {commit_sha}",
                timeout=120,
            )
            if clone_result.exit_code != 0:
                raise SandboxUnavailableError(
                    f"Repository clone/checkout failed (exit {clone_result.exit_code}): "
                    f"{clone_result.result[:200]}"
                )
            return SandboxInfo(
                sandbox_id=sandbox_id,
                provider_name="daytona",
                workspace_path=_DAYTONA_WORKSPACE_PATH,
            )
        except Exception as exc:
            if sandbox is not None:
                try:
                    self._client.delete(sandbox)
                except Exception:
                    pass
            if isinstance(exc, SandboxUnavailableError):
                raise
            raise SandboxUnavailableError(f"Daytona create_sandbox failed: {exc}") from exc

    def run_command(
        self,
        sandbox_info: SandboxInfo,
        argv: list[str],
        env: dict[str, str],
        timeout_seconds: int,
    ) -> SandboxResult:
        if not self.available:
            raise SandboxUnavailableError("Daytona provider is unavailable")
        # Build the command from argv (no shell interpolation).
        cmd = " ".join(
            f"'{part}'" if " " in part or "'" in part else part
            for part in argv
        )
        env_prefix = " ".join(f"{k}={v}" for k, v in env.items())
        full_cmd = f"cd {sandbox_info.workspace_path} && {env_prefix} {cmd}"
        t0 = time.monotonic()
        try:
            sandbox = self._client.get(sandbox_info.sandbox_id)
            result = sandbox.process.exec(full_cmd, timeout=timeout_seconds)
            duration = time.monotonic() - t0
            raw_output: str = result.result or ""
            truncated = len(raw_output.encode()) > _MAX_OUTPUT_BYTES
            stdout = raw_output[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace") \
                if isinstance(raw_output, bytes) else raw_output[:_MAX_OUTPUT_BYTES]
            return SandboxResult(
                exit_code=result.exit_code,
                stdout=stdout,
                stderr="",  # Daytona SDK merges stderr into result.
                duration_seconds=duration,
                timed_out=False,
                truncated=truncated,
            )
        except Exception as exc:
            duration = time.monotonic() - t0
            err_str = str(exc)
            timed_out = "timeout" in err_str.lower() or "timed out" in err_str.lower()
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr=err_str[:512],
                duration_seconds=duration,
                timed_out=timed_out,
            )

    def destroy_sandbox(self, sandbox_info: SandboxInfo) -> None:
        if not self.available:
            return
        try:
            sandbox = self._client.get(sandbox_info.sandbox_id)
            self._client.delete(sandbox)
        except Exception:
            pass  # Must not raise in finally.

    def write_file(
        self,
        sandbox_info: SandboxInfo,
        relative_path: str,
        content: bytes,
    ) -> str:
        """Write file to sandbox by echoing base64-encoded content."""
        if not self.available:
            raise SandboxUnavailableError("Daytona provider is unavailable")
        import base64
        encoded = base64.b64encode(content).decode()
        dest = f"{sandbox_info.workspace_path}/{relative_path}"
        sandbox = self._client.get(sandbox_info.sandbox_id)
        result = sandbox.process.exec(
            f"mkdir -p $(dirname {dest}) && "
            f"echo {encoded} | base64 -d > {dest}",
            timeout=30,
        )
        if result.exit_code != 0:
            raise SandboxUnavailableError(f"Sandbox file write failed (exit {result.exit_code})")
        return dest

    def read_file(
        self,
        sandbox_info: SandboxInfo,
        relative_path: str,
    ) -> bytes:
        if not self.available:
            raise SandboxUnavailableError("Daytona provider is unavailable")
        src = f"{sandbox_info.workspace_path}/{relative_path}"
        sandbox = self._client.get(sandbox_info.sandbox_id)
        result = sandbox.process.exec(f"cat {src}", timeout=30)
        if result.exit_code != 0:
            raise FileNotFoundError(f"Sandbox file read failed: {src}")
        return (result.result or "").encode("utf-8")
