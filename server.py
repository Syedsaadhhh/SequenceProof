"""SequenceProof HTTP server.

Existing endpoints (unchanged):
    GET  /                  HTML shell
    GET  /static/styles.css
    GET  /static/app.js
    GET  /api/sample        Checkout fixture trace
    POST /api/analyze       Checkout fixture analysis (compatibility preview)

New endpoints (Run 2.5):
    GET  /api/sandbox/providers     List available sandbox providers
    POST /api/jobs                  Submit a repository analysis job (202)
    GET  /api/jobs/{job_id}         Poll job status and result
    DELETE /api/jobs/{job_id}       Cancel a QUEUED job

Security:
    - FakeSandboxProvider is never selectable through HTTP.
    - No shell strings from the HTTP body enter any subprocess.
    - No host secrets are exposed in responses.
    - Static assets are served from an explicit allowlist only.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import threading

from sequenceproof import SAMPLE, analyze
from runner_contract import parse_job_request
from jobs import JobStore
from repository_runner import run_repository_analysis
from sandbox.daytona_provider import DaytonaSandboxProvider
from sandbox.docker_provider import DockerSandboxProvider

ROOT = Path(__file__).parent
STATIC_FILES = {
    "/static/styles.css": (ROOT / "static" / "styles.css", "text/css; charset=utf-8"),
    "/static/app.js": (ROOT / "static" / "app.js", "text/javascript; charset=utf-8"),
    "/static/repository.js": (ROOT / "static" / "repository.js", "text/javascript; charset=utf-8"),
}

# Singleton job store — bounded in-memory, no persistence.
_job_store = JobStore()

# Production providers (FakeSandboxProvider excluded).
_PROVIDERS = {
    "daytona": DaytonaSandboxProvider(),
    "docker": DockerSandboxProvider(),
}


def _get_provider():
    """Return the first available production provider, or None."""
    # Explicit selection via env var.
    selected = os.environ.get("SEQUENCEPROOF_PROVIDER")
    if selected:
        p = _PROVIDERS.get(selected)
        if p is not None and p.available:
            return p
        return None
    # Auto-select first available.
    for p in _PROVIDERS.values():
        if p.available:
            return p
    return None


def _provider_status() -> list[dict]:
    return [
        {
            "name": name,
            "available": p.available,
        }
        for name, p in _PROVIDERS.items()
    ]


def _run_job_thread(job, request_obj) -> None:
    """Execute a repository analysis job in a background thread."""
    if not job.claim():
        return  # A queued cancellation won before this worker started.
    provider = _get_provider()
    if provider is None:
        job.transition("FAILED", {
            "error_code": "SANDBOX_UNAVAILABLE",
            "detail": "No sandbox provider is available on this host. "
                      "Install the daytona SDK + DAYTONA_API_KEY, or Docker.",
        })
        job.set_result({
            "status": "FAILED",
            "error_code": "SANDBOX_UNAVAILABLE",
            "detail": "No sandbox provider available.",
        })
        return

    def phase_callback(phase: str, detail: dict) -> None:
        job.transition(phase, detail)

    result = run_repository_analysis(
        provider=provider,
        repo_url=request_obj.repo_url,
        commit_sha=request_obj.commit_sha,
        manifest_path=request_obj.manifest_path,
        trace=request_obj.trace,
        phase_callback=phase_callback,
    )
    final_phase = "COMPLETED" if result.get("status") == "COMPLETED" else "FAILED"
    job.set_result(result)
    job.transition(final_phase, {
        "error_code": result.get("error_code"),
        "job_status": result.get("job_status"),
    })


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def respond(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_bytes(body, "application/json; charset=utf-8", status)

    def do_GET(self):
        if self.path == "/api/repository-example":
            example = ROOT / "examples" / "stale-role-service" / "traces" / "noisy_reproducing.json"
            return self.respond({
                "source": "owned_executable_fixture",
                "trace": json.loads(example.read_text(encoding="utf-8")),
                "repo_url": os.environ.get("SEQUENCEPROOF_EXAMPLE_REPO", ""),
                "commit_sha": os.environ.get("SEQUENCEPROOF_EXAMPLE_SHA", ""),
                "manifest_path": ".sequenceproof/manifest.json",
            })
        if self.path == "/api/sample":
            return self.respond({
                "title": "Card changed during checkout retry",
                "trace": SAMPLE,
                "issue": "A retry sometimes charges the old card after the customer chooses a new one.",
            })

        if self.path == "/api/sandbox/providers":
            return self.respond({"providers": _provider_status()})

        # Job status.
        if self.path.startswith("/api/jobs/"):
            job_id = self.path[len("/api/jobs/"):]
            if not job_id:
                return self.respond({"error": "job_id required"}, 400)
            job = _job_store.get_job(job_id)
            if job is None:
                return self.respond({"error": "job not found"}, 404)
            return self.respond(job.to_dict())

        if self.path == "/api/jobs":
            return self.respond({"jobs": _job_store.all_jobs()})

        if self.path in {"/", "/index.html"}:
            body = (ROOT / "index.html").read_bytes()
            return self.send_bytes(body, "text/html; charset=utf-8")

        if self.path in STATIC_FILES:
            path, content_type = STATIC_FILES[self.path]
            return self.send_bytes(path.read_bytes(), content_type)

        self.respond({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/api/analyze":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 1 or size > 32768:
                    return self.respond(
                        {"error": "Request must be between 1 and 32768 bytes"}, 413
                    )
                data = json.loads(self.rfile.read(size))
                return self.respond(analyze(data.get("trace")))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return self.respond({"error": str(exc)}, 400)

        if self.path == "/api/jobs":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 1 or size > 32768:
                    return self.respond(
                        {"error": "Request must be between 1 and 32768 bytes"}, 413
                    )
                raw = json.loads(self.rfile.read(size))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return self.respond({"error": f"Invalid JSON: {exc}"}, 400)

            try:
                request_obj = parse_job_request(raw)
            except ValueError as exc:
                return self.respond({"error": str(exc), "error_code": "INVALID_REQUEST"}, 400)

            try:
                job = _job_store.create_job(raw)
            except ValueError as exc:
                return self.respond({"error": str(exc), "error_code": "QUEUE_FULL"}, 429)

            # Launch background thread.
            t = threading.Thread(
                target=_run_job_thread,
                args=(job, request_obj),
                daemon=True,
            )
            t.start()

            return self.respond(
                {
                    "job_id": job.job_id,
                    "phase": job.phase,
                    "message": "Job queued. Poll GET /api/jobs/{job_id} for status.",
                },
                status=202,
            )

        return self.respond({"error": "Not found"}, 404)

    def do_DELETE(self):
        if self.path.startswith("/api/jobs/"):
            job_id = self.path[len("/api/jobs/"):]
            if not job_id:
                return self.respond({"error": "job_id required"}, 400)
            cancelled = _job_store.cancel_job(job_id)
            if cancelled:
                return self.respond({"job_id": job_id, "phase": "CANCELLED"})
            job = _job_store.get_job(job_id)
            if job is None:
                return self.respond({"error": "job not found"}, 404)
            return self.respond(
                {"error": f"Job cannot be cancelled in phase {job.phase}",
                 "phase": job.phase},
                409,
            )
        return self.respond({"error": "Not found"}, 404)

    def log_message(self, fmt, *args):
        # Suppress default request logs in test mode; keep in server mode.
        import sys
        if os.environ.get("SEQUENCEPROOF_QUIET_LOG"):
            return
        super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"SequenceProof at http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
