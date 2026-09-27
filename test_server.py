import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from http.server import ThreadingHTTPServer

from server import Handler


class ServerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get(self, path):
        with urlopen(self.base_url + path, timeout=2) as response:
            return response.status, response.headers, response.read()

    def test_frontend_and_allowlisted_static_assets_are_served(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        # The product page is now repository-first; repository.js is the
        # only script loaded.  app.js is no longer referenced in the HTML
        # (checkout demo removed from product).
        self.assertIn(b'/static/styles.css', body)
        self.assertIn(b'/static/repository.js', body)
        self.assertNotIn(b'/static/app.js', body)

        _, css_headers, css = self.get("/static/styles.css")
        _, js_headers, js = self.get("/static/repository.js")
        self.assertTrue(css_headers["Content-Type"].startswith("text/css"))
        self.assertTrue(js_headers["Content-Type"].startswith("text/javascript"))
        self.assertGreater(len(css), 1000)
        self.assertGreater(len(js), 1000)
        self.assertEqual(css_headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(js_headers["X-Content-Type-Options"], "nosniff")

    def test_unallowlisted_source_file_is_not_exposed(self):
        with self.assertRaises(HTTPError) as context:
            self.get("/server.py")
        self.assertEqual(context.exception.code, 404)

    def test_api_exposes_all_retry_mismatches(self):
        trace = [
            {"action": "add_item", "item": "pen"},
            {"action": "begin_checkout"},
            {"action": "set_card", "card": "card-B"},
            {"action": "retry_payment"},
            {"action": "set_card", "card": "card-C"},
            {"action": "retry_payment"},
        ]
        request = Request(
            self.base_url + "/api/analyze",
            data=json.dumps({"trace": trace}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["status"], "REPRODUCED")
        self.assertEqual(payload["original"]["mismatch_count"], 2)
        self.assertEqual(len(payload["original"]["mismatches"]), 2)
        self.assertTrue(payload["minimality"]["certified"])


if __name__ == "__main__":
    unittest.main()
