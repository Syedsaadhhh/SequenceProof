# SequenceProof Master Frontend UI UX Specification

## Implementation aligned design system for Run 2

**Product:** SequenceProof  
**Audience:** Developers, technical judges, QA engineers, and maintainers debugging stateful failures  
**Current scope:** One owned synthetic checkout protocol served by a zero dependency Python application  
**Core promise:** Reduce a valid stateful trace only when a fresh replay preserves the exact original failure ID, then show that the corrected implementation does not reproduce it

This specification governs the Antigravity Run 2 frontend. It is aligned with the merged backend and the real GET /api/sample and POST /api/analyze responses. It does not authorize changes to reduction logic, the failure oracle, or the API contract.

---

## 1 Product truth

The current verified sample contains 12 actions. The backend locally reduces it to four actions, confirms WRONG_CARD_CHARGED in five fresh replays, and checks that corrected retry behavior does not reproduce the failure.

These are observed baseline results, not UI constants:

| Evidence | Current sample result | UI source |
|---|---:|---|
| Original actions | 12 | original_steps.length |
| Reduced actions | 4 | reduced_steps.length |
| Failure identity | WRONG_CARD_CHARGED | failure_id |
| Fresh confirmations | 5 of 5 | Count matching items in trials |
| Corrected implementation | Does not reproduce | fixed_passes and fixed_result |

The interface must not state or imply:

- global minimality;
- guaranteed debugging success;
- measured developer time savings;
- arbitrary repository execution;
- a production payment integration;
- a live IBM Bob runtime API;
- confidence scores that the backend does not calculate.

---

## 2 Ten second experience

The first successful run should communicate this sequence without narration:

~~~mermaid
flowchart LR
    A["12 action sample"] --> B["Fresh replay"]
    B --> C["4 retained actions"]
    C --> D["Same failure 5 of 5"]
    D --> E["Corrected path passes"]
~~~

The primary visual statement after a real response is:

> 12 actions → 4 proof steps  
> WRONG_CARD_CHARGED confirmed 5/5  
> Corrected behavior does not reproduce

Before the API responds, any mention of 12→4 must be labeled **Sample outcome preview**. It must never look like a completed live analysis.

---

## 3 Product personality

SequenceProof should feel like a precision developer instrument:

- calm;
- dense but readable;
- technical;
- evidence first;
- trustworthy;
- deliberate.

Reference qualities may come from Linear, Vercel, observability tools, and modern IDEs, but the interface must not copy a specific product.

Avoid:

- cyberpunk styling;
- constant glow;
- oversized marketing headlines;
- floating decorative cards;
- fake analytics dashboards;
- chat UI conventions;
- robot, brain, shield, and generic AI imagery;
- excessive glassmorphism;
- decorative 3D.

---

## 4 Non negotiable data rules

### Result values

Every result value must be derived from the current API response:

- action counts;
- reduction percentage;
- failure ID;
- expected and actual cards;
- trial count and outcomes;
- candidate checks;
- orphan steps pruned;
- corrected result;
- duration.

### Static content

Static content may explain:

- what fresh replay means;
- what locally reduced means;
- why invalid candidates do not count;
- how exact failure identity is preserved;
- the synthetic and bounded scope.

Static content must not impersonate a completed analysis.

### Missing fields

Do not invent values when a field is unavailable. The current API does not provide:

- case numbers;
- Git commit hashes;
- repository branches;
- environment names;
- rerun commands;
- assertion IDs;
- confidence percentages.

Omit those elements instead of filling them with examples.

### Security

Escape all user controlled values before inserting them into HTML. Never place raw JSON content into innerHTML. Preserve the 32 KiB request limit and 40 action limit.

---

## 5 Application structure

Use one cohesive page with three modes: Ready, Analyzing, and Result.

~~~mermaid
stateDiagram-v2
    [*] --> Ready
    Ready --> Analyzing: Analyze trace
    Analyzing --> Verified: REPRODUCED
    Analyzing --> Invalid: INVALID_TRACE
    Analyzing --> Passing: NOT_REPRODUCED
    Analyzing --> Flaky: FLAKY
    Analyzing --> Error: Request or JSON error
    Verified --> Ready: Reset sample
    Invalid --> Analyzing: Correct and retry
    Passing --> Analyzing: Edit and retry
    Flaky --> Analyzing: Retry
    Error --> Analyzing: Retry
~~~

The page should feel like a working debugging surface, not a landing page followed by a separate tool.

---

## 6 Layout

### Top bar

Height: 56–64 px.

Show:

- SequenceProof wordmark;
- descriptor: **Executable stateful debugging**;
- badge: **Synthetic sample**;
- badge or tooltip: **Bounded analysis**.

Do not show IBM logos. IBM Bob evidence belongs in the repository and submission narrative, not the runtime product interface.

### Hero

Use a compact hero above the workspace:

- eyebrow: **From noisy trace to executable proof**;
- heading: **Find the few actions that actually reproduce the same failure.**;
- one short explanatory sentence;
- preview strip labeled **Sample outcome preview** before execution.

After execution, populate the equation exclusively from the response.

### Desktop workspace

| Zone | Width | Purpose |
|---|---:|---|
| Trace workspace | 42% | Issue context, readable trace, JSON editor, actions |
| Proof workspace | 58% | Analysis state, verified result, comparison, proof drawer |

The right side gains stronger visual weight only after a response.

### Density

- Maximum content width: 1380 px.
- Main page padding: 24–32 px.
- Panel padding: 18–24 px.
- Trace row height: approximately 44–54 px.
- Section gaps: 20–32 px.
- Avoid large empty areas.

---

## 7 Trace workspace

### Sample issue

Populate the issue from GET /api/sample:

> A retry sometimes charges the old card after the customer chooses a new one.

Use the fetched value rather than duplicate it in JavaScript.

### Readable timeline

Render each current JSON action as a numbered row with action name, item or card when present, and a compact semantic indicator.

| Raw action | Derived readable label |
|---|---|
| view_catalog | View catalog |
| add_item | Add item · current item |
| remove_item | Remove item · current item |
| set_card | Select card · current card |
| begin_checkout | Begin checkout |
| retry_payment | Retry payment |
| view_receipt | View receipt |
| refresh_cart | Refresh cart |

The label must be derived from the current action object.

### JSON editor

The editor remains the source of truth.

- use a monospace font;
- provide a visible label;
- show JSON parse errors inline;
- set aria-invalid when malformed;
- send no request when parsing fails;
- refresh the readable timeline after valid changes;
- reset to the fetched sample;
- support Ctrl + Enter to analyze.

### Controls

- Primary: **Analyze trace**
- Secondary: **Reset sample**

Disable Analyze only while a request is pending.

---

## 8 Analysis progress

While the real request is pending, show five explanatory stages:

1. Validate trace
2. Replay from fresh state
3. Reduce valid candidates
4. Confirm exact failure
5. Check corrected behavior

The browser receives one completed response. These stages are an explanatory pending animation, not a live backend stream.

Rules:

- never show a fabricated percentage;
- never show fake candidate counts or timings;
- label the sequence **Analysis in progress**;
- stop immediately when the response arrives;
- respect reduced motion.

---

## 9 Verified result

Render verified styling only when status equals REPRODUCED.

### Result hero

Show:

- **Same failure verified**;
- dynamic original length → reduced length;
- dynamic reduction percentage;
- exact failure ID;
- matching trials / total trials;
- corrected behavior status.

Preferred hierarchy:

1. 12 → 4
2. WRONG_CARD_CHARGED
3. 5/5 fresh confirmations
4. Corrected behavior passes

### Failure moment

Use original.expected and original.actual.

| Field | Dynamic value |
|---|---|
| Expected at retry | original.expected |
| Actually charged | original.actual |
| Failure | failure_id |

Explain:

> The failure oracle compares the card actually charged with the card active at that retry moment.

If expected or actual is absent, omit that row.

### Confirmation strip

Render one cell per item in trials. Count a matching confirmation only when both are true:

~~~text
trial.status === "REPRODUCED"
trial.failure_id === failure_id
~~~

Each cell needs text or an accessible label in addition to color. Do not pre-render five successful cells.

### Corrected behavior

If fixed_passes is true:

> Corrected behavior: target failure not reproduced

Do not write “bug fixed” or imply production validation.

If false:

> Corrected behavior still needs review

---

## 10 Original and reduced comparison

### Original timeline

Show all original_steps.

- retained steps use high contrast;
- removed steps use low contrast and optional strike-through;
- never delete original steps from this column.

### Reduced timeline

Show reduced_steps in returned order.

- use retained proof styling;
- preserve exact action values;
- do not imply insertion or reordering.

### Mapping

Use an ordered subsequence walk:

1. move forward through original_steps;
2. compare each step with the next reduced_steps item;
3. mark the first ordered match as retained;
4. continue without moving backward.

This visual mapping must not change the backend output.

### Motion

After a successful result:

- removed steps fade;
- retained steps remain;
- reduced steps reveal in order;
- the result hero appears once.

No bouncing, particles, rotating marks, or continuous glow.

---

## 11 Proof drawer

Use native details and summary elements or an accessible equivalent.

Include only real response data:

- original status;
- exact failure ID;
- trial outcomes;
- corrected result;
- original replay events;
- candidate checks;
- orphan steps pruned;
- duration;
- locally reduced and bounded scope note.

Keep **Download proof JSON**. The downloaded file must contain the latest real response.

Do not offer Markdown export, reproduction bundles, or copyable rerun commands in Run 2 unless they are genuinely implemented and verified.

---

## 12 Negative and error states

| Condition | UI title | Required behavior |
|---|---|---|
| INVALID_TRACE | Invalid trace | Show original.detail; never show reduction metrics |
| NOT_REPRODUCED | Target failure not reproduced | Explain that no verified reduction was produced |
| FLAKY | Confirmation inconsistent | Show real trial outcomes; do not call it verified |
| Malformed editor JSON | JSON needs correction | Show parse error near editor; send no request |
| HTTP or network failure | Analysis unavailable | Show the safe error and provide Retry |

Do not introduce SETUP_ERROR or UNEXPECTED_ERROR as backend statuses. They may be presentation labels for transport errors only.

No negative state may display:

- 12→4 as a completed result;
- verified green styling;
- five successful trial cells;
- a corrected-pass claim.

---

## 13 Visual system

### Color tokens

~~~css
:root {
  --sp-bg-canvas: #080b10;
  --sp-bg-surface: #0f141b;
  --sp-bg-raised: #151c25;
  --sp-bg-interactive: #1b2430;

  --sp-text-primary: #f3f6f8;
  --sp-text-secondary: #a7b2bf;
  --sp-text-muted: #748292;

  --sp-accent: #67d4c1;
  --sp-accent-strong: #48bda9;
  --sp-accent-soft: rgba(103, 212, 193, 0.12);

  --sp-failure: #f59e72;
  --sp-success: #63d49c;
  --sp-warning: #f3c969;
  --sp-error: #f47c7c;

  --sp-border: rgba(255, 255, 255, 0.08);
  --sp-border-strong: rgba(255, 255, 255, 0.14);

  --sp-radius-sm: 6px;
  --sp-radius-md: 9px;
  --sp-radius-lg: 14px;
}
~~~

Semantic rules:

- teal: verified proof and retained sequence;
- amber/coral: observed wrong charge;
- green: corrected path pass;
- amber: flaky or caution;
- red: malformed input or transport failure;
- blue-gray: ready and not reproduced.

Never communicate status through color alone.

### Surfaces

- 85% solid surfaces;
- no more than 15% translucent or blurred surfaces;
- blur only the sticky top bar or temporary overlay;
- keep borders subtle;
- avoid nested card stacks.

### Typography

Use system fonts only:

~~~css
font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
~~~

Technical values:

~~~css
font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
~~~

| Role | Size | Weight |
|---|---:|---:|
| Result number | clamp(36px, 5vw, 64px) | 760 |
| Page heading | clamp(30px, 4vw, 48px) | 700 |
| Section heading | 16–18px | 650 |
| Body | 14px | 400 |
| Secondary | 12–13px | 400 |
| Micro label | 10–11px | 650 |

Do not load Google Fonts or external icon libraries.

### Icons

Use minimal inline SVG or text-safe symbols with accessible labels. Do not depend on a CDN.

### Radius and shadow

- panel radius: 12–14 px;
- button and input radius: 8–10 px;
- pill radius only for compact status;
- use low-opacity shadows, not glows.

---

## 14 Motion

Motion should answer: **What changed?**

Use:

- 120–180 ms for hover and focus;
- 200–320 ms for result reveal;
- opacity and 4–8 px translation;
- one collapse/fade for removed steps.

Do not use:

- infinite animation;
- simulated live logs;
- fake streaming trials;
- dramatic page transitions;
- counters racing through invented values.

Reduced-motion mode must remove movement without removing information.

---

## 15 Responsive behavior

### Desktop above 1000 px

- 42/58 workspace split;
- original and reduced timelines side by side;
- proof drawer spans the result column.

### Tablet 720–999 px

- compact single-column hero;
- keep two workspace columns only when both remain readable;
- otherwise stack trace above proof.

### Mobile below 720 px

Order:

1. top bar;
2. hero;
3. sample issue;
4. editor and readable trace;
5. Analyze and Reset;
6. result hero;
7. failure moment;
8. confirmation strip;
9. original timeline;
10. reduced timeline;
11. proof drawer;
12. scope note.

No horizontal page scrolling. JSON and proof blocks may scroll internally.

---

## 16 Accessibility

Required:

- semantic headings in order;
- real button, textarea, details, and summary elements;
- visible focus-visible state;
- status updates in a scoped aria-live region;
- editor label and error association;
- aria-busy while analyzing;
- aria-invalid for malformed JSON;
- no color-only status communication;
- keyboard access to every action;
- documented Ctrl + Enter shortcut;
- reduced motion support.

Announce the beginning and final result, not every decorative progress stage.

---

## 17 Exact API binding

### GET /api/sample

| Response field | UI |
|---|---|
| title | Sample title if needed |
| issue | Issue statement |
| trace | Editor and readable timeline |

### POST /api/analyze

For REPRODUCED:

| Response field | UI |
|---|---|
| status | Verdict state |
| failure_id | Exact failure badge |
| original.detail | Failure explanation |
| original.expected | Expected card |
| original.actual | Charged card |
| original.events | Proof event log |
| original_steps | Original timeline |
| reduced_steps | Reduced proof timeline |
| trials | Confirmation cells |
| attempts | Candidate checks |
| orphan_steps_pruned | Pruning metric |
| fixed_result | Corrected-path evidence |
| fixed_passes | Corrected-path verdict |
| duration_ms | Observed runtime |

For negative states, treat absent fields as absent. Never display undefined, null, zero metrics, or placeholder successes just to fill space.

---

## 18 Copy system

Preferred language:

- Analyze trace
- Replay from fresh state
- Same failure verified
- Locally reduced
- Exact failure ID
- Fresh confirmations
- Corrected behavior
- Target failure not reproduced
- Invalid trace
- Inspect execution proof
- Download proof JSON

Avoid:

- AI magic;
- guaranteed minimal;
- bug fixed;
- instant solution;
- perfect reproduction;
- 100% confidence;
- production ready.

Recommended scope copy:

> This result is locally reduced within a bounded search. Every accepted candidate is replayed from fresh state and must preserve the exact observed failure ID. The sample uses synthetic data.

---

## 19 Implementation constraints

- Preserve the zero dependency Python backend.
- Prefer one improved index.html; do not add a frontend build system.
- Preserve GET /api/sample and POST /api/analyze.
- Do not modify sequenceproof.py during Run 2.
- Do not hardcode successful result objects.
- Do not embed fallback success data.
- Do not add external fonts, analytics, icons, or UI libraries.
- Do not touch bob_sessions.
- Do not touch or stage the unrelated local file named ss.
- Keep download output tied to the latest real response.
- Keep result rendering correct across repeated runs.

---

## 20 Run 2 acceptance tests

### Backend

- [ ] python -m unittest -v passes all 10 tests.
- [ ] Default API result remains 12→4.
- [ ] Exact failure remains WRONG_CARD_CHARGED.
- [ ] Five fresh trials remain 5/5.
- [ ] Corrected implementation remains passing.

### Browser

- [ ] Sample loads from /api/sample.
- [ ] Timeline reflects editor JSON.
- [ ] Analyze calls the real /api/analyze.
- [ ] Default result derives all numbers from the response.
- [ ] Expected card-B and charged card-A come from response data.
- [ ] Malformed JSON sends no request.
- [ ] Protocol-invalid trace renders INVALID_TRACE.
- [ ] Valid passing trace renders NOT_REPRODUCED.
- [ ] Negative states show no verified reduction.
- [ ] Repeated runs replace old result data.
- [ ] Downloaded JSON matches the latest response.
- [ ] Browser console has no errors.

### Responsive and accessible

- [ ] Desktop layout is balanced.
- [ ] Tablet layout remains readable.
- [ ] Mobile has no horizontal page scroll.
- [ ] Keyboard-only operation works.
- [ ] Focus states are visible.
- [ ] Live-region announcement is useful and not noisy.
- [ ] Reduced-motion mode preserves all information.

### Trust

- [ ] No fake progress percentage.
- [ ] No fake trials.
- [ ] No hardcoded verified result.
- [ ] No unsupported case, branch, commit, or environment metadata.
- [ ] Locally reduced and synthetic scope remains visible.
- [ ] IBM Bob appears only as build workflow evidence, not runtime integration.

---

## 21 Judge demo sequence

Target duration for the core wow moment: 10 seconds.

1. Show the fetched 12-action sample.
2. Click **Analyze trace**.
3. Let the compact pending stages explain the mechanism.
4. Reveal 12→4 from the real response.
5. Point to WRONG_CARD_CHARGED.
6. Show expected card-B versus charged card-A.
7. Show 5/5 exact-failure confirmations.
8. Show corrected behavior does not reproduce.

Expand the proof drawer only if the judge wants implementation evidence.

---

## 22 Optional future enhancements

These are outside Run 2 unless the backend later supports them:

- multiple state-machine adapters;
- real flaky fixtures;
- persisted run history;
- repository ingestion;
- generated rerun commands;
- Markdown or bundle export;
- authenticated collaboration;
- light theme.

Do not create visual placeholders for these features in the current prototype.

---

## 23 Final design principle

Every element should reinforce one truthful transformation:

> A long stateful report becomes a short executable proof only after the same failure survives valid fresh replay, repeated confirmation, and corrected-behavior comparison.

If a component does not clarify the input, reduction, exact failure, confirmation evidence, or corrected result, remove it.
