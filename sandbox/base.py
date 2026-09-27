"""SandboxProvider protocol — the interface all providers must implement.

A SandboxProvider creates and destroys isolated execution environments.
The kernel never calls provider-specific code; it only calls this interface.
"""
from __future__ import annotations

from typing import Any, Protocol


class SandboxResult:
    """Result from a single command executed inside a sandbox."""
    __slots__ = (
        "exit_code", "stdout", "stderr", "duration_seconds",
        "timed_out", "truncated",
    )

    def __init__(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        duration_seconds: float,
        timed_out: bool = False,
        truncated: bool = False,
    ) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration_seconds = duration_seconds
        self.timed_out = timed_out
        self.truncated = truncated

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": round(self.duration_seconds, 3),
            "timed_out": self.timed_out,
            "truncated": self.truncated,
        }


class SandboxInfo:
    """Information about a created sandbox."""
    __slots__ = ("sandbox_id", "provider_name", "workspace_path")

    def __init__(
        self,
        sandbox_id: str,
        provider_name: str,
        workspace_path: str,
    ) -> None:
        self.sandbox_id = sandbox_id
        self.provider_name = provider_name
        self.workspace_path = workspace_path

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "provider_name": self.provider_name,
            "workspace_path": self.workspace_path,
        }


class SandboxUnavailableError(Exception):
    """Raised when the provider cannot create a sandbox.

    This is distinct from a sandbox runtime error (command failure).
    The kernel treats this as a PROVIDER_UNAVAILABLE job failure.
    """
    pass


class SandboxProvider(Protocol):
    """Interface that every sandbox provider must implement.

    All implementations must:
    - create exactly one sandbox per analysis job;
    - delete the sandbox in a finally block regardless of outcome;
    - never pass host secrets into the sandbox environment;
    - expose real process results (exit code, stdout, stderr, duration);
    - raise SandboxUnavailableError if the provider cannot be set up.

    Implementations must NOT:
    - mock or simulate command execution;
    - return hardcoded results;
    - silently fall back to another provider;
    - expose the provider API key to repository code.
    """

    @property
    def name(self) -> str:
        """Short identifying name, e.g. 'daytona', 'docker', 'fake'."""
        ...

    @property
    def available(self) -> bool:
        """True iff this provider can currently create sandboxes."""
        ...

    def create_sandbox(self, repo_url: str, commit_sha: str) -> SandboxInfo:
        """Create a disposable sandbox, clone the repo, and pin the commit.

        Raises SandboxUnavailableError if the provider cannot proceed.
        The caller is responsible for calling destroy_sandbox in finally.
        """
        ...

    def run_command(
        self,
        sandbox_info: SandboxInfo,
        argv: list[str],
        env: dict[str, str],
        timeout_seconds: int,
    ) -> SandboxResult:
        """Run a command inside the sandbox with explicit timeout.

        argv must be a list of strings; shell=False at all levels.
        env must not contain host secrets.
        Returns SandboxResult with real process data.
        """
        ...

    def destroy_sandbox(self, sandbox_info: SandboxInfo) -> None:
        """Destroy the sandbox and clean up all resources.

        Must be called in a finally block by the orchestration layer.
        Providers should raise on failure so the caller can record an
        honest cleanup status.  The orchestration finally catches any
        exception — providers must never swallow deletion failures silently.
        """
        ...

    def write_file(
        self,
        sandbox_info: SandboxInfo,
        relative_path: str,
        content: bytes,
    ) -> str:
        """Write a file into the sandbox workspace; return the absolute path."""
        ...

    def read_file(
        self,
        sandbox_info: SandboxInfo,
        relative_path: str,
    ) -> bytes:
        """Read a file from the sandbox workspace."""
        ...
