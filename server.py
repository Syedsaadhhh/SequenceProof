from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os

from sequenceproof import SAMPLE, analyze

ROOT = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def respond(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/sample":
            return self.respond({"title": "Card changed during checkout retry", "trace": SAMPLE,
                                 "issue": "A retry sometimes charges the old card after the customer chooses a new one."})
        if self.path in {"/", "/index.html"}:
            body = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
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
