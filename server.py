from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os

from sequenceproof import SAMPLE, analyze

ROOT = Path(__file__).parent
STATIC_FILES = {
    "/static/styles.css": (ROOT / "static" / "styles.css", "text/css; charset=utf-8"),
    "/static/app.js": (ROOT / "static" / "app.js", "text/javascript; charset=utf-8"),
}


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
        if self.path == "/api/sample":
            return self.respond({"title": "Card changed during checkout retry", "trace": SAMPLE,
                                 "issue": "A retry sometimes charges the old card after the customer chooses a new one."})
        if self.path in {"/", "/index.html"}:
            body = (ROOT / "index.html").read_bytes()
            return self.send_bytes(body, "text/html; charset=utf-8")
        if self.path in STATIC_FILES:
            path, content_type = STATIC_FILES[self.path]
            return self.send_bytes(path.read_bytes(), content_type)
        self.respond({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path != "/api/analyze":
            return self.respond({"error": "Not found"}, 404)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 32768:
                return self.respond({"error": "Request must be between 1 and 32768 bytes"}, 413)
            data = json.loads(self.rfile.read(size))
            return self.respond(analyze(data.get("trace")))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.respond({"error": str(exc)}, 400)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"SequenceProof at http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
