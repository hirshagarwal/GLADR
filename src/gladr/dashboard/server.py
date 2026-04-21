"""Local HTTP server for the dynamic dashboard."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import urlparse

from gladr.core.paths import ProjectPaths
from gladr.dashboard.manifest_loader import load_dashboard_payload


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def serve_dashboard(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Serve the dashboard and dynamic artifact API until interrupted."""

    paths = ProjectPaths.discover()
    paths.ensure_runtime_dirs()
    handler = _handler_factory(paths)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}"
    print(f"Serving GLADR dashboard at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping GLADR dashboard.")
    finally:
        server.server_close()


def _handler_factory(paths: ProjectPaths) -> type[BaseHTTPRequestHandler]:
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
            route = urlparse(self.path).path
            if route in {"/", "/index.html"}:
                self._send_html(_load_index_html())
                return

            if route == "/api/dashboard-data":
                self._send_json(load_dashboard_payload(paths))
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}")

        def _send_html(self, content: str) -> None:
            encoded = content.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

    return DashboardRequestHandler


def _load_index_html() -> str:
    source = resources.files("gladr.dashboard.static_app").joinpath("index.html")
    return source.read_text(encoding="utf-8")
