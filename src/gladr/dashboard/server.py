"""Local HTTP server for the dynamic dashboard."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import urlparse

from gladr.analysis.runner import run_parameterized_analysis
from gladr.core.paths import ProjectPaths
from gladr.dashboard.manifest_loader import load_dashboard_payload
from gladr.ingestion.workbench import (
    build_ingestion_workbench_payload,
    preview_ingestion_spec,
    run_ingestion_spec_from_ui,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def serve_dashboard(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, paths: ProjectPaths | None = None) -> None:
    """Serve the dashboard and dynamic artifact API until interrupted."""

    paths = paths or ProjectPaths.discover()
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

            if route == "/api/ingestion-workbench":
                self._send_json(build_ingestion_workbench_payload(paths))
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
            route = urlparse(self.path).path
            if route == "/api/ingestion-preview":
                self._handle_ingestion_preview()
                return

            if route == "/api/ingestion-runs":
                self._handle_ingestion_run()
                return

            if route != "/api/analysis-runs":
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return

            self._handle_analysis_run()

        def _handle_ingestion_preview(self) -> None:
            try:
                payload = self._read_json_body()
                preview = preview_ingestion_spec(
                    str(payload.get("adapter_id") or ""),
                    payload.get("source_file") if payload.get("source_file") is not None else None,
                    payload.get("spec") if isinstance(payload.get("spec"), dict) else None,
                    paths=paths,
                )
            except (OSError, ValueError, KeyError) as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json(preview)

        def _handle_ingestion_run(self) -> None:
            try:
                payload = self._read_json_body()
                written = run_ingestion_spec_from_ui(
                    str(payload.get("adapter_id") or ""),
                    payload.get("source_file") if payload.get("source_file") is not None else None,
                    payload.get("spec") if isinstance(payload.get("spec"), dict) else None,
                    paths=paths,
                )
            except (OSError, ValueError, KeyError) as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({
                "artifacts": {name: path.name for name, path in written.items()},
                "dashboard": load_dashboard_payload(paths),
            }, status=HTTPStatus.CREATED)

        def _handle_analysis_run(self) -> None:
            try:
                payload = self._read_json_body()
                template_id = str(payload.get("template_id") or "")
                parameters = payload.get("parameters")
                if not isinstance(parameters, dict):
                    raise ValueError("Request must include parameter object.")
                output_path = run_parameterized_analysis(template_id, parameters, paths=paths)
            except (OSError, ValueError, KeyError) as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({
                "artifact": output_path.name,
                "dashboard": load_dashboard_payload(paths),
            }, status=HTTPStatus.CREATED)

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

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def _read_json_body(self) -> dict[str, Any]:
            content_length = int(self.headers.get("Content-Length") or "0")
            if content_length <= 0:
                return {}
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")
            return payload

    return DashboardRequestHandler


def _load_index_html() -> str:
    source = resources.files("gladr.dashboard.static_app").joinpath("index.html")
    return source.read_text(encoding="utf-8")
