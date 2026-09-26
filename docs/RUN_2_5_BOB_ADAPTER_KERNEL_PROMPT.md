# Run 2.5 — IBM Bob Adapter Kernel

Work only on branch `bob/run-2-5-adapter-kernel`.

## Why this run exists

SequenceProof currently proves its reduction method through one owned checkout
fixture. The bounded reducer, fresh replays, exact failure identity, five
confirmations, corrected-path check, and one-minimal certificate are valuable,
but validation, replay, repair, and the failure oracle remain checkout-specific.

This run must turn those dependencies into an explicit adapter contract. It
must demonstrate the same kernel against two unrelated stateful bugs without
claiming that the hosted web app can safely execute arbitrary uploaded code.

Read completely before editing:

- `AGENTS.md`
- `sequenceproof.py`
- `server.py`
- `test_sequenceproof.py`
- `test_server.py`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/BUILD_LOG.md`

First report:

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status --short
python -m unittest -v
```

Do not touch or stage the unrelated local files `ss` or
`SequenceProof_Complete_UI_UX_Design_System (1).md`. Do not commit, push,
merge, deploy, or fabricate a Bob screenshot.

## Product contract

The generic kernel may reduce a candidate only when an adapter:

1. validates the stateful trace,
2. replays it from fresh state,
3. returns the exact same non-null failure ID,
4. permits only deletion-based orphan repair,
5. confirms the reduced trace five times,
6. checks the same trace against a corrected implementation.

An oracle is not a fallback. It is the executable predicate every reducer
requires. The product improvement is that the oracle is now supplied through a
documented adapter rather than hardcoded into the reduction kernel.

## Required architecture

Preserve the zero-dependency Python implementation and current public imports.
A safe structure is:

- `core.py` — protocol-agnostic bounded reduction, confirmation, minimality
  certificate, and invariant checks.
- `adapters.py` — adapter protocol/base class, registry, and lookup.
- `checkout_adapter.py` — current card-retry protocol and sample.
- `access_adapter.py` — second unrelated owned stateful protocol.
- `sequenceproof.py` — compatibility facade exporting existing names and
  defaulting old callers to the checkout adapter.
- `sequenceproof_cli.py` — local developer CLI for built-in or user-authored
  adapters.

Equivalent names are acceptable, but the generic core must not contain checkout
actions, card identifiers, checkout state, or a checkout failure ID.

## Adapter contract

Define and document a small typed contract equivalent to:

```python
class BugAdapter(Protocol):
    id: str
    title: str
    issue: str
    sample_trace: list[dict[str, Any]]

    def validate_trace(self, raw: Any) -> list[dict[str, Any]]: ...
    def replay(self, trace: list[dict[str, Any]], fixed: bool = False) -> dict[str, Any]: ...
    def repair_orphans(
        self, candidate: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]: ...
```

Every replay result must use the shared statuses:

- `INVALID_TRACE`
- `NOT_REPRODUCED`
- `REPRODUCED`

A reproduction must contain a stable non-null `failure_id`. Adapter-specific
evidence can appear under `evidence`, `events`, or other documented fields.

## Kernel invariants

Move the reducer and analysis orchestration into the generic core.

The core must:

- accept an adapter instance rather than importing checkout state;
- start every original, candidate, trial, and corrected replay from fresh state;
- accept a candidate only when its status is `REPRODUCED` and its exact
  `failure_id` matches the original;
- never accept `INVALID_TRACE` as evidence;
- remain bounded to 40 input actions, 32 KiB HTTP requests, and 250 candidate
  checks;
- preserve five fresh confirmations;
- preserve `FLAKY` as distinct from passing and invalid;
- preserve the bounded one-minimal certificate;
- never claim global minimality.

Add a defensive generic invariant after adapter repair:

- repaired output must be an ordered subsequence of the candidate using exact
  action-object equality;
- it may delete actions only;
- it may not insert, reorder, or mutate an action;
- if this check fails, reject that repaired candidate rather than treating it
  as evidence.

## Built-in adapter 1: checkout

Move the current checkout behavior into the checkout adapter without changing
its observed contract:

- default sample remains 12 actions;
- reduced proof remains 4 actions;
- failure ID remains `WRONG_CARD_CHARGED`;
- every mismatching retry remains exposed;
- 5/5 confirmations remain;
- corrected implementation passes;
- one-minimal certificate remains true for the default sample.

Existing callers such as `analyze(SAMPLE)`, `replay(trace)`, and
`prune_orphaned_steps(candidate)` must continue to work through the
compatibility facade.

## Built-in adapter 2: stale authorization

Create a second owned synthetic state machine in a different domain.

Recommended protocol:

- an administrator signs in;
- an administrative workspace snapshots the role;
- the user switches to a viewer role;
- a later export incorrectly authorizes using the stale snapshotted role;
- the corrected path authorizes using the current role.

Use a stable failure ID such as:

`STALE_ROLE_AUTHORIZATION`

Include realistic noise actions so its sample is longer than its reduced proof.
The reduced proof should communicate a clear causal sequence such as:

1. sign in as administrator,
2. open privileged workspace,
3. switch to viewer,
4. export restricted audit data.

Requirements:

- fresh replay;
- stateful preconditions;
- invalid traces rejected;
- exact failure preservation;
- five confirmations;
- corrected implementation pass;
- bounded one-minimal certificate;
- only owned synthetic identities and roles.

Do not reuse payment/card terminology in this adapter.

## Public API

Preserve old checkout requests while adding adapter selection.

Required endpoints:

```http
GET /api/scenarios
GET /api/sample
GET /api/sample?adapter=checkout
GET /api/sample?adapter=access-control

POST /api/analyze
{"trace": [...]}

POST /api/analyze
{"adapter": "access-control", "trace": [...]}
```

Rules:

- omitted adapter defaults to checkout for backward compatibility;
- unknown adapter returns HTTP 400 with a clear error;
- `GET /api/scenarios` returns only safe metadata and owned samples;
- every analysis response includes the selected `adapter` ID;
- do not allow the HTTP server to import uploaded Python, clone repositories,
  execute shell commands, or call arbitrary runner URLs.

## Real custom-bug path: local adapter SDK/CLI

Add a local CLI so the open-source project can support user-authored bugs
without executing untrusted code on the public server.

Required built-in usage:

```bash
python sequenceproof_cli.py --adapter checkout --trace trace.json
python sequenceproof_cli.py --adapter access-control --trace trace.json
```

Add a documented local-only custom adapter option, for example:

```bash
python sequenceproof_cli.py --adapter-file ./my_adapter.py --trace trace.json
```

The module must deliberately export one documented adapter object or factory.
Print a clear warning that a local adapter is executable Python and must only be
loaded when the user trusts the file. This option must not be exposed through
the web API.

Add `docs/ADAPTER_SDK.md` with:

- the adapter contract;
- a minimal adapter example;
- required replay result fields;
- deletion-only repair rule;
- security boundary between local CLI and hosted web;
- how to test an adapter;
- honest claim language.

## Trace import boundary

Do not implement arbitrary repository upload in this backend run.

The later frontend pass will provide:

- scenario selector;
- JSON trace file import;
- editable JSON;
- clear selected-adapter context.

A trace file alone is not executable proof; it must be interpreted by the
selected adapter. Document this explicitly.

## Regression tests

Add tests that fail before this refactor and pass after it:

1. Generic kernel source contains no checkout/card-specific action or failure
   constants.
2. Checkout compatibility remains exactly 12→4, 5/5, fixed pass.
3. Access-control sample reproduces its own failure, reduces, confirms 5/5, and
   passes on the corrected path.
4. Invalid access-control traces cannot become evidence.
5. Exact failure IDs never cross between adapters.
6. A malicious/broken adapter that inserts, reorders, or mutates a step during
   repair is rejected by the kernel.
7. Unknown HTTP adapter returns 400.
8. `GET /api/scenarios` and both sample endpoints work.
9. Both POST forms work and identify the chosen adapter.
10. CLI built-in adapter execution works.
11. CLI custom adapter loading works only through the local CLI path.
12. The complete test suite passes.

Use only synthetic data.

## Documentation

Update:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/BUILD_LOG.md`

Use these honest claims:

- “Protocol-agnostic reduction kernel with pluggable executable adapters.”
- “Two included owned adapters demonstrate checkout and stale authorization.”
- “Developers can run trusted custom adapters locally through the CLI.”
- “The hosted app does not execute uploaded repositories or Python modules.”
- “Results are bounded and locally reduced; one-minimality is reported only
  when certified.”

Do not claim:

- all bugs work automatically;
- arbitrary repositories are safely executable in the hosted app;
- global minimality;
- measured developer-time savings;
- a live IBM Bob runtime API.

## Verification

Run:

```bash
python -m unittest -v
python -m compileall -q .
node --check static/app.js
```

Exercise the real HTTP API for:

- scenarios list;
- default checkout sample and analysis;
- access-control sample and analysis;
- invalid trace;
- valid non-reproducing trace;
- unknown adapter;
- payload boundary.

Exercise the CLI for both built-ins and a temporary trusted custom adapter.

## Final response

Return:

1. exact changed-file list;
2. adapter contract;
3. checkout result;
4. access-control result;
5. API examples and observed responses;
6. CLI examples and observed responses;
7. complete test output;
8. proof that broken repair cannot insert, reorder, or mutate steps;
9. security boundary;
10. honest remaining product boundaries;
11. `git status --short`;
12. reminder for the user to capture the real IBM Bob task summary as
    `bob_sessions/sequenceproof_task02_adapter_kernel_summary.png`.

Do not commit or push.
