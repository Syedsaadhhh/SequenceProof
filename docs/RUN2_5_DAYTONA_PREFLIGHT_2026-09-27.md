# Run 2.5 live Daytona preflight — 2026-09-27

This record covers actual Daytona execution on DESKTOP-2F13MRN. It does **not** certify the repository reduction workflow: the stale-role fixture is still uncommitted and the SequenceProof GitHub repository is private.

## Environment

- Branch: `bob/run-2-5-adapter-kernel`; inspected HEAD: `feefc56`.
- Python: system 3.14.4; isolated SDK environment outside the repository uses 3.13.13.
- Daytona Python SDK: 0.218.0. API key found in Windows User scope and loaded into the process without printing it.
- Docker CLI/Desktop/service absent; WSL Ubuntu is version 2 and stopped.
- Real IBM Bob summary screenshot: `bob_sessions/sequenceproof_task02_sandbox_kernel_summary.png` (115,959 bytes; visually inspected).

## Direct SDK smoke

- Created sandbox `0f3912f9-b7c1-431c-98d9-616a5a5fa0c6`.
- `sandbox.process.exec("echo SEQUENCEPROOF_DAYTONA_SMOKE")` returned exit code `0` and `SEQUENCEPROOF_DAYTONA_SMOKE`.
- `client.delete(sandbox)` returned. An immediate lookup still saw the object; a later lookup returned `DaytonaNotFoundError` (HTTP 404). Cleanup is confirmed after propagation.

## Provider probe against a public repository

- Request: `https://github.com/octocat/Hello-World`, pinned commit `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`.
- Sandbox: `be923147-8841-439c-8374-ac4a28ff58da`; workspace `/home/daytona/repo`.
- `git rev-parse HEAD`: exit `0`, stdout exactly `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`.
- Provider file write/read: `.sp_probe.txt` round trip returned `PROVIDER_FILE_OK`.
- Destroy called; subsequent `get` returned `DaytonaNotFoundError`.

## Failure-path cleanup

- Checkout request used the same public repo and an invalid 40-character zero SHA.
- Actual checkout failed with exit `128`: `fatal: unable to read tree (0000000000000000000000000000000000000000)`.
- The provider raised `SandboxUnavailableError`. Daytona sandbox count was `0` before and `0` after; no newly created IDs remained.

## HTTP API preflight

- Server ran at `127.0.0.1:8765` with the real Daytona provider, then was stopped; port 8765 had no listener afterward.
- `GET /api/sandbox/providers`: `daytona.available=true`, `docker.available=false`.
- First `POST /api/jobs` was rejected as `INVALID_REQUEST` because a PowerShell serialization error wrapped `trace` as an object instead of an array. Request construction was corrected.
- Corrected `POST /api/jobs`: same public repo and SHA above, `.sequenceproof/manifest.json`, the fixture's 12-step `noisy_reproducing.json` trace. Response contained job ID `a16572d1-522e-49b9-8de8-a9c3a751e0bf` and phase `STARTING_SANDBOX`.
- Polled `GET /api/jobs/a16572d1-522e-49b9-8de8-a9c3a751e0bf`: phases `QUEUED`, `STARTING_SANDBOX`, `CHECKING_OUT_REPOSITORY`, `FAILED`. Sandbox ID `157a89c3-29a6-4acc-a80d-47b35f7f4b1b`.
- Final result was the expected `MANIFEST_NOT_FOUND`, since Hello-World has no SequenceProof manifest. Daytona list confirmed the job sandbox absent after failure.

## Local changes and checks

- `repository_runner.py`: moved trace-file creation after `git reset` and `git clean`, because cleanup would delete a trace written first. Nonzero or timed-out reset/clean now becomes `EXECUTION_ERROR` rather than permitting a stale replay.
- `sandbox/daytona_provider.py`: current SDK call shape is in place; added cleanup after clone/checkout exceptions and checked file read/write exit codes. This file also changed concurrently during inspection, so review its final contents before staging.
- `python -m py_compile repository_runner.py sandbox/daytona_provider.py` passed.
- Six targeted tests initially passed in 63.943 seconds: SDK surface, four stale-role runner cases, and fake-provider repository reduction. This is not a real reduction result.
- A later fresh-state guard caused the fake-provider reduction test to fail (`FAILED` versus expected `COMPLETED`) because the fixture directory had no Git metadata. The test-only provider now restores its fixture snapshot for reset/clean commands. The focused reduction test then passed in 27.670 seconds; compilation of all three changed Python modules also passed.
- No commit, push, merge, deployment, or repository visibility change was made.

## Remaining gate

Publish only the reviewed `examples/stale-role-service/` source fixture as a public opt-in repository, obtain its actual 40-character commit SHA, then submit that repo and the 12-step trace through `POST /api/jobs`. Record original, candidates, five confirmations, fixed result, minimality, and sandbox destruction. Run full regressions and review the final diff afterward. Publication requires user approval.

## API request and response record

```http
POST http://127.0.0.1:8765/api/jobs
Content-Type: application/json

{"repo_url":"https://github.com/octocat/Hello-World","commit_sha":"7fd1a60b01f91b314f59955a4e4d4e80d8edf11d","manifest_path":".sequenceproof/manifest.json","trace":[{"action":"view_dashboard"},{"action":"switch_account","username":"alice","role":"admin"},{"action":"view_dashboard"},{"action":"view_dashboard"},{"action":"switch_account","username":"bob","role":"viewer"},{"action":"view_dashboard"},{"action":"view_dashboard"},{"action":"perform_action","name":"read_report"},{"action":"view_dashboard"},{"action":"logout"},{"action":"view_dashboard"},{"action":"logout"}]}
```

Accepted response: `{"job_id":"a16572d1-522e-49b9-8de8-a9c3a751e0bf","phase":"STARTING_SANDBOX","message":"Job queued. Poll GET /api/jobs/{job_id} for status."}`

Final poll: `{"job_id":"a16572d1-522e-49b9-8de8-a9c3a751e0bf","phase":"FAILED","sandbox_id":"157a89c3-29a6-4acc-a80d-47b35f7f4b1b","provider_name":"daytona","result":{"status":"FAILED","error_code":"MANIFEST_NOT_FOUND","detail":"Cannot read manifest at .sequenceproof/manifest.json: Sandbox file read failed: /home/daytona/repo/.sequenceproof/manifest.json","provider":"daytona","sandbox_id":"157a89c3-29a6-4acc-a80d-47b35f7f4b1b"}}`

The job's complete event timestamps remain in the Desktop Commander session output. No reduction candidates, confirmations, or fixed run occurred in this preflight.
