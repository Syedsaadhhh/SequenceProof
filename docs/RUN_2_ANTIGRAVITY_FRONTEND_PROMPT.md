# Antigravity Run 2 — Master Frontend

Paste everything below into Google Antigravity Agent mode after synchronizing the repository and creating the branch `antigravity/run-2-master-frontend`.

---

Read `AGENTS.md`, `README.md`, `index.html`, `server.py`, `sequenceproof.py`, `test_sequenceproof.py`, `docs/ARCHITECTURE.md`, `docs/BUILD_LOG.md`, and `docs/SEQUENCEPROOF_UI_UX_DESIGN_SYSTEM.md` before editing. Treat the design-system file as the detailed visual and data-binding authority for this run.

## Mission

Turn the current working SequenceProof page into a judge-ready, enterprise-grade proof interface whose value is understandable in under 10 seconds:

**12 noisy actions → 4-step executable proof → exact failure confirmed 5/5 → corrected implementation passes.**

This is a frontend/product-clarity run. Preserve the verified Run 1 backend behavior and API contract.

## Product truth that must remain visible

SequenceProof reduces a valid stateful action trace only when a fresh replay preserves the exact original failure ID. It then replays the same reduced trace against corrected behavior.

The default sample must continue to show:

- original trace: 12 actions
- locally reduced trace: 4 actions
- failure ID: `WRONG_CARD_CHARGED`
- five fresh confirmations: 5/5
- corrected implementation: does not reproduce
- only synthetic card identifiers and owned sample data

Never claim global minimality, measured developer time savings, arbitrary-repository support, production payment integration, or a live IBM Bob runtime API.

## Visual direction

Create a restrained dark enterprise interface: Linear/Vercel/Palantir-level clarity, not cyberpunk.

- near-black/navy surfaces
- subtle borders and layered panels
- white and cool-gray typography
- restrained teal for verified proof
- restrained amber/coral for the observed failure
- minimal gradients, no neon glow, no decorative 3D
- strong spacing, typography, alignment, and information hierarchy
- responsive at desktop, tablet, and mobile widths
- respect `prefers-reduced-motion`
- accessible focus states, labels, contrast, and keyboard behavior

Do not imitate IBM branding or place IBM logos in the product UI.

## Required information architecture

### 1. Compact top bar

Show:

- SequenceProof wordmark
- “Executable stateful debugging” descriptor
- local/synthetic sample badge
- a small neutral indicator that analysis is bounded

### 2. Ten-second hero

The first viewport must immediately communicate:

- headline: turn a long stateful failure into a short verified reproduction
- a compact visual equation or result strip: `12 actions → 4 proof steps → 5/5 confirmed → fix passes`
- one primary action: **Analyze trace**
- one secondary action: **Reset sample**

Do not display successful result values as fake live output before the API returns. Before analysis, label them clearly as the sample goal or preview. After analysis, populate them exclusively from the real response.

### 3. Trace workspace

Replace the “large JSON box as the whole product” feeling with a serious debugging workspace:

- an editable JSON trace remains available
- also render a readable numbered action timeline from the current JSON
- show validation errors near the editor
- provide a compact sample issue statement
- keep the workflow usable without hiding the actual input

### 4. Analysis progress

During the real API request, show a compact staged progression:

1. Validate trace
2. Replay from fresh state
3. Reduce valid candidates
4. Confirm exact failure
5. Check corrected behavior

This may be a deterministic UI progress treatment while the request is pending, but do not fabricate backend results or timings.

### 5. Verified result — the main wow moment

For a real `REPRODUCED` response, the result area must prominently show:

- `12 → 4`
- exact failure ID
- 5/5 confirmation indicator derived from `trials`
- corrected implementation pass/fail derived from `fixed_passes`
- percentage reduction derived from response lengths
- candidate checks, orphan steps pruned, and duration from the response

Add a compact “failure moment” card derived from the response:

- expected card
- actually charged card
- event-time explanation
- emphasize that the comparison is made at retry time

### 6. Original versus reduced proof

Build a clear side-by-side comparison:

- original timeline with removed noise visually de-emphasized
- reduced timeline with retained steps emphasized
- connecting visual relationship or shared numbering where helpful
- never claim the reducer inserted or reordered an action
- on small screens, stack the timelines without losing meaning

### 7. Proof drawer

Provide an expandable proof/evidence area containing real response data:

- original status and failure ID
- five trial outcomes
- corrected result
- original replay events
- download-proof JSON action
- plain-language scope note: locally reduced, bounded, synthetic sample

### 8. Honest negative states

Create equally polished states for:

- `INVALID_TRACE`
- `NOT_REPRODUCED`
- `FLAKY`
- network/server error
- malformed editor JSON

Never render “verified” styling for a negative or invalid outcome.

## Engineering constraints

- Keep the zero-dependency Python backend.
- Prefer improving `index.html` without introducing a frontend build system.
- Preserve `GET /api/sample` and `POST /api/analyze`.
- Do not modify reduction/oracle semantics during this run.
- Do not hardcode a successful API result.
- Escape all user-controlled strings before inserting HTML.
- Keep the 32 KiB request and 40-step limits.
- Do not touch, stage, or commit any unrelated untracked file named `ss`.
- Do not remove `bob_sessions/` or alter IBM Bob evidence.
- Do not commit, push, merge, or deploy. Leave reviewed working-tree changes for inspection.

## Verification

Complete all of the following:

1. Run `python -m unittest -v`; all 10 existing tests must pass.
2. Start `python server.py`.
3. Exercise the actual browser UI with the default sample.
4. Confirm the UI displays the real 12→4 result, exact `WRONG_CARD_CHARGED` ID, 5/5 trials, and corrected pass.
5. Test malformed JSON.
6. Test a protocol-invalid trace.
7. Test a valid non-reproducing trace.
8. Check desktop, tablet, and mobile layouts.
9. Check keyboard focus and browser console errors.
10. Update `docs/BUILD_LOG.md` with only observed Run 2 results and design decisions.

## Final response

Report:

- changed-file list
- exact test output
- browser scenarios exercised
- any accessibility or responsive checks
- what is derived from the API versus static explanatory copy
- remaining limitations

Do not claim completion for any check that was not actually performed.
