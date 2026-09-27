# Runner Contract v1

A SequenceProof runner is an executable script in a repository that knows
how to replay a trace against that repository's own code and report whether
a specific failure was reproduced.

SequenceProof does not know the repository's actions, state machine, or
failure names. It only knows the runner contract described here.

## Repository opt-in

Add `.sequenceproof/manifest.json` to the repository root:

```json
{
  "schema_version": 1,
  "id": "my-service",
  "title": "Human-readable description of the bug scenario",
  "runner": {
    "argv": ["python", "sequenceproof_runner.py"],
    "fixed_argv": ["python", "sequenceproof_runner.py", "--fixed"],
    "timeout_seconds": 15
  }
}
```

### Manifest fields

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `schema_version` | integer | yes | Must be exactly `1` |
| `id` | string | yes | `[A-Za-z0-9_-]`, max 64 chars |
| `title` | string | yes | Max 200 chars |
| `runner.argv` | array of strings | yes | Non-empty; no shell strings; safe characters only |
| `runner.fixed_argv` | array of strings | no | Same rules as argv; omit if no fix to verify |
| `runner.timeout_seconds` | integer | no | 1–60; service ceiling overrides manifest |

**Rejected values (validation errors):**
- Shell strings in `argv` (e.g. `"python runner.py"` instead of `["python", "runner.py"]`)
- `argv` items containing `;`, `&`, `|`, `$`, spaces, quotes, or other shell metacharacters
- Extra top-level or runner-level keys
- Path traversal in `id` (`..`, `/`)
- `schema_version` other than `1`
- `fixed_argv` absent → `fixed_passes` reports `null` (NOT_CHECKED), never `true`

**Service-level overrides (cannot be changed by the manifest):**
- Maximum timeout: 60 seconds
- Maximum trace actions: 40
- Maximum request body: 32 KiB
- Maximum runner stdout: 64 KiB

## Runner environment

Each runner invocation receives:

| Variable | Value |
| --- | --- |
| `SEQUENCEPROOF_TRACE_PATH` | Absolute path to the candidate trace JSON file |
| `SEQUENCEPROOF_RUN_ID` | Unique UUID for this invocation |

The trace file contains a JSON array of action objects. The runner must not
modify or rename this file.

**Not passed to the runner:**
- `DAYTONA_API_KEY`
- `GITHUB_TOKEN`
- Any other host credentials

## Runner output contract

The runner may print any number of diagnostic lines. Its **final non-empty
stdout line** must be a strict JSON object:

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

### Output fields

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `schema_version` | integer | yes | Must be `1` |
| `status` | string | yes | One of `REPRODUCED`, `NOT_REPRODUCED`, `INVALID_TRACE` |
| `failure_id` | string or null | yes | Non-null only when `status == REPRODUCED` |
| `evidence` | object or null | no | Arbitrary key-value; returned in the job result |

### Status meanings

| Status | Meaning |
| --- | --- |
| `REPRODUCED` | The candidate trace triggered the target failure. |
| `NOT_REPRODUCED` | The trace completed without triggering the failure. |
| `INVALID_TRACE` | The trace is structurally invalid for this repository. |

**Important:** `INVALID_TRACE` is never counted as evidence of the bug.
The kernel accepts a candidate only when `status == REPRODUCED` and
`failure_id` exactly matches the failure ID observed in the original trace.

### EXECUTION_ERROR (kernel-generated)

If the runner exits with a nonzero code, times out, produces no output,
produces malformed JSON, or exceeds the output size limit, the kernel records
`EXECUTION_ERROR`. This status is never bug evidence and never causes the
candidate to be accepted.

## Fresh execution invariant

Every runner invocation (original, candidate, confirmation, fixed):

1. Starts from a fresh runner process created by the selected provider (no reuse).
2. Receives a unique `SEQUENCEPROOF_TRACE_PATH` and `SEQUENCEPROOF_RUN_ID`.
3. Runs after `git reset --hard <pinned-commit-sha> && git clean -fdx`
   to restore the repository to the immutable commit, even if a previous runner modified HEAD.
4. Receives no result from any prior invocation.
5. Has bounded wall time and output size.

## Fixed implementation check

When `fixed_argv` is present in the manifest, the kernel runs it against the
reduced trace after confirmation. The runner is the same script with a different
entry point (e.g. `--fixed` flag). The fixed runner must:

- Execute the corrected implementation (not the buggy one).
- Report `NOT_REPRODUCED` when the fix is correct.
- Follow the same output contract as the main runner.

When `fixed_argv` is absent, `fixed_passes` is `null` in the job result (NOT_CHECKED).

## Job API

### Submit a job

```http
POST /api/jobs
Content-Type: application/json

{
  "repo_url": "https://github.com/OWNER/REPOSITORY",
  "commit_sha": "40_lowercase_hex_characters",
  "manifest_path": ".sequenceproof/manifest.json",
  "trace": [
    {"action": "switch_account", "username": "alice", "role": "admin"},
    {"action": "switch_account", "username": "bob", "role": "viewer"},
    {"action": "perform_action", "name": "read_report"}
  ]
}
```

Returns `202` with:

```json
{
  "job_id": "uuid",
  "phase": "QUEUED",
  "message": "Job queued. Poll GET /api/jobs/{job_id} for status."
}
```

### Poll job status

```http
GET /api/jobs/{job_id}
```

Returns:

```json
{
  "job_id": "uuid",
  "phase": "COMPLETED",
  "created_at": 1234567890.0,
  "sandbox_id": "daytona-sandbox-id",
  "provider_name": "daytona",
  "request": {
    "repo_url": "...",
    "commit_sha": "...",
    "manifest_path": "...",
    "trace_length": 3
  },
  "events": [
    {"phase": "QUEUED", "timestamp": 1234567890.0, "detail": {}},
    {"phase": "STARTING_SANDBOX", "timestamp": 1234567890.1, "detail": {"provider": "daytona"}},
    ...
  ],
  "result": {
    "status": "COMPLETED",
    "job_status": "REPRODUCED",
    "failure_id": "STALE_ROLE_AUTHORIZATION",
    "reduced_steps": [...],
    "trials": [{"status": "REPRODUCED", "failure_id": "..."}, ...],
    "minimality": {"kind": "one-minimal", "certified": true, "checks": 3, "statement": "..."},
    "fixed_passes": true,
    "commit_sha": "...",
    "sandbox_id": "..."
  }
}
```

### Job phases

```
QUEUED               → job accepted, waiting for a free sandbox slot
STARTING_SANDBOX     → provider.create_sandbox() called
CHECKING_OUT_REPOSITORY → manifest read and validated
REPRODUCING_ORIGINAL → first runner execution; failure ID learned
REDUCING             → bounded deletion reduction running
CONFIRMING           → 5× confirmation executions
VERIFYING_FIXED      → fixed_argv runner execution
COMPLETED            → job_status REPRODUCED or FLAKY
FAILED               → error_code set; see below
CANCELLED            → job was in QUEUED phase when DELETE was received
```

### Error codes

| Code | Meaning |
| --- | --- |
| `SANDBOX_UNAVAILABLE` | No provider available; Daytona SDK/key missing and Docker absent |
| `MANIFEST_NOT_FOUND` | `manifest_path` not found in the repository |
| `MANIFEST_INVALID` | Manifest fails validation |
| `ORIGINAL_NOT_REPRODUCED` | Original trace did not reproduce the failure |
| `RUNNER_EXECUTION_ERROR` | Original runner exited nonzero, timed out, or produced bad output |
| `INTERNAL_ERROR` | Unexpected kernel error |
| `INVALID_REQUEST` | Job request fails validation (HTTP 400) |
| `QUEUE_FULL` | One active job already running (HTTP 429) |

### Cancel a queued job

```http
DELETE /api/jobs/{job_id}
```

Only `QUEUED` jobs can be cancelled. Active jobs run to completion.

## Example runner (stale-role-service)

See [`examples/stale-role-service/`](../examples/stale-role-service/) for a
complete working example including:

- `service_buggy.py` — stale authorization implementation
- `service_fixed.py` — corrected implementation
- `sequenceproof_runner.py` — v1 runner that reads the trace and outputs JSON
- `.sequenceproof/manifest.json` — manifest with `argv` and `fixed_argv`
- `traces/` — sample traces for manual testing
- `test_runner.py` — runner unit tests for all four cases

## v1 limitations

- Public GitHub HTTPS repositories only.
- Immutable 40-character commit SHA required; branch names rejected.
- No setup commands (no `pip install`, `npm install`, etc.).
- No private repository support.
- No credentials, tokens, or callback URLs.
- One concurrent sandbox job per server instance.
- Trace length limit: 40 actions.
- No claim of global minimality.
