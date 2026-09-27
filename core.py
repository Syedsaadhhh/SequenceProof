"""Protocol-agnostic bounded trace-reduction kernel.

This module contains no knowledge of any specific application domain,
action names, state machine, or failure IDs. It accepts an opaque
callable oracle and a list of opaque action objects (dicts), and
reduces the trace using bounded ddmin until no single deletion preserves
the exact original failure ID (one-minimal certificate) or the budget
is exhausted.

The oracle contract:
    oracle(candidate: list[dict]) -> dict
    Must return a dict with at least:
        "status": one of REPRODUCED / NOT_REPRODUCED / INVALID_TRACE / EXECUTION_ERROR
        "failure_id": str | None  (non-None only when status == "REPRODUCED")

Guarantees:
- No insertion, reordering, or mutation of actions.
- Candidate accepted only when oracle returns status==REPRODUCED and
  failure_id matches the original exactly.
- INVALID_TRACE and EXECUTION_ERROR are never counted as evidence.
- Five fresh confirmation executions after reduction.
- One-minimal certificate when budget allows.
- Maximum 40 input actions, maximum 250 oracle calls (shared budget).
- Never claims global minimality.
"""
from __future__ import annotations

import math
import time
from typing import Any, Callable

MAX_STEPS = 40
MAX_BUDGET = 250
CONFIRM_ROUNDS = 5


def _accepts(oracle: Callable, candidate: list[dict], failure_id: str) -> bool:
    """Return True iff oracle confirms same failure_id on a non-empty candidate."""
    if not candidate:
        return False
    result = oracle(candidate)
    return (
        result.get("status") == "REPRODUCED"
        and result.get("failure_id") == failure_id
    )


def reduce_trace(
    trace: list[dict[str, Any]],
    failure_id: str,
    oracle: Callable[[list[dict[str, Any]]], dict[str, Any]],
    budget: int = MAX_BUDGET,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Bounded ddmin reduction with one-minimal certificate.

    Parameters
    ----------
    trace:
        Validated original action list (already confirmed reproducing).
    failure_id:
        Exact failure ID from the original replay; must be preserved.
    oracle:
        Callable(candidate) -> result dict. Called for every candidate.
        Must start from fresh state each time.
    budget:
        Maximum oracle calls allowed (shared with certificate pass).

    Returns
    -------
    reduced:
        Locally reduced trace (ordered exact-object subsequence of original).
    attempts:
        Total oracle calls consumed.
    minimality:
        Dict describing the minimality guarantee achieved.
    """
    current = trace[:]
    granularity = 2
    attempts = 0

    while len(current) >= 2 and attempts < budget:
        chunk = math.ceil(len(current) / granularity)
        reduced_this_pass = False
        for start in range(0, len(current), chunk):
            candidate = current[:start] + current[start + chunk:]
            attempts += 1
            if _accepts(oracle, candidate, failure_id):
                current = candidate
                granularity = max(2, granularity - 1)
                reduced_this_pass = True
                break
            if attempts >= budget:
                break
        if not reduced_this_pass:
            if granularity >= len(current):
                break
            granularity = min(len(current), granularity * 2)

    # One-minimal certificate pass: verify no single retained step can be removed.
    certificate_checks = 0
    one_minimal = False
    while current and attempts < budget:
        removed = False
        certificate_checks = 0
        for index in range(len(current)):
            if attempts >= budget:
                break
            candidate = current[:index] + current[index + 1:]
            attempts += 1
            certificate_checks += 1
            if _accepts(oracle, candidate, failure_id):
                current = candidate
                removed = True
                break
        if removed:
            continue
        one_minimal = certificate_checks == len(current)
        break

    minimality = {
        "kind": "one-minimal" if one_minimal else "bounded-local",
        "certified": one_minimal,
        "checks": certificate_checks,
        "statement": (
            "No single retained step can be removed while preserving the exact failure ID."
            if one_minimal
            else "The candidate-check budget ended before one-minimality could be certified."
        ),
    }
    return current, attempts, minimality


def confirm_reduced(
    reduced: list[dict[str, Any]],
    failure_id: str,
    oracle: Callable[[list[dict[str, Any]]], dict[str, Any]],
    rounds: int = CONFIRM_ROUNDS,
) -> tuple[bool, list[dict[str, Any]]]:
    """Run `rounds` fresh confirmations on the reduced trace.

    Returns (all_pass: bool, trial_summaries: list[dict]).
    Each trial summary has "status" and "failure_id" keys.
    """
    trials = []
    for _ in range(rounds):
        result = oracle(reduced)
        trial = {"status": result.get("status"), "failure_id": result.get("failure_id")}
        for key in ("run_id", "exit_code", "duration_seconds"):
            if key in result:
                trial[key] = result[key]
        trials.append(trial)
    all_pass = all(
        t["status"] == "REPRODUCED" and t["failure_id"] == failure_id
        for t in trials
    )
    return all_pass, trials


def run_reduction(
    trace: list[dict[str, Any]],
    oracle: Callable[[list[dict[str, Any]]], dict[str, Any]],
    fixed_oracle: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
    budget: int = MAX_BUDGET,
) -> dict[str, Any]:
    """Full reduction workflow: validate, reproduce, reduce, confirm, fix-check.

    Parameters
    ----------
    trace:
        Already-validated list of action dicts.
    oracle:
        Callable for the buggy/original path. Must start from fresh state.
    fixed_oracle:
        Optional callable for the corrected implementation. When None,
        fixed_result is None and fixed_passes is None (NOT_CHECKED).
    budget:
        Maximum oracle calls.

    Returns
    -------
    Result dict with keys:
        status, failure_id, original, original_steps, reduced_steps,
        trials, attempts, minimality, fixed_result, fixed_passes,
        duration_ms
    """
    start = time.perf_counter()

    # Step 1: original must reproduce.
    original = oracle(trace)
    if original.get("status") != "REPRODUCED":
        return {
            "status": original.get("status"),
            "failure_id": None,
            "original": original,
            "original_steps": trace,
            "reduced_steps": None,
            "trials": [],
            "attempts": 0,
            "minimality": None,
            "fixed_result": None,
            "fixed_passes": None,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        }

    failure_id = original["failure_id"]

    # Step 2: reduce.
    reduced, attempts, minimality = reduce_trace(trace, failure_id, oracle, budget=budget)

    # Step 3: confirm.
    verified, trials = confirm_reduced(reduced, failure_id, oracle)

    # Step 4: fix check.
    fixed_result: dict | None = None
    fixed_passes: bool | None = None
    if fixed_oracle is not None:
        fixed_result = fixed_oracle(reduced)
        fixed_passes = fixed_result.get("status") == "NOT_REPRODUCED"
    # else: fixed_passes remains None == NOT_CHECKED

    return {
        "status": "REPRODUCED" if verified else "FLAKY",
        "failure_id": failure_id,
        "original": original,
        "original_steps": trace,
        "reduced_steps": reduced if verified else None,
        "trials": trials,
        "attempts": attempts,
        "minimality": minimality,
        "fixed_result": fixed_result,
        "fixed_passes": fixed_passes,
        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
    }
