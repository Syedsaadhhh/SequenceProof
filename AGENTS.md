# SequenceProof build rules

## Product contract

SequenceProof reduces a valid, stateful action trace only when a fresh replay
still produces the exact original failure ID. The corrected implementation is
then checked with the same reduced trace.

## Commands

```bash
python -m unittest -v
python server.py
```

The local app is available at `http://127.0.0.1:8000`.

## Non-negotiable behavior

- Start every candidate replay from fresh state.
- Never count an invalid candidate as reproduction evidence.
- Preserve the exact `WRONG_CARD_CHARGED` failure ID during reduction.
- Do not insert or reorder actions while pruning.
- Keep analysis bounded: 40 input actions, 32 KiB request, 250 checks.
- Keep passing, invalid, reproduced, and flaky outcomes distinct.
- Do not hardcode a successful UI result.
- Use only owned synthetic traces and fictional card identifiers.
- Describe the output as locally reduced; do not claim global minimality.

## Definition of done for changes

1. Add a test that would fail without the behavior being introduced or fixed.
2. Run the full unit test suite.
3. Exercise the actual API for success and negative cases when its contract changes.
4. Record material design decisions in `docs/BUILD_LOG.md`.
5. Preserve real IBM Bob task summary screenshots in `bob_sessions/`.

