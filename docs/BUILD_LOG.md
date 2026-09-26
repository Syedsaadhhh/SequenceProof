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

### Current limits

- One deterministic, synthetic checkout protocol.
- Local reduction with a finite search budget; no global-minimum claim.
- No measured comparison with manual debugging yet.
- IBM Bob is used in the engineering workflow and evidenced separately; the app
  does not claim a live Bob inference API.

