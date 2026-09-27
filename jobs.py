"""jobs.py — bounded in-memory job store with truthful phase and event history.

Every phase transition must be caused by real backend work. This module
does not manufacture progress percentages, fake timers, or synthetic results.

Job phases (in order):
    QUEUED
    STARTING_SANDBOX
    CHECKING_OUT_REPOSITORY
    REPRODUCING_ORIGINAL
    REDUCING
    CONFIRMING
    VERIFYING_FIXED
    COMPLETED
    FAILED
    CANCELLED

Capacity:
    MAX_JOBS: Maximum jobs tracked at one time (oldest completed jobs evicted).
    Only one job may be QUEUED or actively running at a time in this prototype.
    Excess submissions are rejected with QUEUE_FULL.

TTL:
    Completed/Failed/Cancelled jobs are kept for JOB_TTL_SECONDS before
    eviction. Eviction is lazy — checked on each operation.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

MAX_JOBS = 20
JOB_TTL_SECONDS = 3600  # 1 hour
TERMINAL_PHASES = {"COMPLETED", "FAILED", "CANCELLED"}
ACTIVE_PHASES = {
    "QUEUED", "STARTING_SANDBOX", "CHECKING_OUT_REPOSITORY",
    "REPRODUCING_ORIGINAL", "REDUCING", "CONFIRMING", "VERIFYING_FIXED",
}
ALL_PHASES = ACTIVE_PHASES | TERMINAL_PHASES


class JobEvent:
    """A single phase-transition event in a job's history."""
    __slots__ = ("phase", "timestamp", "detail")

    def __init__(self, phase: str, detail: dict[str, Any]) -> None:
        self.phase = phase
        self.timestamp = time.time()
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "timestamp": self.timestamp,
            "detail": self.detail,
        }


class Job:
    """Represents a single analysis job."""
    __slots__ = (
        "job_id", "created_at", "request", "phase", "events",
        "result", "sandbox_id", "provider_name",
        "_lock", "_claimed",
    )

    def __init__(self, job_id: str, request: dict[str, Any]) -> None:
        self.job_id = job_id
        self.created_at = time.time()
        self.request = request
        self.phase = "QUEUED"
        self.events: list[JobEvent] = [JobEvent("QUEUED", {})]
        self.result: dict[str, Any] | None = None
        self.sandbox_id: str | None = None
        self.provider_name: str | None = None
        self._lock = threading.Lock()
        self._claimed = False

    def claim(self) -> bool:
        """Atomically claim a queued job before any sandbox work begins."""
        with self._lock:
            if self.phase != "QUEUED" or self._claimed:
                return False
            self._claimed = True
            return True

    def cancel_if_queued(self) -> bool:
        """Cancellation wins only before a worker claims this job."""
        with self._lock:
            if self.phase != "QUEUED" or self._claimed:
                return False
            self.phase = "CANCELLED"
            self.events.append(JobEvent("CANCELLED", {"reason": "user requested"}))
            return True

    def transition(self, phase: str, detail: dict[str, Any] | None = None) -> None:
        """Record a phase transition. Must be called from within the job thread."""
        with self._lock:
            self.phase = phase
            self.events.append(JobEvent(phase, detail or {}))
            if "sandbox_id" in (detail or {}):
                self.sandbox_id = detail["sandbox_id"]
            if "provider" in (detail or {}):
                self.provider_name = detail["provider"]

    def set_result(self, result: dict[str, Any]) -> None:
        with self._lock:
            self.result = result

    def to_dict(self, include_result: bool = True) -> dict[str, Any]:
        with self._lock:
            d: dict[str, Any] = {
                "job_id": self.job_id,
                "phase": self.phase,
                "created_at": self.created_at,
                "sandbox_id": self.sandbox_id,
                "provider_name": self.provider_name,
                "request": {
                    "repo_url": self.request.get("repo_url"),
                    "commit_sha": self.request.get("commit_sha"),
                    "manifest_path": self.request.get("manifest_path"),
                    "trace_length": len(self.request.get("trace", [])),
                },
                # Bounded log excerpt: last 30 events.
                "events": [e.to_dict() for e in self.events[-30:]],
            }
            if include_result and self.result is not None:
                d["result"] = self.result
            return d


class JobStore:
    """Thread-safe bounded in-memory job store."""

    def __init__(
        self,
        max_jobs: int = MAX_JOBS,
        ttl_seconds: float = JOB_TTL_SECONDS,
    ) -> None:
        self._max = max_jobs
        self._ttl = ttl_seconds
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def _evict_expired(self) -> None:
        """Remove terminal jobs older than TTL. Must be called under self._lock."""
        now = time.time()
        expired = [
            jid for jid, job in self._jobs.items()
            if job.phase in TERMINAL_PHASES
            and (now - job.created_at) > self._ttl
        ]
        for jid in expired:
            del self._jobs[jid]

    def _active_count(self) -> int:
        """Count jobs in non-terminal phases. Must be called under self._lock."""
        return sum(1 for j in self._jobs.values() if j.phase in ACTIVE_PHASES)

    def create_job(self, request: dict[str, Any]) -> Job:
        """Create and register a new job.

        Raises ValueError if the queue is full (one active job already running
        or max capacity reached).
        """
        with self._lock:
            self._evict_expired()
            if self._active_count() >= 1:
                raise ValueError(
                    "QUEUE_FULL: one analysis job is already running. "
                    "SequenceProof v1 supports one concurrent job."
                )
            if len(self._jobs) >= self._max:
                raise ValueError(
                    f"QUEUE_FULL: maximum {self._max} tracked jobs reached."
                )
            job_id = str(uuid.uuid4())
            job = Job(job_id=job_id, request=request)
            self._jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        """Mark a QUEUED job as CANCELLED. Returns True if successful."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            return job.cancel_if_queued()

    def all_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            self._evict_expired()
            return [j.to_dict(include_result=False) for j in self._jobs.values()]
