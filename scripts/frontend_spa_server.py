#!/usr/bin/env python3
"""Small, security-conscious static file server with SPA history fallback.

The server intentionally owns only frontend static paths. API paths are left
unhandled so a separate backend remains the sole owner of ``/api``.
"""

from __future__ import annotations

import argparse
import mimetypes
import posixpath
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Type
from urllib.parse import unquote, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENT_ROOT = REPOSITORY_ROOT / "frontend" / "dist"


class SPARequestHandler(BaseHTTPRequestHandler):
    """Serve files below ``document_root`` and fall back to ``index.html``."""

    server_version = "XuanqiongSPAServer/1.0"
    sys_version = ""

    @property
    def document_root(self) -> Path:
        return self.server.document_root  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._dispatch(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._dispatch(send_body=False)

    def _dispatch(self, *, send_body: bool) -> None:
        request_path = self._decoded_path()
        if request_path is None:
            self._not_found()
            return

        # The frontend server must never become an accidental API fallback.
        if request_path == "/api" or request_path.startswith("/api/"):
            self._not_found()
            return

        candidate = self._safe_candidate(request_path)
        if candidate is None:
            self._not_found()
            return

        if candidate.is_file():
            self._send_file(candidate, send_body=send_body)
            return

        # Existing directories are never listed and never treated as routes.
        if candidate.exists():
            self._not_found()
            return

        # Missing paths with a suffix are assets, not client-side routes.
        if self._has_extension(request_path):
            self._not_found()
            return

        index_path = self._safe_candidate("/index.html")
        if index_path is not None and index_path.is_file():
            self._send_file(index_path, send_body=send_body)
            return

        self._not_found()

    def _decoded_path(self) -> str | None:
        try:
            raw_path = urlsplit(self.path).path
            decoded = unquote(raw_path, errors="strict")
        except (UnicodeDecodeError, ValueError):
            return None

        if not decoded.startswith("/") or "\x00" in decoded:
            return None
        # Reject Windows separators too, even though production runs on Linux.
        if "\\" in decoded:
            return None
        if any(part == ".." for part in decoded.split("/")):
            return None
        return decoded

    def _safe_candidate(self, request_path: str) -> Path | None:
        root = self.document_root
        relative = request_path.lstrip("/") or "index.html"
        candidate = (root / posixpath.normpath(relative)).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    @staticmethod
    def _has_extension(request_path: str) -> bool:
        final_component = request_path.rsplit("/", 1)[-1]
        return bool(final_component and Path(final_component).suffix)

    def _send_file(self, path: Path, *, send_body: bool) -> None:
        try:
            size = path.stat().st_size
            content_type = mimetypes.guess_type(path.name, strict=False)[0]
            source = path.open("rb")
        except (OSError, ValueError):
            # Do not expose filesystem details if a file disappears or becomes
            # unreadable between resolution and open/stat.
            self._not_found()
            return

        try:
            self.send_response(200)
            self.send_header(
                "Content-Type", content_type or "application/octet-stream"
            )
            self.send_header("Content-Length", str(size))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if send_body:
                shutil.copyfileobj(source, self.wfile)
        except (BrokenPipeError, ConnectionResetError):
            # The client may close a valid response early; do not attempt a
            # second response after status headers have already been sent.
            return
        finally:
            source.close()

    def _not_found(self) -> None:
        self.send_error(404, "Not Found")

    def log_message(self, format: str, *args: object) -> None:
        # Keep the standalone helper quiet by default; callers can subclass it
        # when access logging is desired.
        return


def make_handler(document_root: str | Path) -> Type[SPARequestHandler]:
    """Create a request handler bound to one resolved document root."""

    root = Path(document_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"document root is not a directory: {root}")

    class BoundSPARequestHandler(SPARequestHandler):
        pass

    # The server instance owns this value, which also makes test servers easy
    # to construct without global mutable state.
    BoundSPARequestHandler.__name__ = "BoundSPARequestHandler"
    return BoundSPARequestHandler


def create_server(
    document_root: str | Path,
    host: str = "127.0.0.1",
    port: int = 5174,
    handler_class: Type[SPARequestHandler] | None = None,
) -> ThreadingHTTPServer:
    """Build a threaded server without starting or changing any other service."""

    root = Path(document_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"document root is not a directory: {root}")
    handler = handler_class or make_handler(root)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    server.document_root = root  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_DOCUMENT_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5174)
    args = parser.parse_args()

    server = create_server(args.root, args.host, args.port)
    print(
        f"frontend_spa_server listening on http://{args.host}:{args.port} "
        f"root={server.document_root}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())