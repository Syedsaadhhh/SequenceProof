"""sequenceproof_runner.py — SequenceProof v1 runner for stale-role-service.

Reads the trace file at $SEQUENCEPROOF_TRACE_PATH and replays it against
the service, then prints a strict v1 JSON result as the final stdout line.

Usage (buggy path):
    SEQUENCEPROOF_TRACE_PATH=trace.json python sequenceproof_runner.py

Usage (fixed path):
    SEQUENCEPROOF_TRACE_PATH=trace.json python sequenceproof_runner.py --fixed

Contract:
    - Final non-empty stdout line must be a strict JSON object with keys:
        schema_version, status, failure_id, evidence
    - status is one of: REPRODUCED, NOT_REPRODUCED, INVALID_TRACE
    - failure_id is non-null only when status == REPRODUCED
    - All diagnostic prints go before the final JSON line
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

_FAILURE_ID = "STALE_ROLE_AUTHORIZATION"
_ALLOWED_ACTIONS = {
    "switch_account",
    "perform_action",
    "view_dashboard",
    "logout",
}
_MAX_TRACE_STEPS = 40


def _output(status: str, failure_id: Any = None, evidence: Any = None) -> None:
    print(json.dumps({
        "schema_version": 1,
        "status": status,
        "failure_id": failure_id,
        "evidence": evidence,
    }), flush=True)


def main() -> None:
    fixed = "--fixed" in sys.argv

    trace_path = os.environ.get("SEQUENCEPROOF_TRACE_PATH")
    if not trace_path:
        print("RUNNER: SEQUENCEPROOF_TRACE_PATH not set", file=sys.stderr)
        _output("INVALID_TRACE")
        sys.exit(0)

    try:
        with open(trace_path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"RUNNER: cannot read trace: {exc}", file=sys.stderr)
        _output("INVALID_TRACE")
        sys.exit(0)

    if not isinstance(raw, list):
        print("RUNNER: trace must be a JSON array", file=sys.stderr)
        _output("INVALID_TRACE")
        sys.exit(0)

    if len(raw) > _MAX_TRACE_STEPS:
        print(f"RUNNER: trace has more than {_MAX_TRACE_STEPS} steps", file=sys.stderr)
        _output("INVALID_TRACE")
        sys.exit(0)

    # Validate all steps first.
    for i, step in enumerate(raw):
        if not isinstance(step, dict):
            print(f"RUNNER: step {i+1} is not an object", file=sys.stderr)
            _output("INVALID_TRACE")
            sys.exit(0)
        action = step.get("action")
        if action not in _ALLOWED_ACTIONS:
            print(f"RUNNER: step {i+1} has unknown action {action!r}", file=sys.stderr)
            _output("INVALID_TRACE")
            sys.exit(0)
        if action == "switch_account":
            if not isinstance(step.get("username"), str) or not step["username"]:
                print(f"RUNNER: switch_account step {i+1} missing username", file=sys.stderr)
                _output("INVALID_TRACE")
                sys.exit(0)
            if not isinstance(step.get("role"), str) or not step["role"]:
                print(f"RUNNER: switch_account step {i+1} missing role", file=sys.stderr)
                _output("INVALID_TRACE")
                sys.exit(0)
        if action == "perform_action":
            if not isinstance(step.get("name"), str) or not step["name"]:
                print(f"RUNNER: perform_action step {i+1} missing name", file=sys.stderr)
                _output("INVALID_TRACE")
                sys.exit(0)

    # Import the appropriate service implementation.
    if fixed:
        print("RUNNER: using fixed implementation", flush=True)
        from service_fixed import AuthState
    else:
        print("RUNNER: using buggy implementation", flush=True)
        from service_buggy import AuthState  # type: ignore[no-redef]

    state = AuthState()
    expected_role: str | None = None
    last_perform_result: dict[str, Any] | None = None

    for i, step in enumerate(raw):
        action = step["action"]
        print(f"RUNNER: step {i+1} action={action}", flush=True)

        if action in ("view_dashboard", "logout"):
            # No-op read-only actions.
            continue

        if action == "switch_account":
            username = step["username"]
            role = step["role"]
            state.switch_account(username, role)
            expected_role = role
            print(f"RUNNER: switched to {username} role={role}", flush=True)

        elif action == "perform_action":
            if state.current_user is None:
                print("RUNNER: perform_action before any switch_account", file=sys.stderr)
                _output("INVALID_TRACE")
                sys.exit(0)
            try:
                result = state.perform_action(step["name"])
            except ValueError as exc:
                print(f"RUNNER: perform_action failed: {exc}", file=sys.stderr)
                _output("INVALID_TRACE")
                sys.exit(0)
            last_perform_result = result
            authorized_as = result["authorized_as"]
            print(
                f"RUNNER: performed {step['name']} "
                f"expected_role={expected_role} authorized_as={authorized_as}",
                flush=True,
            )

            # Check for the stale-role bug: the current account's expected
            # role differs from what the service actually authorized.
            if expected_role is not None and authorized_as != expected_role:
                _output(
                    "REPRODUCED",
                    failure_id=_FAILURE_ID,
                    evidence={
                        "expected_role": expected_role,
                        "authorized_as": authorized_as,
                        "user": result["user"],
                        "action_name": step["name"],
                        "step": i + 1,
                    },
                )
                sys.exit(0)

    # Trace completed without the stale-role bug firing.
    _output("NOT_REPRODUCED")
    sys.exit(0)


if __name__ == "__main__":
    main()
