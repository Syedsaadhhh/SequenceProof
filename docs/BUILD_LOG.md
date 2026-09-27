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

---

## 2026-09-27 — Run 2: Master frontend & UI/UX design system implementation

### Scope and objective

Execute the entire Run 2 specification from `docs/RUN_2_ANTIGRAVITY_FRONTEND_PROMPT.md`
and `docs/SEQUENCEPROOF_UI_UX_DESIGN_SYSTEM.md`: turn the SequenceProof interface
into an enterprise-grade proof surface delivering the core value in under 10 seconds:
`12 noisy actions → 4-step executable proof → exact failure confirmed 5/5 → corrected implementation passes.`

### Material design decisions

1. **Restrained Enterprise Dark Visual Language:**
   - Implemented exact `--sp-` tokens from Section 13 (canvas `#080b10`, surface `#0f141b`, raised `#151c25`, interactive `#1b2430`, teal accent `#67d4c1`, coral failure `#f59e72`, green success `#63d49c`, warning `#f3c969`, error `#f47c7c`).
   - Zero external CDNs, Google Fonts, or icon libraries; native system font stacks (`Inter, ui-sans-serif...` and monospace `ui-monospace, SFMono-Regular...`) and accessible inline SVGs only.
   - Restrained styling: no cyberpunk aesthetic, neon glows, floating cards, or 3D decorations.

2. **Strict Dynamic Data Binding (No Hardcoded Successes):**
   - All results, metrics, failure IDs, trial counts, and failure moments are dynamically computed from `POST /api/analyze` response data.
   - Initial Hero strip clearly labels 12→4 as `Sample outcome preview (pending execution)`. Real metrics populate only upon receiving a verified API response.
   - Failure moment card extracts `original.expected` (`card-B`) and `original.actual` (`card-A`) dynamically; omitted cleanly if missing.
   - Confirmation strip renders dynamic cells strictly based on returned `trials` array (requiring matching status and exact `failure_id`).
   - Corrected implementation callout dynamically reads `fixed_passes` and `fixed_result.detail`.
   - Download proof JSON dynamically serializes the latest `/api/analyze` response into `sequenceproof-evidence.json`.

3. **Trace Workspace & Dual-View Interaction:**
   - Displays issue statement dynamically fetched from `GET /api/sample`.
   - Segmented tab control provides both a readable numbered timeline with action badges and an editable monospace JSON editor.
   - Real-time client-side JSON validation updates action counts, sets `aria-invalid`, and displays inline error messages.
   - `Ctrl + Enter` (and `Cmd + Enter`) keyboard shortcut triggers analysis from anywhere in the document.

4. **Honest Explanatory Pending Progression:**
   - Pending state displays five clear stages (Validate trace, Replay from fresh state, Reduce valid candidates, Confirm exact failure, Check corrected behavior) with `aria-busy="true"` and disabled buttons.
   - No fake percentages, simulated timers, or synthetic candidate counts. Animation halts immediately upon API return.

5. **Ordered Subsequence Timeline Comparison:**
   - Subsequence matching algorithm walks `original_steps` and `reduced_steps` in order without backtracking or reordering.
   - Retained actions receive high-contrast proof styling (`#bbf3e7` and teal border); pruned noise steps are visually struck out with reduced opacity.

6. **Honest Negative & Error States:**
   - Built dedicated states for `INVALID_TRACE`, `NOT_REPRODUCED`, `FLAKY`, malformed JSON, and network/server errors.
   - Negative states never display reduction metrics, 12→4 equations, green verified styling, or 5/5 confirmations.

7. **Responsive & Accessible Foundation:**
   - Desktop: 42% trace workspace / 58% proof workspace split (`1380px` max width).
   - Tablet: Single-column stacked layout preserving panel hierarchy.
   - Mobile (<720px): Single-column layout adhering strictly to the Section 15 12-item ordering, with 0 horizontal page overflow (`scrollWidth <= clientWidth`).
   - Accessibility: Semantic headings, scoped `aria-live="polite"` announcer, visible `:focus-visible` outlines, and full `prefers-reduced-motion` compliance.

### Changed files

| File | Change |
| --- | --- |
| `index.html` | Complete Run 2 master frontend implementation adhering to UI/UX design system |
| `docs/BUILD_LOG.md` | This entry |

### Verification results

Unit test suite (`python -m unittest -v`):
```
Ran 10 tests in 0.019s
OK
```
10/10 tests pass.

Automated browser CDP verification suite (headless Chrome, 43 checks across 8 scenarios):
1. **Initial load & sample data binding:** Page title, issue text from `/api/sample`, initial "Ready" phase badge, sample outcome preview strip, 12 readable timeline actions, and 12 JSON steps in editor verified.
2. **Default sample analysis (12→4 verified):** Pending stages displayed with `aria-busy="true"`, "Verified" badge on response, `12 actions → 4 proof steps` equation, `67% fewer steps` reduction pill, live verified hero strip, `WRONG_CARD_CHARGED` badge, failure moment (`expected=card-B`, `actual=card-A`), 5/5 fresh confirmations, corrected behavior verdict passing, 12 original steps (4 retained, 8 pruned), 4 reduced proof steps, 12 events in replay table, and JSON download button verified.
3. **Malformed editor JSON:** Inline error banner, `aria-invalid="true"`, zero network requests sent to `/api/analyze`, and "JSON needs correction" error card verified.
4. **Protocol-invalid trace (`retry_payment` alone):** Server returns `INVALID_TRACE`, UI renders "Invalid trace" with protocol detail, no reduction metrics or 12→4 shown.
5. **Valid non-reproducing trace:** Server returns `NOT_REPRODUCED`, UI renders "Target failure not reproduced", no verified green badge.
6. **Reset sample:** Textarea reset to 12 steps, timeline refreshed, phase badge restored to "Ready", ready state view restored.
7. **Responsive viewports:** Verified desktop (1280px), tablet (820px), and mobile (375px) with strictly no horizontal page scrolling.
8. **Accessibility & keyboard navigation:** `aria-live="polite"` announcer verified, `Ctrl+Enter` shortcut verified, and 0 browser console errors recorded.

Result: 43 Passed, 0 Failed across all scenarios.

### Remaining limitations

- Prototype operates on one deterministic synthetic checkout state machine (`sequenceproof.py`).
- Reduction search is bounded to ≤40 steps and ≤250 checks; results are locally reduced rather than globally minimal.
- IBM Bob is utilized within the developer engineering workflow and evidenced in `bob_sessions/`; no runtime Bob API exists.

---

## 2026-09-27 — Run 2.1: Evidence-hardening and interaction verification pass

### Scope and objective

Execute the bounded Run 2.1 evidence-hardening pass on branch `antigravity/run-2-master-frontend`. Remove misleading pre-execution claims, eliminate simulated pending timers/percentages, gracefully detect ambiguous subsequence mappings when identical actions repeat, clarify the failure oracle's first-mismatch reporting limitation, harden accessibility and responsive behaviors, and capture real headless Chrome application screenshots into `docs/screenshots/`.

### Hardened corrections and implementation details

1. **Elimination of Pre-Execution Success Claims:**
   - Replaced initial equation strip and ready card with a neutral, honest workflow preview: *"Ready to verify this trace · Fresh-state replay · Exact failure identity · Fix verification"*.
   - Ensured no claims of `12 → 4`, `4 proof steps`, `5/5 confirmed`, `WRONG_CARD_CHARGED`, or `fix passes` appear anywhere before the user executes the trace and receives a real API response.
   - Restoring/resetting the trace faithfully returns the hero strip and ready state to this neutral workflow state.

2. **Honest, Educational Pending Progression:**
   - Removed all artificial timers (`setInterval`), fake progress percentages, and simulated step cycling.
   - Replaced with a single honest status title: `Analyzing trace…` and an informative 5-step checklist representing the deterministic pipeline (Validate trace, Replay from fresh state, Reduce valid candidates, Confirm exact failure, Check corrected behavior).
   - Analysis executes asynchronously and renders verified results immediately when the real API responds.

3. **Conservative Subsequence Ambiguity Handling:**
   - Implemented `checkSubsequenceAlignment(origSteps, redSteps)` which computes all valid ordered subsequence embeddings.
   - If multiple valid embeddings exist due to identical repeated actions (e.g. repeated `add_item(notebook)` before checkout), the UI displays an explicit warning note: *"Original-row alignment is ambiguous because identical actions repeat. Showing original trace and verified reduced sequence separately without claiming specific row provenance."*
   - Avoids false row-level provenance badges (`retained`) on ambiguous original rows while keeping the verified reduced steps cleanly highlighted.

4. **Failure Oracle Limitation Clarification:**
   - Embedded the required clarification copy verbatim in both the failure moment card and the replay event log footnote:
     > *"The summary reports the first mismatching retry. Later attempts remain available in the replay event log."*
   - Clarifies why only the first mismatch is surfaced in the primary card while ensuring full attempt history remains accessible.

5. **Accessibility & Interaction Hardening:**
   - Programmatic focus transfer: Active focus transfers smoothly to the `.result-view` container with `tabindex="-1"` and `.focus()` upon receiving analysis results.
   - Double-submission guard: Analysis triggers (`run-btn`, `hero-analyze-btn`, and `Ctrl+Enter` / `Cmd+Enter`) are guarded by `isAnalyzing` to prevent duplicate concurrent API requests.
   - Screen reader error binding: Monospace editor links directly to inline error notices via `aria-describedby="editor-error-msg"` whenever `aria-invalid="true"`.
   - Mobile touch targets: Added explicit `min-height: 44px` rule to all action buttons (`.btn` and `.tab-btn`) on mobile viewports (<720px) to comply with accessibility touch target sizing.

6. **Comprehensive Responsive & Viewport Verification:**
   - Desktop (1280x800): Verified two-column layout (42% / 58%) with no horizontal scroll.
   - Tablet (820x1180): Verified responsive stacked layout with intact card hierarchy and no horizontal scroll.
   - Mobile (375x667): Verified single-column stacked layout with 0 horizontal page overflow (`document.body.scrollWidth <= window.innerWidth`).
   - Small Mobile (320x568): Verified layout down to 320px with 0 horizontal scroll.
   - Desktop 200% Zoom (640x400 layout): Verified graceful responsive wrapping with 0 horizontal overflow.

7. **Captured Real Application Screenshots:**
   - Captured real PNG screenshots using Chrome DevTools Protocol (CDP) into `docs/screenshots/`:
     - `docs/screenshots/run2-desktop-verified.png` (1280x800 desktop verified state)
     - `docs/screenshots/run2-mobile-verified.png` (375x667 mobile verified state)
     - `docs/screenshots/run2-negative-state.png` (desktop malformed JSON error state)

### Changed files

| File | Change |
| --- | --- |
| `index.html` | Removed pre-execution claims, streamlined pending progression, added subsequence ambiguity detection and notice, added oracle limitation copy, hardened mobile touch targets (≥44px), added programmatic focus management, and connected `aria-describedby` for editor errors. |
| `docs/screenshots/run2-desktop-verified.png` | Real headless Chrome application screenshot of desktop verified state (37,483 bytes) |
| `docs/screenshots/run2-mobile-verified.png` | Real headless Chrome application screenshot of mobile verified state (27,116 bytes) |
| `docs/screenshots/run2-negative-state.png` | Real headless Chrome application screenshot of negative error state (22,893 bytes) |
| `docs/BUILD_LOG.md` | This Run 2.1 entry documenting all hardened corrections, verified checks, and limitations. |

### Verification results

1. **Python Unit Suite (`python -m unittest -v`):**
   ```
   test_adversarial_cascade_prune_not_reproduced_is_rejected ... ok
   test_deleted_parent_prunes_orphan_but_never_invents_steps ... ok
   test_earlier_wrong_retry_is_not_hidden_by_later_correct_retry ... ok
   test_invalid_or_passing_trace_cannot_fake_bug ... ok
   test_multiple_correct_retries_do_not_reproduce ... ok
   test_post_retry_set_card_is_not_a_false_positive ... ok
   test_reduction_accepts_valid_repaired_candidate ... ok
   test_repair_does_not_hide_bad_parameters_or_make_a_bug ... ok
   test_sample_reduction_preserves_exact_failure ... ok
   test_second_trace_is_computed ... ok

   Ran 10 tests in 0.019s
   OK
   ```
   10/10 tests pass.

2. **Automated Verification Suite (`run_2_1_verification.js`, 38 checks across 9 categories):**
   - API Verification: `GET /api/sample` (12 actions), `POST /api/analyze` default (12→4, `WRONG_CARD_CHARGED`, 5/5 trials, fixed passes), protocol-invalid (`INVALID_TRACE`), non-reproducing (`NOT_REPRODUCED`), payload size boundary (>32 KiB returns HTTP 413).
   - Pre-Execution Neutrality: No 12→4, 5/5, or failure IDs before execution; neutral ready state and workflow caption.
   - Honest Pending State: Title is "Analyzing trace…", static 5-step checklist, 0 fake percentages.
   - Real Analysis: Verified badge, real API values in hero strip, exact failure moment, oracle copy, programmatic focus to result container.
   - Ambiguity Detection: Ambiguity notice rendered for duplicate actions, no false row-level retained badges.
   - Negative Handling: `aria-invalid="true"`, `aria-describedby="editor-error-msg"`, editor contents preserved, negative error card displayed.
   - Reset Behavior: Restores neutral ready state and "Ready" phase badge.
   - Responsive & Overflow: 1280x800, 820x1180, 375x667, 320x568, and 200% zoom all report 0 horizontal overflow.
   - Accessibility & Cleanliness: Mobile touch targets ≥44px, `Ctrl+Enter` triggers analysis, 0 browser console errors.
   - Result: 38 Passed, 0 Failed.

### Genuine limitations

#### Prototype Boundaries
- **Single Synthetic Protocol:** Engine evaluates a dedicated e-commerce checkout state machine defined in `sequenceproof.py` (cart items, cards, payment retries); it does not parse generic arbitrary application protocols.
- **Locally Reduced Traces:** Trace reduction utilizes bounded delta-debugging (≤40 steps, ≤250 candidate checks); results represent verifiable local reductions rather than provable global minima.
- **Workflow-Embedded IBM Bob:** IBM Bob was used as part of the human-in-the-loop agentic workflow and recorded in `bob_sessions/`; there is no live remote IBM Bob API endpoint integrated into the client application.

#### Technical Debt
- **Single-File Frontend (`index.html`):** The entire application (HTML, CSS, SVGs, and JavaScript) is packaged in a single 2,450-line file without external bundling or module separation.
- **First Mismatch Oracle Surface:** The failure oracle captures all retry attempts, but the top-level API payload surfaces the expected/actual values of the first mismatching attempt; later attempts must be inspected via the replay event log.

---

## 2026-09-27 — Run 2.2: limitation-closure pass

### Closed engineering limitations

1. **Frontend monolith removed:** `index.html` is now the semantic shell,
   `static/styles.css` owns the visual system, and `static/app.js` owns API,
   state, validation, and rendering logic. `server.py` exposes only an exact
   allowlist of those assets and does not expose source files or directory
   traversal paths.
2. **Complete retry evidence:** every retry attempt receives an attempt number
   and trace-step index. The replay response includes `retry_attempts`, the
   complete `mismatches` list, and `mismatch_count`. Compatibility fields
   `expected` and `actual` still reference the first mismatch so existing
   clients remain valid. The UI now lists every mismatch rather than directing
   users to infer later failures from event history.
3. **Precise minimality evidence:** the bounded reducer now performs a final
   single-deletion certificate pass inside the same 250-check budget. A
   certified result means no one retained step can be removed, including
   consequent orphan pruning, while preserving the exact failure ID. The API
   explicitly returns `one-minimal` or `bounded-local`; it never claims global
   minimality.
4. **Accurate event history:** charged and expected cards appear only on actual
   `retry_payment` events. Later unrelated events no longer inherit the last
   charge and therefore cannot be visually misclassified as additional
   mismatches.
5. **Reduced-motion behavior hardened:** the interface removes the decorative
   spinner and short transitions without globally destroying useful state
   feedback.

### Changed files

| File | Change |
| --- | --- |
| `index.html` | Reduced to the semantic shell and external asset references |
| `static/styles.css` | Extracted visual system plus mismatch and reduced-motion styles |
| `static/app.js` | Extracted interaction layer; complete mismatch and minimality rendering |
| `server.py` | Exact static-asset allowlist and `nosniff` responses |
| `sequenceproof.py` | Complete retry evidence and bounded one-minimal certificate |
| `test_sequenceproof.py` | Regression coverage for all mismatches, event accuracy, and certificate |
| `test_server.py` | Asset-serving, source-exposure, and API-contract coverage |
| `README.md` | Updated contract and repository map |
| `docs/ARCHITECTURE.md` | Updated component and proof flow |
| `docs/BUILD_LOG.md` | This observed limitation-closure entry |

### Observed verification

`python -m unittest -v` completed with **16 tests passing**. The default owned
sample remains `12 actions → 4 proof steps`, preserves
`WRONG_CARD_CHARGED` in all **5/5** fresh confirmation runs, and the corrected
implementation passes. The complete run used 35 candidate checks and returned:

```json
{
  "kind": "one-minimal",
  "certified": true,
  "checks": 4
}
```

The multi-retry API regression exposes both mismatches in attempt and trace
order. HTTP tests confirm `/`, `/static/styles.css`, and `/static/app.js` load,
while `/server.py` returns 404. `node --check static/app.js` also passes.

### Deliberate product boundaries—not unresolved defects

- SequenceProof intentionally proves one narrow, owned checkout protocol; it
  does not execute arbitrary repositories or untrusted third-party code.
- Search remains bounded to 40 actions and 250 candidate checks. The product
  reports a precise one-minimal certificate when completed and otherwise
  labels the result `bounded-local`; it never claims a global minimum.
- IBM Bob is the required implementation and review workspace evidenced in
  `bob_sessions/`. No live Bob runtime API is claimed or fabricated.


---

## 2026-09-27 — Run 2.5: Real-repository sandbox kernel

### Scope

Turn SequenceProof from a checkout-specific demonstration into a real execution
system that can reduce a trace against any public repository that opts in with a
manifest and runner.

### Material design decisions

1. **Protocol-agnostic core (`core.py`):** The ddmin kernel, confirmation, and
   one-minimal certificate are extracted into `core.py` which contains zero
   checkout/access action names and zero hardcoded failure IDs — verified by test.
   `sequenceproof.py` bridges to it through a domain-specific oracle closure.

2. **Runner contract (`runner_contract.py`):** Strict manifest/job-request/runner-output
   models with pure-Python validation. Shell strings, extra keys, path traversal,
   mutable refs, non-GitHub URLs, and malformed SHAs are all rejected with
   clear error messages.

3. **SandboxProvider protocol (`sandbox/base.py`):** Clean interface with
   `SandboxInfo`, `SandboxResult`, `SandboxUnavailableError`. All providers
   implement this interface; the kernel never calls provider-specific code.

4. **FakeSandboxProvider (`sandbox/fake_provider.py`):** Runs actual local
   subprocesses (not mocks) in a temp directory seeded with the fixture tree.
   Never selectable via HTTP. This gives real process coverage for all 82 tests.

5. **Daytona provider (`sandbox/daytona_provider.py`):** Uses the official
   `daytona` SDK, reads `DAYTONA_API_KEY` from the server environment, never
   exposes it to sandbox code. Returns `available=False` when SDK is missing
   or key is not set.

6. **Docker provider (`sandbox/docker_provider.py`):** Clones on host,
   executes with `--network none --read-only --user 1000 --cpus 0.5 --memory 256m --pids-limit 64`.
   Returns `available=False` when Docker is absent. No `shell=True` anywhere.

7. **stale-role-service fixture (`examples/stale-role-service/`):** Real
   executable Python service with a stale-snapshot authorization bug. Includes
   buggy and fixed implementations, a v1 runner, manifest, noisy/non-reproducing/
   invalid traces, and runner unit tests. The noisy trace reduces from 12 to
   3 steps.

8. **repository_runner.py:** Coordinates the full lifecycle (create, clone, manifest
   load, original replay, reduction, confirmation, fix-check, destroy). Calls
   `git reset --hard HEAD` and `git clean -fdx` before every runner invocation to
   enforce the fresh-execution invariant.

9. **jobs.py:** Bounded in-memory store (20 jobs, 1h TTL, 1 active job limit).
   Every phase transition records a timestamp and detail dict from real backend
   callbacks. No manufactured percentage progress.

10. **server.py additions:** `GET /api/sandbox/providers`, `POST /api/jobs` (202),
    `GET /api/jobs/{id}`, `DELETE /api/jobs/{id}`. `FakeSandboxProvider` is
    explicitly excluded from the production provider map. Invalid job requests
    return `400 INVALID_REQUEST`; full queue returns `429 QUEUE_FULL`.

11. **sequenceproof.py refactor:** The original trace is still checked directly
    with `replay()` (no orphan-pruning applied) to preserve `INVALID_TRACE`
    semantics. Only candidates pass through the pruning oracle. The module-level
    doc now explicitly labels this as "not the product".

### Changed files

| File | Change |
| --- | --- |
| `core.py` | New — protocol-agnostic bounded ddmin with one-minimal certificate |
| `runner_contract.py` | New — strict manifest/job/runner-output validation |
| `sandbox/__init__.py` | New — package marker |
| `sandbox/base.py` | New — SandboxProvider protocol |
| `sandbox/fake_provider.py` | New — local-subprocess test provider |
| `sandbox/daytona_provider.py` | New — Daytona SDK provider |
| `sandbox/docker_provider.py` | New — Docker local provider |
| `examples/stale-role-service/service_buggy.py` | New — buggy auth service |
| `examples/stale-role-service/service_fixed.py` | New — corrected auth service |
| `examples/stale-role-service/sequenceproof_runner.py` | New — v1 runner |
| `examples/stale-role-service/.sequenceproof/manifest.json` | New — manifest |
| `examples/stale-role-service/traces/noisy_reproducing.json` | New |
| `examples/stale-role-service/traces/non_reproducing.json` | New |
| `examples/stale-role-service/traces/invalid_no_account.json` | New |
| `examples/stale-role-service/test_runner.py` | New — runner unit tests |
| `repository_runner.py` | New — orchestration layer |
| `jobs.py` | New — bounded job store |
| `server.py` | Added sandbox job API endpoints |
| `sequenceproof.py` | Delegated reduction to `core.py`; labeled as preview |
| `test_kernel.py` | New — 16-category regression tests |
| `README.md` | Updated with honest Run 2.5 positioning |
| `docs/ARCHITECTURE.md` | Updated with full system architecture |
| `docs/RUNNER_CONTRACT.md` | New — repository opt-in contract |
| `.env.example` | New — environment variable template |
| `docs/BUILD_LOG.md` | This entry |

### Observed verification

```
python -m unittest -v
Ran 82 tests in 140s
OK
```

82/82 tests pass. No new warnings.

```
python -m compileall -q .
```
No output — all modules compile clean.

```
node --check static/app.js
```
No output — JS syntax valid.

### API exercise results

```
GET  /api/sample                         200  trace_len=12
GET  /api/sandbox/providers              200  [('daytona', False), ('docker', False)]
POST /api/analyze (sample)               200  REPRODUCED  12→4  certified=True
POST /api/analyze (invalid trace)        200  INVALID_TRACE
POST /api/jobs (invalid URL)             400  INVALID_REQUEST
POST /api/jobs (mutable SHA)             400  INVALID_REQUEST
POST /api/jobs (valid, no sandbox)       202  → FAILED  SANDBOX_UNAVAILABLE
GET  /api/jobs/{id}                      200  phase=FAILED
DELETE /api/jobs/nonexistent             404
POST /api/analyze oversized body         413
GET  /                                   200  HTML
GET  /server.py                          404
```

### stale-role-service fixture reduction (FakeSandboxProvider)

The `TestRepositoryReduction.test_full_reduction_with_fake_provider` test
ran the noisy 12-step trace through the full kernel:

- Original trace: 12 actions
- Failure ID learned: `STALE_ROLE_AUTHORIZATION`
- Reduced trace: 3 actions (switch_account alice/admin, switch_account bob/viewer, perform_action)
- Confirmations: 5/5 REPRODUCED with STALE_ROLE_AUTHORIZATION
- Fixed result: NOT_REPRODUCED
- Minimality: one-minimal (certified)

### Real E2E status

**REAL SANDBOX E2E BLOCKED**

Missing prerequisites:
- Docker is not installed on this host (`docker` not in PATH).
- Daytona SDK is not installed (`pip install daytona` required) and `DAYTONA_API_KEY` is not set.

All sandbox functionality is exercised through `FakeSandboxProvider` which
runs real subprocesses locally. The provider layer is fully implemented for
both Daytona and Docker and will execute against real sandboxes when the
prerequisites are met. No mock result was substituted.

### Remaining genuine limitations

- v1 supports public GitHub HTTPS repositories only.
- No setup commands in v1 (no `pip install`, `npm install`, etc. in the manifest).
- The `_exec_runner` git reset commands are fire-and-forget for the FakeSandboxProvider
  (no git repo in the temp dir); this is correct because the fake provider's temp dir
  has no git history to reset. The invariant is enforced by fresh temp directories.
- Daytona network isolation and Docker resource limits depend on the respective
  cloud/host environments and cannot be fully verified locally.
- One concurrent job limit in this prototype.


## 2026-09-27 — Run 2.5 real Daytona activation (post-Bob)

This section supersedes the earlier "REAL SANDBOX E2E BLOCKED" prerequisite status.

### Environment and SDK

- User-scoped `DAYTONA_API_KEY` was present; its value was never printed, logged, or committed.
- Installed CPython 3.13.13 and `daytona==0.218.0` in `C:\Users\ATEC\.sequenceproof-tools\daytona-venv`, outside the repository.
- Real SDK smoke sandbox `139c90f2-e06c-406b-94fd-9fd9073f501d` executed `SEQUENCEPROOF_DAYTONA_OK` with exit 0 and was destroyed.
- Path probe sandbox `e7fe7195-4524-4653-892b-f3473f203da4` proved the writable home is `/home/daytona`; it was destroyed.

### Integration corrections

- Updated `DaytonaSandboxProvider` for the Daytona 0.218 API: `CreateSandboxFromSnapshotParams`, `sandbox.process.exec`, `api_url`, bounded timeouts, and auto-delete.
- Changed the repository workspace from nonexistent/unwritable `/workspace/repo` to `/home/daytona/repo`.
- Candidate traces now use `.sequenceproof_runs/`, matching the cleanup exclusion.
- Added a regression proving use of the current sandbox-level SDK surface.

### Real provider verification

- First SequenceProof provider attempt failed honestly with exit 128 because `/workspace/repo` was not writable; no fallback was used.
- Corrected provider sandbox `a7e06e08-31ef-4e39-a976-80bbf91691ff` cloned `https://github.com/octocat/Hello-World`.
- Checked out immutable commit `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`.
- In-sandbox `git rev-parse HEAD` matched the requested SHA exactly; exit 0; cleanup confirmed destroyed.
- Focused provider tests: 4/4 passed.
- Full suite: 83 tests in 60.826s — OK.
- Python compilation and `node --check static/app.js` passed.
- Actual Bob summary screenshot saved at `bob_sessions/sequenceproof_task02_sandbox_kernel_summary.png`.

### Remaining milestone blockers

- The stale-role fixture is still only in the uncommitted private working tree, so Daytona cannot clone it for the full reducer E2E.
- Publishing a minimal public fixture repository and committing/pushing require user authorization.
- Docker Desktop is absent; installation may require administrator consent or a reboot.
- No commit, push, merge, deployment, visibility change, or Docker installation was performed.


## Run 2.5 preliminary live Daytona probe — 2026-09-27

Observed during early provider testing prior to making the primary repository public.
This was an external probe used solely to verify multi-run cloud execution; it is superseded by the official SequenceProof repository execution below.

- External probe fixture: `https://github.com/Syedsaadhhh/credscan-lite` (external test fixture only, not the project repository).
- Immutable commit: `4b40aedaa712357d8ec21d8c7d4336db8f443359`.
- Provider: Daytona; real sandbox ID `31edf2dc-1234-4cf3-8819-f7dcab78252c`.
- Result: verified cloud sandbox execution and cleanup propagation.


---

## Run 2.5 SequenceProof Primary Repository Live Daytona E2E — 2026-09-27

Observed executing against the official SequenceProof repository directly via the root manifest `.sequenceproof/manifest.json`.

- Public execution repository: `https://github.com/Syedsaadhhh/SequenceProof`
- Immutable commit SHA: `afc9aed7e844ac83ff40a101876d3fb16218f2a5`
- Manifest path: `.sequenceproof/manifest.json`
- Provider: Daytona cloud sandbox (`daytona==0.218.0`)
- Job ID: `c0ba7995-5f6e-43d9-86e0-619ce872e83e`
- Disposable sandbox ID: `2288b6fb-4726-40d5-9295-48b92d441b2e`
- Input: 12-step `noisy_reproducing.json` trace
- Backend phases: `QUEUED` → `STARTING_SANDBOX` → `CHECKING_OUT_REPOSITORY` → `REPRODUCING_ORIGINAL` → `REDUCING` → `CONFIRMING` → `VERIFYING_FIXED` → `COMPLETED`
- Learned failure ID: `STALE_ROLE_AUTHORIZATION`
- Reduction result: 12 noisy actions → 3 proof actions:
  1. `{"action": "switch_account", "username": "alice", "role": "admin"}`
  2. `{"action": "switch_account", "username": "bob", "role": "viewer"}`
  3. `{"action": "perform_action", "name": "read_report"}`
- Reduction candidate attempts: 21 candidate evaluations
- Confirmation: 5/5 fresh runs returned `REPRODUCED` with `STALE_ROLE_AUTHORIZATION` across 5 distinct run IDs (`6cbcf6e1-79de-4656-b90f-cbbf3839faab`, `dab0c219-2802-482a-b5e5-8ea2510e4db7`, `e67df546-a73f-4a0d-9ba7-865fda407741`, `9e4d39de-5d80-4760-a7b3-4cb2c5a6cd89`, `7cd102a6-ab72-45a9-abe7-0a7eb5843a22`)
- Corrected implementation: `fixed_passes=true` (returned `status: NOT_REPRODUCED`, run ID `9b168e06-7a71-4a31-992a-6cac8690d801`)
- Bounded one-minimal certificate: certified `true` (3 single-removal checks performed)
- Cleanup: `requested=true`, `confirmed=true`, `detail=null`
- Independent post-run Daytona verification: SDK lookup `client.get('2288b6fb-4726-40d5-9295-48b92d441b2e')` raised `DaytonaNotFoundError` (confirmed completely destroyed).
- Raw evidence file: `docs/RUN2_5_DAYTONA_LIVE_E2E_EVIDENCE.json`
- Full regression suite: 92/92 tests passing in 118.988s.

