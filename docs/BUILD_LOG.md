# Build log

## 2026-09-26 — executable baseline

- Implemented a synthetic checkout state machine and `WRONG_CARD_CHARGED` oracle.
- Added bounded delta debugging and five fresh confirmation trials.
- Added corrected-code replay and downloadable JSON evidence.
- Added validity-aware pruning for actions orphaned by a candidate deletion.
- Added six tests, including invalid input and an orphan-pruning case.
- Added Docker deployment support through `HOST` and `PORT`.

### Observed baseline

| Check | Result |
| --- | --- |
| Sample reduction | 12 actions to 4 |
| Failure identity | `WRONG_CARD_CHARGED` preserved |
| Confirmation | 5 of 5 fresh runs |
| Corrected version | Does not reproduce |
| Unit suite | 6 tests pass |

---

## 2026-09-27 — oracle false-positive fix + adversarial regression tests

### Tested hypothesis

**Question:** Can a `set_card` issued *after* `retry_payment` produce a
false-positive `WRONG_CARD_CHARGED` report when the payment was actually
charged to the correct card?

**Adversarial trace:**
```
add_item(pen) → begin_checkout   (pending_card = card-A)
             → retry_payment     (charges card-A; card-A == card-A: CORRECT)
             → set_card(card-B)  (card changes AFTER the charge)
```

### Observed before fix

`replay()` evaluated `state.charged_card != state.card` at the **end** of the
trace.  After the post-retry `set_card(card-B)`, `charged_card=A` and
`card=B` diverged, so the oracle reported `REPRODUCED / WRONG_CARD_CHARGED`.

`analyze()` accepted the trace as a verified reproduction:
- `status: REPRODUCED`
- `failure_id: WRONG_CARD_CHARGED`
- `reduced_steps` non-None (4 steps including the spurious `set_card`)
- `fixed_passes: False` — because the fixed implementation also charged
  `card-A` at retry time (the only card then active), so the same post-retry
  divergence fired on the corrected path too.

The corrected implementation therefore appeared to "not fix" a bug that was
never present in this trace.

### Root cause

The oracle compared card state **at trace end** rather than **at the moment
`retry_payment` fired**.  The `WRONG_CARD_CHARGED` bug is a stale-snapshot
defect: `retry_payment` uses `pending_card` (snapshotted at `begin_checkout`)
instead of the *current* card.  That comparison must happen at retry time.
Any `set_card` after the retry is irrelevant to whether the charge was wrong.

### Fix (sequenceproof.py)

Added `Checkout.card_at_retry: str | None` — set to `self.card` every time
`retry_payment` fires, on both the buggy and corrected paths.

Changed the oracle condition from:

```python
if state.charged_card != state.card:          # ← compared final card
```

to:

```python
if state.charged_card != state.card_at_retry: # ← compared card at retry time
```

`expected` and `detail` fields also updated to reference `card_at_retry`.

This is a minimal, targeted change: one new dataclass field, one guard update,
two string-format references.  No public API surface changed.

### Observed after fix

| Trace | Before | After |
| --- | --- | --- |
| Adversarial (post-retry set_card) | `REPRODUCED` (false positive) | `NOT_REPRODUCED` |
| Default SAMPLE (12→4 reduction) | `REPRODUCED` ✓ | `REPRODUCED` ✓ |
| Second trace (card-B then card-C) | `REPRODUCED` ✓ | `REPRODUCED` ✓ |
| Invalid trace (retry with no checkout) | `INVALID_TRACE` ✓ | `INVALID_TRACE` ✓ |
| Non-reproducing trace | `NOT_REPRODUCED` ✓ | `NOT_REPRODUCED` ✓ |
| Corrected-implementation pass | `True` ✓ | `True` ✓ |

### Changed files

| File | Change |
| --- | --- |
| `sequenceproof.py` | Added `card_at_retry` field; oracle checks retry-time card |
| `test_sequenceproof.py` | Added `test_post_retry_set_card_is_not_a_false_positive` (regression test that failed before fix); added `test_adversarial_cascade_prune_not_reproduced_is_rejected` (invariant lock for cascade-prune → `NOT_REPRODUCED` guard) |
| `docs/BUILD_LOG.md` | This entry |

### Test results

```
Ran 8 tests in 0.039s
OK
```

Unit suite: 8/8 pass.

API suite (4 scenarios via in-process server):
- `POST /api/analyze` with default SAMPLE → `REPRODUCED`, 12→4 steps, 5/5 trials, `fixed_passes=True` ✓
- Protocol-invalid trace (`retry_payment` alone) → `INVALID_TRACE` ✓
- Non-reproducing trace (no card switch before retry) → `NOT_REPRODUCED` ✓
- Adversarial trace (post-retry `set_card`) → `NOT_REPRODUCED`, `failure_id=None` ✓

### Remaining limitations (superseded by next entry)

- One deterministic, synthetic checkout protocol.
- Local reduction with a finite search budget; no global-minimum claim.
- ~~The oracle detects only the last `retry_payment` state~~ — fixed in the
  next entry by the per-attempt list.
- No measured comparison with manual debugging yet.
- IBM Bob is used in the engineering workflow and evidenced separately; the
  app does not claim a live Bob inference API.

---

## 2026-09-27 — per-attempt oracle: multi-retry false-negative fix

### Original final-state false positive (from previous entry)

The initial oracle compared `charged_card != state.card` at **trace end**.
A `set_card` after a correct retry drifted the final card value, firing
`WRONG_CARD_CHARGED` when the charge was correct.  Fixed in the previous
entry by recording `card_at_retry` at retry time and comparing against it.

### Multiple-retry false negative (this entry)

The previous fix used two scalars (`charged_card`, `card_at_retry`) that
were **overwritten** on each `retry_payment`.  The oracle therefore saw only
the **last** retry attempt.

Counter-example that exposed the gap:

```
add_item(pen)
begin_checkout          # pending_card = card-A
set_card(card-B)
retry_payment           # charges card-A; expected card-B → WRONG
set_card(card-A)
retry_payment           # charges card-A; expected card-A → CORRECT
```

Before this fix: `card_at_retry = card-A`, `charged_card = card-A` after the
second (correct) retry → oracle reported `NOT_REPRODUCED`.  The first wrong
charge was silently hidden.

### Per-attempt solution

Replaced `charged_card: str | None` and `card_at_retry: str | None` in
`Checkout` with a single `retry_attempts: list[dict[str, str]]` field
(default empty list, via `field(default_factory=list)`).

Every `retry_payment` appends `{"expected": self.card, "actual": charged}`
to the list — one record per attempt, in order, never overwritten.

`replay()` iterates the list and reports the **first** entry where
`actual != expected`.  If every entry matches, the trace is `NOT_REPRODUCED`.
The `expected` / `actual` keys in the response always come from the first
mismatch, which is the semantically correct failure point.

Event logging now reads `state.retry_attempts[-1]["actual"]` for the
`charged_card` column — identical to what the scalar provided for the last
step, so the frontend event table is unaffected.

### Observed after fix

| Trace | Before | After |
| --- | --- | --- |
| First retry wrong, second correct | `NOT_REPRODUCED` (false negative) | `REPRODUCED / WRONG_CARD_CHARGED` |
| Post-retry `set_card` (false positive) | `NOT_REPRODUCED` ✓ | `NOT_REPRODUCED` ✓ |
| Multiple correct retries | `NOT_REPRODUCED` ✓ | `NOT_REPRODUCED` ✓ |
| Default SAMPLE (12→4) | `REPRODUCED` ✓ | `REPRODUCED` ✓ |
| Corrected-implementation pass | `True` ✓ | `True` ✓ |
| Multi-retry fixed path | `True` ✓ | `True` ✓ |

### Changed files

| File | Change |
| --- | --- |
| `sequenceproof.py` | Replaced `charged_card` + `card_at_retry` scalars with `retry_attempts` list; oracle iterates attempts; event log uses last attempt's `actual` |
| `test_sequenceproof.py` | Added `test_earlier_wrong_retry_is_not_hidden_by_later_correct_retry`; added `test_multiple_correct_retries_do_not_reproduce`; preserved all 8 prior tests |
| `docs/BUILD_LOG.md` | This entry |

### Test results

```
Ran 10 tests in 0.022s
OK
```

Unit suite: 10/10 pass.

API suite (5 scenarios via in-process server):
- `POST /api/analyze` with default SAMPLE → `REPRODUCED`, 12→4 steps, 5/5 trials, `fixed_passes=True` ✓
- Protocol-invalid trace (`retry_payment` alone) → `INVALID_TRACE` ✓
- Non-reproducing trace (no card switch before retry) → `NOT_REPRODUCED` ✓
- Adversarial trace (post-retry `set_card`) → `NOT_REPRODUCED`, `failure_id=None` ✓
- Multi-retry trace (first wrong, second correct) → `REPRODUCED`, `expected=card-B`, `actual=card-A`, `fixed_passes=True` ✓

### Remaining genuine limitations

- One deterministic, synthetic checkout protocol; no generalization to other
  state machines.
- Local reduction with a finite search budget; no global-minimum claim.
- Only the **first** wrong attempt in `retry_attempts` is surfaced in the
  report; later wrong attempts are present in the list but not individually
  reported.  This is sufficient for the current single-session contract.
- No measured comparison with manual debugging time.
- IBM Bob is used in the engineering workflow and evidenced separately; the
  app does not claim a live Bob inference API.

