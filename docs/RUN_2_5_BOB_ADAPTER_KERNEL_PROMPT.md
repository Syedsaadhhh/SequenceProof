# Run 2.5 — IBM Bob Real-Repository Sandbox Kernel

Work only on branch `bob/run-2-5-adapter-kernel`.

This brief supersedes the earlier adapter-only scope. The filename remains unchanged
only to preserve branch continuity.

## Mission

Turn SequenceProof from a checkout-specific demonstration into a real execution
system:

> Given a pinned public repository, an executable replay contract, and a trace that
> already reproduces a bug, run the repository in a disposable sandbox and reduce
> the trace only while fresh executions preserve the exact original failure ID.

The payment fixture remains as a fast built-in preview and regression baseline. It
must no longer be presented as the product.

SequenceProof is not expected to discover every bug automatically. It is a
reproducer minimizer. A repository opts in by supplying a small executable runner
that defines how to replay its own trace and classify its own failure. The kernel
must not know the repository's actions, state machine, or failure names.

## Competitive bar

The implementation must be stronger than a paste-and-claim dashboard:

- no hardcoded analysis outcome;
- no timer-driven fake progress;
- no claim that a sandbox ran when it did not;
- no silent fallback from real execution to a synthetic result;
- no generic AI risk score standing in for executable evidence;
- no "supports every bug" claim;
- no global-minimality claim.

The ten-second demo must visibly show real phases backed by server state:

1. resolve a public GitHub repository and pinned commit;
2. create a disposable sandbox;
3. execute the original trace and capture its failure ID;
4. execute deletion candidates against the real repository;
5. confirm the reduced proof five fresh times;
6. execute the corrected implementation;
7. destroy the sandbox;
8. display the commit SHA, command, actual process result, and reduction certificate.

## Read before editing

Read fully:

- `AGENTS.md`
- `sequenceproof.py`
- `server.py`
- `test_sequenceproof.py`
- `test_server.py`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/BUILD_LOG.md`
- `docs/SEQUENCEPROOF_UI_UX_DESIGN_SYSTEM.md`

First print:

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status --short
python -m unittest -v
```

Do not touch or stage the unrelated local files `ss` or
`SequenceProof_Complete_UI_UX_Design_System (1).md`. Do not commit, push,
merge, deploy, or fabricate a Bob screenshot.

## Architectural boundary

Separate these responsibilities, using equivalent names if clearer:

- `core.py`: protocol-agnostic bounded deletion reducer, confirmation,
  exact-failure checks, and one-minimal certificate.
- `runner_contract.py`: strict manifest, job request, and runner-output models.
- `sandbox/base.py`: `SandboxProvider` protocol.
- `sandbox/daytona_provider.py`: primary cloud provider for the hosted demo.
- `sandbox/docker_provider.py`: optional local provider when Docker is actually
  available.
- `sandbox/fake_provider.py`: deterministic tests only; never selectable by a
  production HTTP request.
- `repository_runner.py`: repository checkout, manifest loading, candidate
  execution, result parsing, cleanup, and provider-neutral orchestration.
- `jobs.py`: bounded in-memory job store and truthful phase/event history.
- existing checkout code: compatibility preview only.

Do not force these exact filenames if the current repository architecture suggests
a smaller safe refactor. The hard rule is that the generic reducer cannot contain
checkout actions, card state, access-control actions, or known failure IDs.

## Repository opt-in contract

Initially support public GitHub HTTPS repositories only. Require an immutable
40-character commit SHA; do not accept a mutable branch name as proof identity.

The repository contains `.sequenceproof/manifest.json`:

```json
{
  "schema_version": 1,
  "id": "stale-role-service",
  "title": "Stale authorization after account switch",
  "runner": {
    "argv": ["python", "sequenceproof_runner.py"],
    "fixed_argv": ["python", "sequenceproof_runner.py", "--fixed"],
    "timeout_seconds": 15
  }
}
```

Rules:

- reject unknown manifest keys and malformed values;
- `argv` and `fixed_argv` are non-empty string arrays, never shell strings;
- service-owned limits override manifest values;
- no setup command is accepted in v1;
- no credentials, tokens, private repository URLs, arbitrary callback URLs, or
  host paths may enter the sandbox;
- the provider API key must never be exposed to repository code;
- `fixed_argv` is optional for third-party repositories; when absent, report
  `NOT_CHECKED`, never `fixed_passes=true`.

For every replay, write the candidate trace as JSON to a fresh path and pass its
path through `SEQUENCEPROOF_TRACE_PATH`. Set a unique
`SEQUENCEPROOF_RUN_ID`. Run the manifest argv without host-shell interpolation.

A runner may print diagnostic lines, but its final non-empty stdout line must be
one strict JSON object:

```json
{
  "schema_version": 1,
  "status": "REPRODUCED",
  "failure_id": "STALE_ROLE_AUTHORIZATION",
  "evidence": {
    "expected_role": "viewer",
    "authorized_as": "admin"
  }
}
```

Shared statuses are:

- `REPRODUCED`
- `NOT_REPRODUCED`
- `INVALID_TRACE`

Only `REPRODUCED` may have a non-null `failure_id`. A nonzero exit, timeout,
malformed JSON, missing output, or oversized output is `EXECUTION_ERROR`, never
bug evidence.

The engine learns the target failure ID from the original trace's first real
replay. It must not be hardcoded in the manifest or kernel.

## Fresh execution invariant

Every original, candidate, confirmation, and fixed replay must:

- use a new process;
- use a unique trace path and run ID;
- restore the checked-out repository to the pinned commit before execution;
- remove untracked files created by the previous replay;
- receive no prior replay result or mutable application state;
- have bounded wall time and output size.

If the provider cannot establish those conditions, fail the job explicitly.
Do not downgrade to the built-in checkout fixture.

## Sandbox providers

### Daytona: hosted path

Use the official `daytona` Python SDK as an optional dependency and
`DAYTONA_API_KEY` from the server environment.

The provider must:

- create one disposable sandbox per analysis job;
- clone the public repository at the exact requested commit;
- expose the resolved commit in evidence;
- run commands with explicit timeouts;
- capture real exit code, stdout, stderr, and duration;
- delete the sandbox in `finally`, including failures and cancellation;
- never pass host secrets into the sandbox;
- return `SANDBOX_UNAVAILABLE` when the SDK/key/service is unavailable.

Do not mock Daytona in production code and do not claim a Daytona execution unless
the provider returns a real sandbox ID.

### Docker: local path

Implement only if Docker is available during this run. Use subprocess argv, never
`shell=True`. Apply at least:

- `--rm`;
- non-root user;
- read-only root filesystem where compatible;
- CPU, memory, PID, and wall-clock limits;
- no privileged mode;
- no Docker socket mount;
- no host credential mounts;
- a writable temporary workspace only;
- deterministic cleanup.

Clone/fetch the public repository outside the no-network replay container, pin and
verify the commit, then execute replay commands with network disabled. If Docker
is missing, report the provider as unavailable; do not simulate it.

Provider selection must be explicit through configuration. No production request
may select `FakeSandboxProvider`.

## Real executable fixture

Add a small owned repository fixture under `examples/stale-role-service/`. It
must be actual executable Python code invoked as a subprocess, not a call into the
old in-memory checkout state machine.

It must include:

- a realistic application module;
- a buggy implementation;
- a corrected implementation;
- `sequenceproof_runner.py`;
- `.sequenceproof/manifest.json`;
- a noisy sample trace;
- a stable failure `STALE_ROLE_AUTHORIZATION`;
- stateful preconditions;
- at least one invalid trace;
- at least one valid non-reproducing trace;
- runner unit tests.

The runner reads the trace file identified by `SEQUENCEPROOF_TRACE_PATH`. The
buggy and fixed paths must execute different real implementation code. Do not
hardcode a final API response or a predetermined reduced trace.

This controlled fixture is the guaranteed demo. Also support any public repository
that implements the same v1 contract. Do not call an unconfigured repository
supported.

## Generic reduction invariants

The repository execution adapter must feed the existing reduction kernel without
weakening it:

- maximum 40 input actions;
- maximum 32 KiB request;
- bounded candidate attempts;
- deletion only;
- repaired output must be an ordered exact-object subsequence;
- no insertion, reordering, or action mutation;
- original trace must reproduce first;
- candidate accepted only when status is `REPRODUCED` and exact non-null
  `failure_id` matches the original;
- five fresh confirmation executions;
- `FLAKY` remains distinct;
- fixed result is independently executed;
- bounded one-minimal certificate remains honest;
- never claim global minimality.

The existing checkout sample must remain 12 to 4, 5/5 confirmations, corrected
pass, and one-minimal certificate.

## Truthful job API

Keep existing endpoints working. Add:

```http
GET  /api/sandbox/providers
POST /api/jobs
GET  /api/jobs/{job_id}
DELETE /api/jobs/{job_id}
```

Example request:

```json
{
  "repo_url": "https://github.com/OWNER/REPOSITORY",
  "commit_sha": "40_HEX_CHARACTERS",
  "manifest_path": ".sequenceproof/manifest.json",
  "trace": []
}
```

`POST /api/jobs` returns `202` and a job ID. Job state is one of:

- `QUEUED`
- `STARTING_SANDBOX`
- `CHECKING_OUT_REPOSITORY`
- `REPRODUCING_ORIGINAL`
- `REDUCING`
- `CONFIRMING`
- `VERIFYING_FIXED`
- `COMPLETED`
- `FAILED`
- `CANCELLED`

Every transition must be caused by real backend work. Store timestamps, provider,
sandbox ID when real, resolved commit SHA, candidate count, bounded log excerpts,
and final result. Do not manufacture percentage progress.

Run at most one sandbox job at a time in this prototype. Reject excess queued work
with a clear bounded-capacity response. Apply job TTL cleanup.

Provider failure, repository failure, manifest failure, runner failure, and
non-reproducing original traces must have distinct error codes.

## Security and data boundary

A sandbox without a boundary is not a sandbox. Keep v1 narrow:

- public repositories only;
- immutable commit required;
- no user secrets;
- no private GitHub token;
- no arbitrary host file upload;
- no callback URLs;
- no shell string from HTTP;
- strict payload/output limits;
- allowlist `https://github.com/<owner>/<repo>` URL shape;
- cleanup in every exit path;
- redact environment values from logs;
- never return full unbounded stdout/stderr.

If an official provider cannot enforce a desired limit, document that exact
boundary instead of claiming it.

## Tests

Add regression tests for at least:

1. generic core contains no checkout/access action names or known failure IDs;
2. manifest rejects shell strings, extra keys, missing argv, excessive timeout,
   traversal paths, mutable refs, non-GitHub URLs, and malformed SHAs;
3. original non-reproduction stops before reduction;
4. exact failure mismatch is rejected;
5. invalid trace is never evidence;
6. timeout, nonzero exit, malformed output, oversized output, and missing output
   become `EXECUTION_ERROR`;
7. each replay gets a unique run ID/path and reset;
8. fake provider cannot be chosen through HTTP;
9. provider unavailability is explicit and never returns a fixture result;
10. cleanup runs after success, failure, timeout, and cancellation;
11. job phases reflect actual executor callbacks;
12. queue and TTL bounds work;
13. real stale-role runner handles reproducing, invalid, passing, and fixed cases;
14. repository reduction confirms 5/5 and returns a one-minimal certificate;
15. checkout compatibility remains exactly 12 to 4;
16. all existing frontend/server tests remain green.

Use a fake provider only for deterministic unit tests. Before declaring this run
complete, perform at least one end-to-end execution through a real Daytona or
Docker provider. If neither is available, say `REAL SANDBOX E2E BLOCKED` and
identify the missing prerequisite. Do not substitute a mock result.

## Documentation

Update:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/BUILD_LOG.md`
- add `docs/RUNNER_CONTRACT.md`
- add `.env.example` without secrets
- add dependency/install instructions only where required

Use honest positioning:

- "Reduces an already-reproducing stateful trace against a real executable
  repository contract."
- "Runs public, pinned repositories in a disposable sandbox."
- "Preserves exact failure identity across fresh executions."
- "Locally reduced; one-minimal only when certified."
- "The included payment fixture is a preview, not the product."
- "Repositories opt in with a manifest and runner."

Do not claim:

- automatic support for every repository or bug;
- automatic bug discovery;
- global minimality;
- arbitrary private-repository safety;
- measured developer-time savings;
- IBM Bob runtime API integration;
- a real sandbox run that was not observed.

## Verification

Run:

```powershell
python -m unittest -v
python -m compileall -q .
node --check static/app.js
```

Exercise:

- all legacy endpoints;
- provider status;
- invalid job requests;
- unavailable-provider path;
- original not reproduced;
- runner execution error;
- successful real sandbox job;
- fixed verification;
- cancellation and cleanup;
- real fixture reduction with 5/5 confirmations.

Record exact observed commands and outputs in `docs/BUILD_LOG.md`.

## Final response

Return:

1. exact changed-file list;
2. architecture and runner contract;
3. exact provider used for the real E2E;
4. real sandbox ID and pinned commit SHA, if available;
5. original and reduced traces;
6. exact failure ID;
7. candidate count and five confirmation results;
8. corrected-run result;
9. API requests and observed responses;
10. complete test output;
11. cleanup evidence;
12. security boundaries;
13. honest remaining limitations;
14. `git status --short`;
15. reminder to capture the real IBM Bob task summary as
    `bob_sessions/sequenceproof_task02_sandbox_kernel_summary.png`.

Do not commit or push.
