# SequenceProof — Hackathon Submission & Demo Guide

## Project Summary

**SequenceProof** reduces an already-reproducing stateful action trace against a real executable repository contract. Given an opt-in public GitHub repository pinned at an immutable 40-character commit SHA, SequenceProof provisions a disposable cloud sandbox (via Daytona), executes the trace from clean state, and reduces it to a minimal proof sequence only while fresh replays preserve the exact original failure ID.

### The Problem
In distributed and stateful software systems, bugs rarely emerge from a single isolated action; they emerge from long, noisy sequences of state mutations (account switches, session cache updates, authorization handoffs, cart updates). Developers and QA engineers are left with 12+ steps of logs where 75% of the actions are irrelevant noise.

### The Solution: Real-First Trace Minimization
1. **Repository Opt-in**: The repository provides `.sequenceproof/manifest.json` and a lightweight runner script. The core reduction kernel remains 100% domain-agnostic with zero built-in assumptions about actions or failure IDs.
2. **Disposable Cloud Sandbox**: Provisions an isolated container via Daytona (`daytona==0.218.0`).
3. **Exact Failure Preservation**: Identifies the original failure ID (`STALE_ROLE_AUTHORIZATION`). Every candidate reduction step starts from fresh state and is accepted only if the exact failure ID recurs.
4. **5/5 Confirmation & Fix Verification**: Replays the reduced trace 5 independent times with unique run IDs, then tests the corrected implementation.
5. **Certified Minimality**: Issues a bounded one-minimal certificate confirming no single remaining step can be pruned.
6. **Truthful Resource Cleanup**: Automatically deletes the sandbox in `finally` and independently confirms destruction via Daytona API lookup.

---

## Live Render Web Service Deployment

The application is packaged as a single unified Docker container serving both the frontend UI and the REST API (`/api/jobs`, `/api/sandbox/providers`).

### Render Blueprint / Manual Deployment
- **Live Deployment URL**: [https://sequenceproof.onrender.com/](https://sequenceproof.onrender.com/)
- **Repository**: `https://github.com/Syedsaadhhh/SequenceProof`
- **Branch**: `bob/run-2-5-adapter-kernel`
- **Runtime**: `Docker` (using root `Dockerfile`)
- **Port**: Assigned dynamically by Render via `PORT` environment variable (listens on `0.0.0.0`)
- **Blueprint Spec**: Pre-configured in [`render.yaml`](../render.yaml)

### Environment Variables on Render
| Variable | Value / Source | Purpose |
| :--- | :--- | :--- |
| `DAYTONA_API_KEY` | *Secret environment variable* | Hosted Daytona sandbox provisioning API key |
| `SEQUENCEPROOF_PROVIDER` | `daytona` | Selects Daytona cloud sandbox provider |
| `SEQUENCEPROOF_EXAMPLE_REPO` | `https://github.com/Syedsaadhhh/SequenceProof` | Pre-fills owned public repository |
| `SEQUENCEPROOF_EXAMPLE_SHA` | `afc9aed7e844ac83ff40a101876d3fb16218f2a5` | Pinned immutable commit with stale-role fixture |
| `SEQUENCEPROOF_PROTECT_CREDITS` | `1` | Restricts public execution to owned repo to prevent credit drainage |
| `HOST` | `0.0.0.0` | Container bind address |

---

## Verified Live Daytona E2E Execution Evidence

Conducted on the live public repository `https://github.com/Syedsaadhhh/SequenceProof` at commit `afc9aed7e844ac83ff40a101876d3fb16218f2a5`. Complete raw evidence is recorded in [`docs/RUN2_5_DAYTONA_LIVE_E2E_EVIDENCE.json`](RUN2_5_DAYTONA_LIVE_E2E_EVIDENCE.json).

- **Job ID**: `c0ba7995-5f6e-43d9-86e0-619ce872e83e`
- **Disposable Sandbox ID**: `2288b6fb-4726-40d5-9295-48b92d441b2e`
- **Provider**: Daytona (`daytona==0.218.0`)
- **Observed Phases**: `QUEUED` → `STARTING_SANDBOX` → `CHECKING_OUT_REPOSITORY` → `REPRODUCING_ORIGINAL` → `REDUCING` → `CONFIRMING` → `VERIFYING_FIXED` → `COMPLETED`
- **Learned Failure ID**: `STALE_ROLE_AUTHORIZATION`
- **Input Trace**: 12 actions (noisy account switches, dashboard views, and report operations)
- **Reduced Proof Output (3 actions)**:
  1. `{"action": "switch_account", "username": "alice", "role": "admin"}`
  2. `{"action": "switch_account", "username": "bob", "role": "viewer"}`
  3. `{"action": "perform_action", "name": "read_report"}`
- **Candidate Evaluations**: 21 attempts
- **Confirmation Runs**: 5/5 fresh runs reproduced `STALE_ROLE_AUTHORIZATION` across 5 distinct run IDs
- **Corrected Implementation**: `fixed_passes=true` (status `NOT_REPRODUCED`, run ID `9b168e06-7a71-4a31-992a-6cac8690d801`)
- **Minimality Guarantee**: Certified `one-minimal` (3 single-step-removal checks)
- **Cleanup Status**: `requested: true`, `confirmed: true`, `detail: null`
- **Independent Verification**: SDK lookup `client.get('2288b6fb-4726-40d5-9295-48b92d441b2e')` returned `DaytonaNotFoundError` (destroyed with zero orphaned sandboxes).

### Live Production Execution via Render URL (`https://sequenceproof.onrender.com`)
Directly executed through the public Render deployment (Job ID: `f01787ad-4b38-49b9-8188-ef422aa8f587`, raw record in [`docs/RUN2_5_RENDER_DEPLOYED_E2E_EVIDENCE.json`](RUN2_5_RENDER_DEPLOYED_E2E_EVIDENCE.json)):
- **Sandbox ID**: `d908f182-e73f-4b99-a9a1-3c773f4153a6`
- **Execution Time**: Completed in 11 seconds
- **Output**: 12 actions → 3 actions, `STALE_ROLE_AUTHORIZATION`, 5/5 fresh confirmations, `one-minimal` certified, `fixed_passes: true`
- **Cleanup**: `requested: true`, `confirmed: true`, `detail: null` (confirmed deleted via Daytona SDK 404 lookup)

---

## IBM Bob IDE Development Workflow

IBM Bob IDE served as the central AI-agentic pair programmer for building SequenceProof:

1. **Proof Invariant Formulation (Task 01)**: Developed the exact failure oracle and state reset protocols, preventing false positives from cascading failures or unrelated exceptions.
2. **Sandbox Adapter Kernel (Task 02)**: Architected the pluggable sandbox interface (`SandboxProvider`), Daytona SDK integration, and truthful cleanup tracking.
3. **Session Verification Artifacts**:
   - `bob_sessions/sequenceproof_task01_proof_invariant_summary.png` (Task 1 summary)
   - `bob_sessions/sequenceproof_task02_sandbox_kernel_summary.png` (Task 2 summary)

*Note: IBM Bob IDE was used to develop the codebase and test harness; it does not execute as an internal service inside the deployed web application.*

---

## 2-Minute Demo Video Walkthrough Script

| Time | Screen / Visual | Voiceover / Action |
| :--- | :--- | :--- |
| **0:00 - 0:25** | Landing page at public URL | "Welcome to SequenceProof. In distributed stateful systems, bugs often hide inside noisy action traces. Here, an account switch leaves a stale role in memory, allowing unauthorized access. But the raw log has 12 noisy steps." |
| **0:25 - 0:50** | Click "Load executable test trace" | "Notice how SequenceProof connects directly to an immutable GitHub commit: `afc9aed7...` on our public repository. We hit 'Execute in disposable sandbox'." |
| **0:50 - 1:20** | Live Phase Transitions | "SequenceProof talks directly to Daytona. It provisions a disposable cloud sandbox, clones the repository at the pinned commit, and executes the original trace. Notice the live phase events: `STARTING_SANDBOX`, `CHECKING_OUT_REPOSITORY`, `REPRODUCING_ORIGINAL`." |
| **1:20 - 1:45** | Reduction & Confirmation | "The engine reduces the 12 steps down to just 3 critical actions. It doesn't guess: it executes 5 independent fresh trials with unique run IDs to confirm the bug 5/5 times, and verifies that the fixed code passes." |
| **1:45 - 2:00** | Cleanup & Certificate | "The sandbox is destroyed immediately in finally, verified by the Daytona API. Developers download the complete cryptographic proof JSON for pull requests. That is SequenceProof: verifiable, deterministic bug minimization." |

---

## Genuine Limitations & Scope Boundaries

1. **Opt-in Repository Model**: SequenceProof does not attempt black-box inference against arbitrary non-instrumented code; target repositories opt in using `.sequenceproof/manifest.json`.
2. **Bounded Delta-Debugging**: Guarantees bounded one-minimality within budget (max 40 actions, 250 candidate checks); it does not compute a global combinatorial minimum.
3. **Credit Protection**: Anonymous traffic is restricted to the verified `Syedsaadhhh/SequenceProof` repository to prevent arbitrary compute abuse on Daytona.
