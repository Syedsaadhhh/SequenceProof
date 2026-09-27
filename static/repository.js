/* Repository mode: only server-backed phases and executable evidence. */
(() => {
  "use strict";
  const el = (id) => document.getElementById(id);
  const state = { jobId: null, job: null, timer: null, polling: false, busy: false };
  const terminal = new Set(["COMPLETED", "FAILED", "CANCELLED"]);
  const setText = (id, value) => { el(id).textContent = String(value == null ? "—" : value); };
  const status = (message, bad = false) => {
    setText("repo-status", message);
    el("repo-status").className = bad ? "repo-status repo-error" : "repo-status";
  };
  const addRow = (parent, values, className = "") => {
    const row = document.createElement("div");
    row.className = "repo-row " + className;
    for (const value of values) {
      const cell = document.createElement("span");
      cell.textContent = String(value == null ? "—" : value);
      row.appendChild(cell);
    }
    parent.appendChild(row);
  };
  const stopPolling = () => {
    if (state.timer !== null) clearInterval(state.timer);
    state.timer = null;
    state.busy = false;
    el("repo-submit").disabled = false;
    el("repo-cancel").disabled = true;
  };
  async function loadProviders() {
    try {
      const res = await fetch("/api/sandbox/providers", { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      const available = (data.providers || []).filter(p => p.available).map(p => p.name);
      setText("repo-provider", available.length ? "Available: " + available.join(", ") : "Unavailable: no real sandbox provider configured");
      el("repo-provider").className = available.length ? "repo-provider repo-online" : "repo-provider repo-offline";
    } catch (err) {
      setText("repo-provider", "Provider status unavailable: " + err.message);
      el("repo-provider").className = "repo-provider repo-offline";
    }
  }
  async function loadExample() {
    try {
      const res = await fetch("/api/repository-example", { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      el("repo-trace").value = JSON.stringify(data.trace, null, 2);
      if (data.repo_url) el("repo-url").value = data.repo_url;
      if (data.commit_sha) el("repo-sha").value = data.commit_sha;
      if (data.manifest_path) el("repo-manifest").value = data.manifest_path;
      status("Executable test trace loaded. Submit it to create real sandbox evidence.");
    } catch (err) {
      status("Could not load fixture: " + err.message, true);
    }
  }
  function render(job) {
    if (!job || !job.phase) return;
    state.job = job;
    setText("repo-phase", job.phase);
    setText("repo-job-id", job.job_id);
    const events = el("repo-events");
    events.replaceChildren();
    for (const entry of job.events || []) {
      const detail = Object.entries(entry.detail || {}).map(([k, v]) => k + ": " + String(v)).join(" · ");
      const instant = Number.isFinite(entry.timestamp) ? new Date(entry.timestamp * 1000).toLocaleTimeString() : "—";
      addRow(events, [instant, entry.phase, detail]);
    }
    const result = job.result;
    if (!result) {
      setText("repo-summary", job.phase === "CANCELLED" ? "Cancelled by backend before execution." : terminal.has(job.phase) ? "Waiting for final server result…" : "Waiting for server execution evidence…");
      return;
    }
    el("repo-download").disabled = false;
    const executions = el("repo-executions");
    executions.replaceChildren();
    for (const run of result.executions || []) {
      addRow(executions, [run.stage, run.trace_length + " actions", run.status, run.run_id, run.trace_sha256], run.status === "EXECUTION_ERROR" ? "repo-error" : "");
    }
    if (job.phase === "FAILED") {
      setText("repo-summary", "FAILED: " + (result.error_code || "UNKNOWN") + " — " + (result.detail || "No detail"));
      el("repo-summary").className = "repo-summary repo-error";
      return;
    }
    if (job.phase === "CANCELLED") {
      setText("repo-summary", "Job cancelled before execution.");
      return;
    }
    if (job.phase !== "COMPLETED") return;
    const trials = result.trials || [];
    const passed = trials.filter(t => t.status === "REPRODUCED" && t.failure_id === result.failure_id).length;
    const reduction = Array.isArray(result.reduced_steps) ? result.reduced_steps : [];
    const original = Array.isArray(result.original_steps) ? result.original_steps : [];
    const certified = result.minimality && result.minimality.certified === true;
    const fix = result.fixed_passes === true ? "NOT_REPRODUCED" : result.fixed_passes === false ? "FAILED" : "NOT_CHECKED";
    setText("repo-summary", (result.job_status === "REPRODUCED" ? "Verified execution: " : "Unstable result: ") +
      original.length + " → " + (result.job_status === "REPRODUCED" ? reduction.length : "?") + " actions · " +
      passed + "/" + trials.length + " fresh confirmations · fix: " + fix +
      " · " + (certified ? "one-minimal certified" : "bounded-local only"));
    el("repo-summary").className = result.job_status === "REPRODUCED" ? "repo-summary repo-online" : "repo-summary repo-error";
    setText("repo-failure", result.failure_id || "—");
    setText("repo-commit", result.commit_sha || "—");
    setText("repo-provider-used", result.provider || "—");
    setText("repo-original", JSON.stringify(result.original || {}, null, 2));
    setText("repo-reduced", result.job_status === "REPRODUCED" ? JSON.stringify(reduction, null, 2) : "No confirmed proof available.");
    setText("repo-certificate", JSON.stringify(result.minimality || {}, null, 2));
    const checks = el("repo-confirmations");
    checks.replaceChildren();
    for (const [index, trial] of trials.entries()) {
      const ok = trial.status === "REPRODUCED" && trial.failure_id === result.failure_id;
      addRow(checks, ["#" + (index + 1), ok ? "MATCH" : "DIVERGED", trial.status, trial.run_id || "ID unavailable"], ok ? "repo-online" : "repo-error");
    }
  }
  async function poll() {
    if (!state.jobId || state.polling) return;
    state.polling = true;
    try {
      const res = await fetch("/api/jobs/" + encodeURIComponent(state.jobId), { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const job = await res.json();
      if (job.job_id !== state.jobId) return;
      render(job);
      if (terminal.has(job.phase) && (job.result || job.phase === "CANCELLED")) {
        stopPolling();
        status(job.phase === "COMPLETED" ? "Job finished; inspect server evidence." : "Job ended: " + job.phase, job.phase !== "COMPLETED");
      }
    } catch (err) {
      status("Polling interrupted: " + err.message + ". Retry by refreshing the page and reopening the job ID.", true);
      stopPolling();
    } finally {
      state.polling = false;
    }
  }
  async function submit() {
    if (state.busy) return;
    let trace;
    try {
      trace = JSON.parse(el("repo-trace").value);
      if (!Array.isArray(trace) || trace.length < 1 || trace.length > 40 || !trace.every(x => x && typeof x === "object" && !Array.isArray(x))) {
        throw new Error("Trace must be 1–40 action objects.");
      }
      const payload = JSON.stringify({
        repo_url: el("repo-url").value.trim(),
        commit_sha: el("repo-sha").value.trim(),
        manifest_path: el("repo-manifest").value.trim() || ".sequenceproof/manifest.json",
        trace
      });
      if (new TextEncoder().encode(payload).length > 32768) throw new Error("Request exceeds 32 KiB.");
      state.busy = true;
      el("repo-submit").disabled = true;
      el("repo-download").disabled = true;
      el("repo-cancel").disabled = false;
      el("repo-executions").replaceChildren();
      el("repo-confirmations").replaceChildren();
      setText("repo-summary", "Submitting repository job…");
      const res = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload });
      const data = await res.json();
      if (!res.ok) throw new Error((data.error_code ? data.error_code + ": " : "") + (data.error || "HTTP " + res.status));
      state.jobId = data.job_id;
      status("Job accepted. Showing only backend-reported phases.");
      await poll();
      if (state.busy) state.timer = setInterval(poll, 1500);
    } catch (err) {
      stopPolling();
      status("Submission failed: " + err.message, true);
    }
  }
  async function cancel() {
    if (!state.jobId) return;
    try {
      const res = await fetch("/api/jobs/" + encodeURIComponent(state.jobId), { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "HTTP " + res.status);
      status("Cancellation confirmed by backend.");
      await poll();
    } catch (err) {
      status("Cancellation unavailable: " + err.message + ". Active jobs finish and clean up normally.", true);
    }
  }
  function download() {
    if (!state.job || !state.job.result) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(state.job, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "sequenceproof-repository-" + state.job.job_id + ".json";
    a.click();
    URL.revokeObjectURL(url);
  }
  el("repo-submit").addEventListener("click", submit);
  el("repo-cancel").addEventListener("click", cancel);
  el("repo-download").addEventListener("click", download);
  el("repo-load-example").addEventListener("click", loadExample);
  loadProviders();
})();
