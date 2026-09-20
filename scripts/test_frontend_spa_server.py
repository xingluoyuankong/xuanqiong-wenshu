#!/usr/bin/env python3
"""Regression tests for scripts/frontend_spa_server.py."""

from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))

from frontend_spa_server import create_server  # noqa: E402


class FrontendSPAServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "dist"
        (self.root / "assets").mkdir(parents=True)
        (self.root / "index.html").write_text(
            "<!doctype html><html><body>SPA INDEX</body></html>\n",
            encoding="utf-8",
        )
        (self.root / "assets" / "app.js").write_text(
            "console.log('static asset');\n", encoding="utf-8"
        )
        (self.root / "assets" / "style.css").write_text(
            "body { color: black; }\n", encoding="utf-8"
        )
        self.outside = Path(self.temp_dir.name) / "outside-secret.txt"
        self.outside.write_text("outside secret\n", encoding="utf-8")

        self.server = create_server(self.root, host="127.0.0.1", port=0)
        self.thread = threading.Thread(
            target=self.server.serve_forever, name="spa-test-server", daemon=True
        )
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp_dir.cleanup()

    def request(self, path: str) -> tuple[int, bytes, str]:
        request = Request(self.base_url + path, method="GET")
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, response.read(), response.headers.get(
                    "Content-Type", ""
                )
        except HTTPError as error:
            return error.code, error.read(), error.headers.get("Content-Type", "")

    def test_root_and_real_static_file_are_served(self) -> None:
        status, body, content_type = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"SPA INDEX", body)
        self.assertTrue(content_type.startswith("text/html"))

        status, body, content_type = self.request("/assets/app.js?cache=1")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"console.log('static asset');\n")
        self.assertTrue(content_type.startswith("text/javascript"))

    def test_unknown_extensionless_route_falls_back_to_index(self) -> None:
        status, body, content_type = self.request("/novel/chapters/42")
        self.assertEqual(status, 200)
        self.assertIn(b"SPA INDEX", body)
        self.assertTrue(content_type.startswith("text/html"))

    def test_missing_extension_asset_is_not_fallback(self) -> None:
        status, _body, _content_type = self.request("/assets/missing.js")
        self.assertEqual(status, 404)
        status, _body, _content_type = self.request("/missing.css")
        self.assertEqual(status, 404)
        status, _body, _content_type = self.request("/missing.route.json")
        self.assertEqual(status, 404)

    def test_api_paths_are_not_owned_by_frontend_server(self) -> None:
        for path in ("/api", "/api/health", "/api/unknown-route"):
            with self.subTest(path=path):
                status, _body, _content_type = self.request(path)
                self.assertEqual(status, 404)

    def test_path_traversal_is_rejected(self) -> None:
        traversal_paths = (
            "/../outside-secret.txt",
            "/%2e%2e/outside-secret.txt",
            "/%2e%2e/%2e%2e/outside-secret.txt",
            "/%5C%5Coutside-secret.txt",
        )
        for path in traversal_paths:
            with self.subTest(path=path):
                status, body, _content_type = self.request(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"outside secret", body)

    def test_existing_directory_is_not_listed_or_treated_as_route(self) -> None:
        status, body, _content_type = self.request("/assets")
        self.assertEqual(status, 404)
        self.assertNotIn(b"SPA INDEX", body)

    def test_symlink_outside_document_root_is_rejected(self) -> None:
        link = self.root / "outside.txt"
        try:
            link.symlink_to(self.outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable")
        status, body, _content_type = self.request("/outside.txt")
        self.assertEqual(status, 404)
        self.assertNotIn(b"outside secret", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)