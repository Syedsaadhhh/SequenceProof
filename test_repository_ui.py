"""Run 2.5 UI/API tests. FakeSandboxProvider runs real LOCAL subprocesses only."""
import json
import os
import re
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server
from sandbox.fake_provider import FakeSandboxProvider


FIXTURE = Path(__file__).parent / "examples" / "stale-role-service"


class RepositoryHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=3)

    def get(self, path):
        with urlopen(self.base + path, timeout=10) as response:
            return response.status, response.headers, json.loads(response.read())

    def post(self, path, body):
        request = Request(
            self.base + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_real_mode_html_and_static_asset(self):
        with urlopen(self.base + "/", timeout=10) as response:
            html = response.read()
        self.assertIn(b'id="repo-submit"', html)
        self.assertIn(b'/static/repository.js', html)
        with urlopen(self.base + "/static/repository.js", timeout=10) as response:
            js = response.read()
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn(b'/api/jobs', js)
        self.assertIn(b'/api/sandbox/providers', js)
        self.assertNotIn(b'fakeSuccess', js)
        self.assertNotIn(b'/static/app.js', html)
        self.assertNotIn(b'Built-in synthetic regression', html)

    def test_fixture_endpoint_identifies_executable_source(self):
        status, headers, data = self.get("/api/repository-example")
        self.assertEqual(status, 200)
        self.assertEqual(data["source"], "owned_executable_fixture")
        self.assertEqual(data["manifest_path"], ".sequenceproof/manifest.json")
        self.assertEqual(len(data["trace"]), 12)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_root_manifest_executes_embedded_fixture_from_repository_root(self):
        root = Path(__file__).parent
        manifest = json.loads((root / ".sequenceproof" / "manifest.json").read_text())
        trace_path = FIXTURE / "traces" / "noisy_reproducing.json"
        env = os.environ.copy()
        env["SEQUENCEPROOF_TRACE_PATH"] = str(trace_path)
        env["SEQUENCEPROOF_RUN_ID"] = "root-manifest-test"
        buggy = subprocess.run(
            [sys.executable, *manifest["runner"]["argv"][1:]],
            cwd=root, env=env, capture_output=True, text=True, timeout=20,
        )
        fixed = subprocess.run(
            [sys.executable, *manifest["runner"]["fixed_argv"][1:]],
            cwd=root, env=env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(buggy.returncode, 0, buggy.stderr)
        self.assertEqual(fixed.returncode, 0, fixed.stderr)
        self.assertEqual(json.loads(buggy.stdout.splitlines()[-1])["failure_id"], "STALE_ROLE_AUTHORIZATION")
        self.assertEqual(json.loads(fixed.stdout.splitlines()[-1])["status"], "NOT_REPRODUCED")

    def test_manifest_path_command_injection_rejected_before_execution(self):
        trace = [{"action": "view_dashboard"}]
        body = {
            "repo_url": "https://github.com/octocat/Hello-World",
            "commit_sha": "a" * 40,
            "manifest_path": ".sequenceproof/manifest.json;id",
            "trace": trace,
        }
        with self.assertRaises(HTTPError) as context:
            self.post("/api/jobs", body)
        self.assertEqual(context.exception.code, 400)

    def test_job_api_records_real_local_subprocess_execution(self):
        provider = FakeSandboxProvider(fixture_root=FIXTURE)
        trace = json.loads((FIXTURE / "traces" / "noisy_reproducing.json").read_text())
        body = {
            "repo_url": "https://github.com/octocat/Hello-World",
            "commit_sha": "a" * 40,
            "manifest_path": ".sequenceproof/manifest.json",
            "trace": trace,
        }
        with patch.object(server, "_get_provider", return_value=provider):
            status, accepted = self.post("/api/jobs", body)
            self.assertEqual(status, 202)
            job_id = accepted["job_id"]
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                _, _, job = self.get("/api/jobs/" + job_id)
                if job["phase"] in {"COMPLETED", "FAILED"} and job.get("result"):
                    break
                time.sleep(0.2)
            else:
                self.fail("Local subprocess job timed out")
        self.assertEqual(job["phase"], "COMPLETED", job.get("result"))
        result = job["result"]
        self.assertEqual(result["job_status"], "REPRODUCED")
        self.assertEqual(result["failure_id"], "STALE_ROLE_AUTHORIZATION")
        self.assertEqual(len(result["trials"]), 5)
        self.assertTrue(all(t["status"] == "REPRODUCED" for t in result["trials"]))
        self.assertEqual(len({t["run_id"] for t in result["trials"]}), 5)
        self.assertIs(result["fixed_passes"], True)
        self.assertIs(result["minimality"]["certified"], True)
        executions = result["executions"]
        self.assertEqual(len(executions), 1 + result["attempts"] + 5 + 1)
        self.assertEqual(len({x["run_id"] for x in executions}), len(executions))
        self.assertTrue(all(re.fullmatch("[0-9a-f]{64}", x["trace_sha256"]) for x in executions))
        phases = [e["phase"] for e in job["events"]]
        self.assertLess(phases.index("REDUCING"), phases.index("CONFIRMING"))
        self.assertLess(phases.index("CONFIRMING"), phases.index("VERIFYING_FIXED"))
        self.assertEqual(provider._sandboxes, {}, "Local fixture sandbox was not destroyed")


class JobClaimTests(unittest.TestCase):
    def test_claimed_work_cannot_be_cancelled(self):
        from jobs import JobStore
        store = JobStore()
        job = store.create_job({"trace": []})
        self.assertTrue(job.claim())
        self.assertFalse(store.cancel_job(job.job_id))
        self.assertEqual(job.phase, "QUEUED")

    def test_cancelled_job_can_never_start(self):
        from jobs import JobStore
        store = JobStore()
        job = store.create_job({"trace": []})
        self.assertTrue(store.cancel_job(job.job_id))
        self.assertFalse(job.claim())
        self.assertEqual(job.phase, "CANCELLED")


if __name__ == "__main__":
    unittest.main()
