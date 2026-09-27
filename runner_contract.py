"""Strict manifest, job-request, and runner-output models for SequenceProof.

All validation is performed in pure Python with no external libraries.
Validation raises ValueError with a human-readable message describing
exactly which field failed and why.

Runner output contract
----------------------
A runner may print diagnostic lines to stdout, but its final non-empty
stdout line must be a strict JSON object matching RunnerOutput.

RunnerOutput statuses:
    REPRODUCED      — bug confirmed; failure_id must be non-null
    NOT_REPRODUCED  — trace played through without triggering the failure
    INVALID_TRACE   — trace is structurally invalid for this repository

These are runner-reported statuses. The kernel additionally uses:
    EXECUTION_ERROR — nonzero exit, timeout, malformed/missing output,
                      or oversized output; never counts as evidence.

Manifest v1 rules
-----------------
- schema_version must be exactly 1
- id: non-empty string, no path separators or shell metacharacters
- title: non-empty string, ≤ 200 chars
- runner.argv: non-empty list of non-empty strings (no shell string)
- runner.fixed_argv: same rules, OPTIONAL — absent means NOT_CHECKED
- runner.timeout_seconds: 1..SERVICE_MAX_TIMEOUT_SECONDS
- No setup commands, credentials, callback URLs, or extra top-level keys
- All path-like values are rejected if they contain '..' or shell chars

URL allowlist
-------------
Only https://github.com/<owner>/<repo> is accepted in v1.
Owner and repo must be non-empty, contain only alphanumeric, '-', '_', '.'.

Commit SHA
----------
Exactly 40 lowercase hex characters; mutable refs (branch names) rejected.
"""
from __future__ import annotations

import re
from typing import Any

# Service-imposed ceilings that override manifest values.
SERVICE_MAX_TIMEOUT_SECONDS = 60
SERVICE_MAX_TRACE_ACTIONS = 40
SERVICE_MAX_REQUEST_BYTES = 32_768
SERVICE_MAX_RUNNER_OUTPUT_BYTES = 65_536
_MANIFEST_TOP_LEVEL_KEYS = {"schema_version", "id", "title", "runner"}
_RUNNER_KEYS = {"argv", "fixed_argv", "timeout_seconds"}
_SAFE_ID_RE = re.compile(r'^[A-Za-z0-9_\-]{1,64}$')
_SHA_RE = re.compile(r'^[0-9a-f]{40}$')
_GITHUB_URL_RE = re.compile(
    r'^https://github\.com/([A-Za-z0-9_\-\.]+)/([A-Za-z0-9_\-\.]+)$'
)
_SAFE_ARGV_CHAR_RE = re.compile(r'^[A-Za-z0-9_\-\./\:]+$')


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

class ManifestRunner:
    """Validated runner section of a manifest."""
    __slots__ = ("argv", "fixed_argv", "timeout_seconds")

    def __init__(
        self,
        argv: list[str],
        timeout_seconds: int,
        fixed_argv: list[str] | None = None,
    ) -> None:
        self.argv = argv
        self.fixed_argv = fixed_argv
        self.timeout_seconds = timeout_seconds

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "argv": self.argv,
            "timeout_seconds": self.timeout_seconds,
        }
        if self.fixed_argv is not None:
            d["fixed_argv"] = self.fixed_argv
        return d


class Manifest:
    """Validated and normalised manifest for a repository opt-in."""
    __slots__ = ("schema_version", "id", "title", "runner")

    def __init__(
        self,
        schema_version: int,
        manifest_id: str,
        title: str,
        runner: ManifestRunner,
    ) -> None:
        self.schema_version = schema_version
        self.id = manifest_id
        self.title = title
        self.runner = runner

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "runner": self.runner.to_dict(),
        }


def _validate_argv(argv: Any, field: str) -> list[str]:
    if not isinstance(argv, list) or not argv:
        raise ValueError(f"{field} must be a non-empty list")
    for i, part in enumerate(argv):
        if not isinstance(part, str) or not part:
            raise ValueError(f"{field}[{i}] must be a non-empty string")
        if not _SAFE_ARGV_CHAR_RE.match(part):
            raise ValueError(
                f"{field}[{i}] contains unsafe characters; "
                "use only [A-Za-z0-9_\\-./:]"
            )
    return list(argv)


def parse_manifest(raw: Any) -> Manifest:
    """Parse and strictly validate a manifest dict.

    Raises ValueError for any violation.
    Returns a Manifest on success.
    """
    if not isinstance(raw, dict):
        raise ValueError("manifest must be a JSON object")
    extra = set(raw) - _MANIFEST_TOP_LEVEL_KEYS
    if extra:
        raise ValueError(f"manifest has unknown top-level keys: {sorted(extra)}")

    if raw.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")

    manifest_id = raw.get("id")
    if not isinstance(manifest_id, str) or not manifest_id:
        raise ValueError("manifest.id must be a non-empty string")
    if not _SAFE_ID_RE.match(manifest_id):
        raise ValueError(
            "manifest.id must contain only [A-Za-z0-9_-] and be ≤ 64 chars"
        )

    title = raw.get("title")
    if not isinstance(title, str) or not title:
        raise ValueError("manifest.title must be a non-empty string")
    if len(title) > 200:
        raise ValueError("manifest.title must be ≤ 200 characters")

    runner_raw = raw.get("runner")
    if not isinstance(runner_raw, dict):
        raise ValueError("manifest.runner must be an object")
    extra_runner = set(runner_raw) - _RUNNER_KEYS
    if extra_runner:
        raise ValueError(f"manifest.runner has unknown keys: {sorted(extra_runner)}")

    argv = _validate_argv(runner_raw.get("argv"), "manifest.runner.argv")

    fixed_argv: list[str] | None = None
    if "fixed_argv" in runner_raw:
        fixed_argv = _validate_argv(runner_raw["fixed_argv"], "manifest.runner.fixed_argv")

    timeout_raw = runner_raw.get("timeout_seconds", 15)
    if not isinstance(timeout_raw, int) or isinstance(timeout_raw, bool):
        raise ValueError("manifest.runner.timeout_seconds must be an integer")
    if timeout_raw < 1:
        raise ValueError("manifest.runner.timeout_seconds must be ≥ 1")
    # Service ceiling overrides manifest value.
    timeout_seconds = min(timeout_raw, SERVICE_MAX_TIMEOUT_SECONDS)

    return Manifest(
        schema_version=1,
        manifest_id=manifest_id,
        title=title,
        runner=ManifestRunner(
            argv=argv,
            timeout_seconds=timeout_seconds,
            fixed_argv=fixed_argv,
        ),
    )


# ---------------------------------------------------------------------------
# Job request
# ---------------------------------------------------------------------------

class JobRequest:
    """Validated inbound job submission."""
    __slots__ = ("repo_url", "commit_sha", "manifest_path", "trace")

    def __init__(
        self,
        repo_url: str,
        commit_sha: str,
        manifest_path: str,
        trace: list[dict[str, Any]],
    ) -> None:
        self.repo_url = repo_url
        self.commit_sha = commit_sha
        self.manifest_path = manifest_path
        self.trace = trace

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_url": self.repo_url,
            "commit_sha": self.commit_sha,
            "manifest_path": self.manifest_path,
            "trace": self.trace,
        }


def parse_job_request(raw: Any) -> JobRequest:
    """Parse and validate a job submission dict.

    Raises ValueError for any violation.
    Returns JobRequest on success.
    """
    if not isinstance(raw, dict):
        raise ValueError("job request must be a JSON object")

    repo_url = raw.get("repo_url")
    if not isinstance(repo_url, str) or not repo_url:
        raise ValueError("repo_url must be a non-empty string")
    m = _GITHUB_URL_RE.match(repo_url)
    if not m:
        raise ValueError(
            "repo_url must be https://github.com/<owner>/<repo> "
            "(public GitHub HTTPS only)"
        )
    owner, repo = m.group(1), m.group(2)
    if not owner or not repo:
        raise ValueError("repo_url owner and repo must be non-empty")

    commit_sha = raw.get("commit_sha")
    if not isinstance(commit_sha, str):
        raise ValueError("commit_sha must be a string")
    if not _SHA_RE.match(commit_sha):
        raise ValueError(
            "commit_sha must be exactly 40 lowercase hex characters; "
            "mutable branch refs are not accepted"
        )

    manifest_path = raw.get("manifest_path", ".sequenceproof/manifest.json")
    if not isinstance(manifest_path, str) or not manifest_path:
        raise ValueError("manifest_path must be a non-empty string")
    if (len(manifest_path) > 200 or ".." in manifest_path or not
            re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', manifest_path)):
        raise ValueError("manifest_path must be a safe relative repository path")

    trace = raw.get("trace")
    if not isinstance(trace, list):
        raise ValueError("trace must be a JSON array")
    if len(trace) > SERVICE_MAX_TRACE_ACTIONS:
        raise ValueError(
            f"trace must have at most {SERVICE_MAX_TRACE_ACTIONS} actions"
        )
    for i, step in enumerate(trace):
        if not isinstance(step, dict):
            raise ValueError(f"trace[{i}] must be a JSON object")

    return JobRequest(
        repo_url=repo_url,
        commit_sha=commit_sha,
        manifest_path=manifest_path,
        trace=list(trace),
    )


# ---------------------------------------------------------------------------
# Runner output
# ---------------------------------------------------------------------------

RUNNER_STATUSES = {"REPRODUCED", "NOT_REPRODUCED", "INVALID_TRACE"}
_RUNNER_OUTPUT_KEYS = {"schema_version", "status", "failure_id", "evidence"}


class RunnerOutput:
    """Parsed and validated output from a runner subprocess."""
    __slots__ = ("schema_version", "status", "failure_id", "evidence")

    def __init__(
        self,
        schema_version: int,
        status: str,
        failure_id: str | None,
        evidence: dict[str, Any] | None,
    ) -> None:
        self.schema_version = schema_version
        self.status = status
        self.failure_id = failure_id
        self.evidence = evidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "failure_id": self.failure_id,
            "evidence": self.evidence,
        }


def parse_runner_output(raw: Any) -> RunnerOutput:
    """Parse and strictly validate a runner output dict.

    Raises ValueError for any violation.
    Returns RunnerOutput on success.
    """
    if not isinstance(raw, dict):
        raise ValueError("runner output must be a JSON object")

    extra = set(raw) - _RUNNER_OUTPUT_KEYS
    if extra:
        raise ValueError(f"runner output has unknown keys: {sorted(extra)}")

    if raw.get("schema_version") != 1:
        raise ValueError("runner output schema_version must be 1")

    status = raw.get("status")
    if status not in RUNNER_STATUSES:
        raise ValueError(
            f"runner output status must be one of {sorted(RUNNER_STATUSES)}"
        )

    failure_id = raw.get("failure_id", None)
    if status == "REPRODUCED":
        if not isinstance(failure_id, str) or not failure_id:
            raise ValueError(
                "runner output failure_id must be a non-empty string when status=REPRODUCED"
            )
    else:
        if failure_id is not None:
            raise ValueError(
                "runner output failure_id must be null when status is not REPRODUCED"
            )

    evidence = raw.get("evidence", None)
    if evidence is not None and not isinstance(evidence, dict):
        raise ValueError("runner output evidence must be a JSON object or null")

    return RunnerOutput(
        schema_version=1,
        status=status,
        failure_id=failure_id,
        evidence=evidence,
    )
