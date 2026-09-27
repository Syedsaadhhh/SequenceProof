"""repository_runner.py — provider-neutral orchestration for repository analysis jobs.

This module coordinates the full lifecycle of a sandbox-based analysis job:

1. Create a disposable sandbox via the provided SandboxProvider.
2. Clone the public repository at the exact pinned commit.
3. Read and validate .sequenceproof/manifest.json from the repository.
4. Replay the original trace and learn the failure ID.
5. Feed the oracle to core.reduce_trace for bounded ddmin reduction.
6. Confirm the reduced trace 5×.
7. Execute the fixed path (if manifest has fixed_argv).
8. Destroy the sandbox in finally — including on failures.

The orchestration layer does not know:
- The application domain, action names, or state machine.
- The expected failure ID (learned from the first real execution).
- Whether the result will be REPRODUCED, NOT_REPRODUCED, etc.

Fresh-execution invariant
-------------------------
Every individual oracle call (original, candidate, confirmation, fixed):
- Uses a new subprocess via the sandbox provider.
- Receives a unique SEQUENCEPROOF_RUN_ID.
- Writes the candidate trace to a fresh path (SEQUENCEPROOF_TRACE_PATH).
- Restores the repository to the pinned commit before execution (git reset).
- Removes untracked files from the previous replay.

Phase callbacks
---------------
The caller passes a `phase_callback(phase: str, detail: dict)` to receive
live phase transitions. Phases are documented in jobs.py.

Security
--------
- No host secrets enter the sandbox environment.
- No shell strings from HTTP enter any subprocess.
- argv from the manifest is passed as a list.
- Output is bounded to SERVICE_MAX_RUNNER_OUTPUT_BYTES.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from core import reduce_trace, confirm_reduced
from runner_contract import (
    Manifest,
    parse_manifest,
    parse_runner_output,
    RunnerOutput,
    SERVICE_MAX_RUNNER_OUTPUT_BYTES,
)
from sandbox.base import SandboxInfo, SandboxProvider, SandboxUnavailableError

# Hard cap on output bytes read from the sandbox before parsing.
_MAX_OUTPUT = SERVICE_MAX_RUNNER_OUTPUT_BYTES
_CONFIRM_ROUNDS = 5


class RunnerError(Exception):
    """Raised when the runner subprocess produces a non-REPRODUCED result
    or an unrecoverable error during the initial replay."""
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _exec_runner(
    provider: SandboxProvider,
    sandbox_info: SandboxInfo,
    manifest: Manifest,
    trace: list[dict],
    fixed: bool,
    run_id: str,
    trace_filename: str,
    commit_sha: str = "HEAD",
) -> dict[str, Any]:
    """Execute the runner once and return the parsed result dict.

    On nonzero exit, timeout, missing output, malformed JSON, or oversized
    output: returns {"status": "EXECUTION_ERROR", "failure_id": None, ...}.

    Never raises — errors are encoded in the returned dict.
    """
    # Restore the repository to the pinned commit and clean untracked files.
    for label, command in (
        ("reset", ["git", "reset", "--hard", commit_sha]),
        ("clean", ["git", "clean", "-fdx"]),
    ):
        cleanup = provider.run_command(sandbox_info, command, {}, timeout_seconds=10)
        if cleanup.exit_code != 0 or cleanup.timed_out:
            return {
                "status": "EXECUTION_ERROR",
                "failure_id": None,
                "detail": f"repository {label} failed (exit {cleanup.exit_code})",
                "exit_code": cleanup.exit_code,
                "run_id": run_id,
            }

    # Write the trace after cleanup so git clean cannot remove it.
    trace_bytes = json.dumps(trace).encode()
    actual_path = provider.write_file(sandbox_info, trace_filename, trace_bytes)
    env = {
        "SEQUENCEPROOF_TRACE_PATH": actual_path,
        "SEQUENCEPROOF_RUN_ID": run_id,
    }
    argv = manifest.runner.fixed_argv if fixed else manifest.runner.argv

    result = provider.run_command(
        sandbox_info,
        argv,
        env,
        timeout_seconds=manifest.runner.timeout_seconds,
    )

    if result.timed_out:
        return {
            "status": "EXECUTION_ERROR",
            "failure_id": None,
            "detail": "runner timed out",
            "exit_code": result.exit_code,
            "run_id": run_id,
        }
    if result.exit_code != 0:
        return {
            "status": "EXECUTION_ERROR",
            "failure_id": None,
            "detail": f"runner exited with code {result.exit_code}",
            "exit_code": result.exit_code,
            "stderr": result.stderr[:256],
            "run_id": run_id,
        }
    # Extract last non-empty stdout line.
    stdout = result.stdout
    if len(stdout.encode()) > _MAX_OUTPUT:
        return {
            "status": "EXECUTION_ERROR",
            "failure_id": None,
            "detail": "runner stdout exceeds output limit",
            "run_id": run_id,
        }
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return {
            "status": "EXECUTION_ERROR",
            "failure_id": None,
            "detail": "runner produced no output",
            "run_id": run_id,
        }
    last_line = lines[-1]
    try:
        raw_output = json.loads(last_line)
    except json.JSONDecodeError:
        return {
            "status": "EXECUTION_ERROR",
            "failure_id": None,
            "detail": f"runner final line is not JSON: {last_line[:100]}",
            "run_id": run_id,
        }
    try:
        parsed = parse_runner_output(raw_output)
    except ValueError as exc:
        return {
            "status": "EXECUTION_ERROR",
            "failure_id": None,
            "detail": f"runner output invalid: {exc}",
            "run_id": run_id,
        }

    return {
        "status": parsed.status,
        "failure_id": parsed.failure_id,
        "evidence": parsed.evidence,
        "exit_code": result.exit_code,
        "duration_seconds": result.duration_seconds,
        "run_id": run_id,
        "runner_argv": argv,
        "stdout_last_line": last_line,
    }


def _make_oracle(
    provider: SandboxProvider,
    sandbox_info: SandboxInfo,
    manifest: Manifest,
    fixed: bool = False,
    commit_sha: str = "HEAD",
    execution_log: list[dict[str, Any]] | None = None,
    stage_getter: Callable[[], str] | None = None,
) -> Callable[[list[dict]], dict[str, Any]]:
    """Return an oracle callable that the core reduction kernel can call."""
    counter = [0]

    def oracle(candidate: list[dict]) -> dict[str, Any]:
        counter[0] += 1
        run_id = str(uuid.uuid4())
        trace_filename = f".sequenceproof_runs/sp_run_{run_id[:8]}.json"
        result = _exec_runner(
            provider, sandbox_info, manifest,
            candidate, fixed, run_id, trace_filename, commit_sha,
        )
        if execution_log is not None:
            canonical = json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
            execution_log.append({
                "stage": stage_getter() if stage_getter else "RUNNER",
                "run_id": run_id,
                "trace_length": len(candidate),
                "trace_sha256": hashlib.sha256(canonical).hexdigest(),
                "status": result.get("status"),
                "failure_id": result.get("failure_id"),
                "exit_code": result.get("exit_code"),
                "duration_seconds": result.get("duration_seconds"),
            })
        return result

    return oracle


def run_repository_analysis(
    provider: SandboxProvider,
    repo_url: str,
    commit_sha: str,
    manifest_path: str,
    trace: list[dict[str, Any]],
    phase_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run a full repository analysis job.

    Parameters
    ----------
    provider:
        A SandboxProvider instance. Must not be FakeSandboxProvider in
        production (enforced at the HTTP layer, not here).
    repo_url:
        Allowlisted GitHub HTTPS URL.
    commit_sha:
        Exactly 40 hex characters.
    manifest_path:
        Relative path inside the repository to the manifest JSON.
    trace:
        Validated list of action dicts.
    phase_callback:
        Optional callable(phase_name, detail_dict) for live phase reporting.

    Returns
    -------
    dict with full job result, including status, failure_id, reduced_steps,
    trials, minimality, fixed_result, provider info, and sandbox_id.
    """
    def _phase(name: str, detail: dict | None = None) -> None:
        if phase_callback is not None:
            phase_callback(name, detail or {})

    start = time.perf_counter()
    sandbox_info: SandboxInfo | None = None
    _result: dict[str, Any] | None = None

    try:
        # Phase 1: create sandbox.
        _phase("STARTING_SANDBOX", {"provider": provider.name})
        sandbox_info = provider.create_sandbox(repo_url, commit_sha)

        # Phase 2: load manifest.
        _phase("CHECKING_OUT_REPOSITORY", {
            "sandbox_id": sandbox_info.sandbox_id,
            "repo_url": repo_url,
            "commit_sha": commit_sha,
        })
        def _fail(error_code: str, detail: str, extra: dict | None = None) -> dict[str, Any]:
            nonlocal _result
            _result = {
                "status": "FAILED",
                "error_code": error_code,
                "detail": detail,
                "provider": provider.name,
                "sandbox_id": sandbox_info.sandbox_id if sandbox_info else None,
            }
            if extra:
                _result.update(extra)
            return _result

        try:
            manifest_bytes = provider.read_file(sandbox_info, manifest_path)
        except (OSError, FileNotFoundError) as exc:
            return _fail("MANIFEST_NOT_FOUND", f"Cannot read manifest at {manifest_path}: {exc}")
        try:
            manifest_raw = json.loads(manifest_bytes)
            manifest = parse_manifest(manifest_raw)
        except (json.JSONDecodeError, ValueError) as exc:
            return _fail("MANIFEST_INVALID", str(exc))

        # Phase 3: reproduce original.
        _phase("REPRODUCING_ORIGINAL", {"trace_length": len(trace)})
        execution_log: list[dict[str, Any]] = []
        stage = ["REPRODUCING_ORIGINAL"]
        oracle = _make_oracle(
            provider, sandbox_info, manifest, fixed=False,
            commit_sha=commit_sha, execution_log=execution_log,
            stage_getter=lambda: stage[0],
        )
        original_result = oracle(trace)

        if original_result["status"] == "EXECUTION_ERROR":
            return _fail("RUNNER_EXECUTION_ERROR",
                         original_result.get("detail", "runner error"),
                         {"original": original_result})
        if original_result["status"] != "REPRODUCED":
            return _fail("ORIGINAL_NOT_REPRODUCED",
                         f"Original trace status: {original_result['status']}",
                         {"original": original_result})

        failure_id = original_result["failure_id"]

        # Phase 4: reduce.
        _phase("REDUCING", {"failure_id": failure_id})
        stage[0] = "REDUCING"
        reduced, attempts, minimality = reduce_trace(trace, failure_id, oracle)

        # Phase 5: confirm. These runs must occur AFTER the phase event.
        _phase("CONFIRMING", {"reduced_length": len(reduced)})
        stage[0] = "CONFIRMING"
        verified, confirm_trials = confirm_reduced(reduced, failure_id, oracle)

        # Phase 6: verify fixed.
        fixed_result: dict | None = None
        fixed_passes: bool | None = None
        if manifest.runner.fixed_argv is not None:
            _phase("VERIFYING_FIXED")
            stage[0] = "VERIFYING_FIXED"
            fixed_oracle = _make_oracle(
                provider, sandbox_info, manifest, fixed=True,
                commit_sha=commit_sha, execution_log=execution_log,
                stage_getter=lambda: stage[0],
            )
            fixed_raw = fixed_oracle(reduced)
            fixed_result = fixed_raw
            if fixed_raw["status"] == "EXECUTION_ERROR":
                fixed_passes = None
            else:
                fixed_passes = fixed_raw["status"] == "NOT_REPRODUCED"
        else:
            fixed_passes = None  # NOT_CHECKED

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        _result = {
            "status": "COMPLETED",
            "job_status": "REPRODUCED" if verified else "FLAKY",
            "failure_id": failure_id,
            "manifest": manifest.to_dict(),
            "original": original_result,
            "original_steps": trace,
            "reduced_steps": reduced if verified else None,
            "trials": confirm_trials,
            "attempts": attempts,
            "minimality": minimality,
            "executions": execution_log,
            "fixed_result": fixed_result,
            "fixed_passes": fixed_passes,
            "provider": provider.name,
            "sandbox_id": sandbox_info.sandbox_id,
            "commit_sha": commit_sha,
            "repo_url": repo_url,
            "duration_ms": duration_ms,
        }
        return _result

    except SandboxUnavailableError as exc:
        _result = {
            "status": "FAILED",
            "error_code": "SANDBOX_UNAVAILABLE",
            "detail": str(exc),
            "provider": provider.name,
        }
        return _result
    except Exception as exc:
        _result = {
            "status": "FAILED",
            "error_code": "INTERNAL_ERROR",
            "detail": str(exc),
            "provider": provider.name,
        }
        return _result
    finally:
        # Always attempt sandbox destruction — even after failures, errors,
        # or cancellation.  Record the truthful outcome without raising.
        # Mutate _result in place so the caller (job store) sees the
        # cleanup evidence after the finally completes.
        if sandbox_info is not None:
            _cleanup_status: dict[str, Any] = {
                "sandbox_id": sandbox_info.sandbox_id,
                "requested": True,
                "confirmed": False,
                "detail": None,
            }
            try:
                provider.destroy_sandbox(sandbox_info)
                _cleanup_status["confirmed"] = True
            except Exception as _exc:
                _cleanup_status["confirmed"] = False
                _cleanup_status["detail"] = str(_exc)[:200]
            if _result is not None:
                _result["cleanup"] = _cleanup_status
