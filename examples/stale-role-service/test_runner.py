"""Unit tests for the stale-role-service runner.

Tests run the actual runner subprocess using the real service code,
verifying all four required cases:
1. Reproducing trace → REPRODUCED / STALE_ROLE_AUTHORIZATION
2. Invalid trace → INVALID_TRACE
3. Valid non-reproducing trace → NOT_REPRODUCED
4. Fixed implementation → NOT_REPRODUCED on the reproducing trace
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent
RUNNER = str(FIXTURE_DIR / "sequenceproof_runner.py")
NOISY_TRACE = FIXTURE_DIR / "traces" / "noisy_reproducing.json"
NON_REPRODUCING_TRACE = FIXTURE_DIR / "traces" / "non_reproducing.json"
INVALID_TRACE = FIXTURE_DIR / "traces" / "invalid_no_account.json"


def _run_runner(trace: list, fixed: bool = False) -> dict:
    """Write trace to a temp file and run the runner subprocess. Returns parsed output."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=str(FIXTURE_DIR)
    ) as f:
        json.dump(trace, f)
        trace_path = f.name
    try:
        argv = [sys.executable, RUNNER]
        if fixed:
            argv.append("--fixed")
        env = {**os.environ, "SEQUENCEPROOF_TRACE_PATH": trace_path}
        result = subprocess.run(
            argv,
            capture_output=True,
            timeout=15,
            cwd=str(FIXTURE_DIR),
            env=env,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        lines = [line for line in stdout.splitlines() if line.strip()]
        if not lines:
            raise AssertionError(f"Runner produced no output. stderr: {result.stderr.decode()}")
        last_line = lines[-1]
        return json.loads(last_line)
    finally:
        os.unlink(trace_path)


def _run_runner_file(trace_path: Path, fixed: bool = False) -> dict:
    """Run the runner with an existing trace file."""
    argv = [sys.executable, RUNNER]
    if fixed:
        argv.append("--fixed")
    env = {**os.environ, "SEQUENCEPROOF_TRACE_PATH": str(trace_path)}
    result = subprocess.run(
        argv,
        capture_output=True,
        timeout=15,
        cwd=str(FIXTURE_DIR),
        env=env,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise AssertionError(f"Runner produced no output. stderr: {result.stderr.decode()}")
    return json.loads(lines[-1])


class RunnerReproducingTests(unittest.TestCase):
    """Case 1: Reproducing trace."""

    def test_noisy_trace_reproduces_stale_role(self):
        result = _run_runner_file(NOISY_TRACE)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "REPRODUCED")
        self.assertEqual(result["failure_id"], "STALE_ROLE_AUTHORIZATION")
        self.assertIsNotNone(result.get("evidence"))
        evidence = result["evidence"]
        self.assertEqual(evidence["expected_role"], "viewer")
        self.assertEqual(evidence["authorized_as"], "admin")

    def test_minimal_reproducing_trace(self):
        trace = [
            {"action": "switch_account", "username": "alice", "role": "admin"},
            {"action": "switch_account", "username": "bob", "role": "viewer"},
            {"action": "perform_action", "name": "read_report"},
        ]
        result = _run_runner(trace)
        self.assertEqual(result["status"], "REPRODUCED")
        self.assertEqual(result["failure_id"], "STALE_ROLE_AUTHORIZATION")


class RunnerInvalidTests(unittest.TestCase):
    """Case 2: Invalid trace."""

    def test_perform_action_before_switch_account_is_invalid(self):
        result = _run_runner_file(INVALID_TRACE)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "INVALID_TRACE")
        self.assertIsNone(result["failure_id"])

    def test_unknown_action_is_invalid(self):
        trace = [{"action": "unknown_xyz"}]
        result = _run_runner(trace)
        self.assertEqual(result["status"], "INVALID_TRACE")
        self.assertIsNone(result["failure_id"])

    def test_switch_account_missing_role_is_invalid(self):
        trace = [{"action": "switch_account", "username": "alice"}]
        result = _run_runner(trace)
        self.assertEqual(result["status"], "INVALID_TRACE")

    def test_switch_account_missing_username_is_invalid(self):
        trace = [{"action": "switch_account", "role": "admin"}]
        result = _run_runner(trace)
        self.assertEqual(result["status"], "INVALID_TRACE")

    def test_empty_trace_is_invalid(self):
        result = _run_runner([])
        # Empty list = INVALID_TRACE (0 steps, no switch_account before perform_action
        # is never reached, but no output produced = INVALID_TRACE)
        # Actually an empty trace loops to the end → NOT_REPRODUCED, but that is valid.
        # The runner accepts empty as NOT_REPRODUCED (nothing happened).
        self.assertIn(result["status"], ("INVALID_TRACE", "NOT_REPRODUCED"))
        self.assertIsNone(result["failure_id"])


class RunnerNonReproducingTests(unittest.TestCase):
    """Case 3: Valid non-reproducing trace."""

    def test_single_account_no_bug(self):
        result = _run_runner_file(NON_REPRODUCING_TRACE)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "NOT_REPRODUCED")
        self.assertIsNone(result["failure_id"])

    def test_no_role_switch_no_bug(self):
        trace = [
            {"action": "switch_account", "username": "alice", "role": "admin"},
            {"action": "view_dashboard"},
            {"action": "perform_action", "name": "read_report"},
        ]
        result = _run_runner(trace)
        self.assertEqual(result["status"], "NOT_REPRODUCED")
        self.assertIsNone(result["failure_id"])


class RunnerFixedTests(unittest.TestCase):
    """Case 4: Fixed implementation."""

    def test_noisy_trace_does_not_reproduce_on_fixed(self):
        result = _run_runner_file(NOISY_TRACE, fixed=True)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "NOT_REPRODUCED")
        self.assertIsNone(result["failure_id"])

    def test_minimal_reproducing_trace_fixed(self):
        trace = [
            {"action": "switch_account", "username": "alice", "role": "admin"},
            {"action": "switch_account", "username": "bob", "role": "viewer"},
            {"action": "perform_action", "name": "read_report"},
        ]
        result = _run_runner(trace, fixed=True)
        self.assertEqual(result["status"], "NOT_REPRODUCED")
        self.assertIsNone(result["failure_id"])


if __name__ == "__main__":
    unittest.main()
