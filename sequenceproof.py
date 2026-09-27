"""Checkout compatibility preview — a stateful bug reproduction fixture.

This module implements the WRONG_CARD_CHARGED checkout scenario that serves
as the built-in SequenceProof preview. It is NOT the product.

The protocol-specific reduction logic (reduce_trace, confirm) is now delegated
to the generic kernel in core.py, which knows nothing about checkout, cards,
or specific failure IDs. The state machine, oracle, and domain logic remain here.

The generic reduction kernel (core.py) must never import this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

import core as _core

ALLOWED = {"view_catalog", "add_item", "remove_item", "set_card", "begin_checkout", "retry_payment", "view_receipt", "refresh_cart"}
MAX_STEPS = 40


@dataclass
class Checkout:
    card: str = "card-A"
    cart: list[str] = field(default_factory=list)
    pending_card: str | None = None
    retry_attempts: list[dict[str, Any]] = field(default_factory=list)

    def apply(self, step: dict[str, Any], fixed: bool = False) -> None:
        action = step["action"]
        if action in {"view_catalog", "view_receipt", "refresh_cart"}:
            return
        if action == "add_item":
            item = step.get("item")
            if not isinstance(item, str) or not item or len(item) > 40:
                raise ValueError("add_item needs a short item name")
            self.cart.append(item)
        elif action == "remove_item":
            item = step.get("item")
            if not isinstance(item, str) or item not in self.cart:
                raise ValueError("cannot remove an item that is not in the cart")
            self.cart.remove(item)
        elif action == "set_card":
            card = step.get("card")
            if card not in {"card-A", "card-B", "card-C"}:
                raise ValueError("card must be card-A, card-B or card-C")
            self.card = card
        elif action == "begin_checkout":
            if not self.cart:
                raise ValueError("checkout needs an item")
            if self.pending_card is not None:
                raise ValueError("checkout already pending")
            self.pending_card = self.card
        elif action == "retry_payment":
            if self.pending_card is None:
                raise ValueError("retry needs a pending checkout")
            # Deliberate sample bug: the retry charges the card snapshotted at begin_checkout.
            # The corrected implementation uses the current card instead.
            charged = self.card if fixed else self.pending_card
            # Record every attempt as {expected: card active now, actual: card charged}.
            self.retry_attempts.append({"expected": self.card, "actual": charged})
        else:
            raise ValueError("unsupported action")


def validate_trace(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_STEPS:
        raise ValueError(f"trace must be a list of 1 to {MAX_STEPS} steps")
    result = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or item.get("action") not in ALLOWED:
            raise ValueError(f"step {i + 1} has an unsupported action")
        if set(item) - {"action", "item", "card"}:
            raise ValueError(f"step {i + 1} has unknown fields")
        result.append(item)
    return result


def _attempt_evidence(state: Checkout) -> dict[str, Any]:
    """Return stable, JSON-safe evidence for every payment retry."""
    attempts = [dict(attempt) for attempt in state.retry_attempts]
    mismatches = [attempt for attempt in attempts
                  if attempt["actual"] != attempt["expected"]]
    return {
        "retry_attempts": attempts,
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
    }


def replay(trace: list[dict[str, Any]], fixed: bool = False) -> dict[str, Any]:
    state = Checkout()  # Fresh state for every candidate and trial.
    events = []
    for i, step in enumerate(trace):
        try:
            state.apply(step, fixed=fixed)
        except ValueError as exc:
            return {"status": "INVALID_TRACE", "failure_id": None,
                    "detail": str(exc), "at_step": i + 1, "events": events,
                    **_attempt_evidence(state)}
        attempt = None
        if step["action"] == "retry_payment":
            attempt = state.retry_attempts[-1]
            attempt["attempt"] = len(state.retry_attempts)
            attempt["step"] = i + 1
        events.append({"step": i + 1, "action": step["action"], "current_card": state.card,
                       "pending_card": state.pending_card,
                       "expected_card": attempt["expected"] if attempt else None,
                       "charged_card": attempt["actual"] if attempt else None,
                       "is_mismatch": bool(attempt and attempt["actual"] != attempt["expected"])})
    evidence = _attempt_evidence(state)
    if not state.retry_attempts:
        return {"status": "NOT_REPRODUCED", "failure_id": None,
                "detail": "No payment retry occurred", "events": events, **evidence}
    if evidence["mismatches"]:
        first = evidence["mismatches"][0]
        return {"status": "REPRODUCED", "failure_id": "WRONG_CARD_CHARGED",
                "detail": f"Expected {first['expected']}, charged {first['actual']}",
                # Keep these fields for compatibility while exposing every mismatch below.
                "expected": first["expected"], "actual": first["actual"],
                "events": events, **evidence}
    return {"status": "NOT_REPRODUCED", "failure_id": None,
            "detail": f"Charged the current card {state.retry_attempts[-1]['actual']}",
            "expected": state.retry_attempts[-1]["expected"],
            "actual": state.retry_attempts[-1]["actual"], "events": events, **evidence}


def prune_orphaned_steps(candidate: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Remove actions whose prerequisite was deleted, without adding or reordering actions.

    This is deliberately limited to the sample checkout protocol. Invalid parameters
    remain invalid; only a missing cart item or pending checkout can be pruned.
    Every returned candidate is still replayed by the failure oracle.
    """
    state = Checkout()
    valid = []
    pruned = 0
    for step in candidate:
        action = step["action"]
        if (action == "remove_item" and step.get("item") not in state.cart
                or action == "begin_checkout" and not state.cart
                or action == "retry_payment" and state.pending_card is None):
            pruned += 1
            continue
        try:
            state.apply(step)
        except ValueError:
            # A malformed action or any other protocol violation must not be
            # silently repaired into apparent evidence.
            return candidate, 0
        valid.append(step)
    return valid, pruned


def _orphan_pruning_oracle(candidate: list[dict[str, Any]]) -> dict[str, Any]:
    """Oracle that applies checkout orphan-pruning before replaying.

    This is the domain-specific adapter that bridges the generic core kernel
    to the checkout state machine. The kernel only calls this — it has no
    knowledge of prune_orphaned_steps, Checkout, or WRONG_CARD_CHARGED.
    """
    repaired, _ = prune_orphaned_steps(candidate)
    return replay(repaired)


def analyze(raw_trace: Any) -> dict[str, Any]:
    """Checkout compatibility preview — unchanged public contract.

    The original trace is replayed directly (no orphan-pruning applied to it).
    Reduction candidates use the pruning oracle as before.
    Internally delegates reduction and confirmation to core.run_reduction.
    """
    trace = validate_trace(raw_trace)
    start = time.perf_counter()

    # Step 1: replay the original trace directly — no orphan-pruning applied.
    # This preserves INVALID_TRACE / NOT_REPRODUCED for invalid originals.
    original = replay(trace)
    if original["status"] != "REPRODUCED":
        return {
            "status": original["status"],
            "failure_id": None,
            "original": original,
            "original_steps": trace,
            "reduced_steps": None,
            "trials": [],
            "attempts": 0,
            "orphan_steps_pruned": 0,
            "minimality": None,
            "fixed_result": None,
            "fixed_passes": None,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        }

    # Count orphan steps pruned so the original API contract is preserved.
    orphan_steps_pruned = [0]

    def _counting_oracle(candidate: list[dict[str, Any]]) -> dict[str, Any]:
        repaired, pruned = prune_orphaned_steps(candidate)
        if pruned:
            orphan_steps_pruned[0] += pruned
        return replay(repaired)

    failure_id = original["failure_id"]

    # Step 2: reduce via the generic kernel (pruning oracle for candidates).
    reduced, attempts, minimality = _core.reduce_trace(
        trace=trace,
        failure_id=failure_id,
        oracle=_counting_oracle,
    )

    # Step 3: confirm 5×.
    verified, trials = _core.confirm_reduced(reduced, failure_id, _counting_oracle)

    # Step 4: fix-check.
    fixed = replay(reduced, fixed=True)
    fixed_passes = fixed["status"] == "NOT_REPRODUCED"

    return {
        "status": "REPRODUCED" if verified else "FLAKY",
        "failure_id": failure_id,
        "original": original,
        "original_steps": trace,
        "reduced_steps": reduced if verified else None,
        "trials": trials,
        "attempts": attempts,
        "orphan_steps_pruned": orphan_steps_pruned[0],
        "minimality": minimality,
        "fixed_result": fixed,
        "fixed_passes": fixed_passes,
        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
    }


SAMPLE = [
    {"action": "view_catalog"}, {"action": "add_item", "item": "notebook"},
    {"action": "refresh_cart"}, {"action": "set_card", "card": "card-A"},
    {"action": "view_catalog"}, {"action": "begin_checkout"},
    {"action": "view_receipt"}, {"action": "set_card", "card": "card-B"},
    {"action": "refresh_cart"}, {"action": "view_catalog"},
    {"action": "retry_payment"}, {"action": "view_receipt"},
]
