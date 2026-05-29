"""Local HTTP server for the dynamic dashboard."""

from __future__ import annotations

import json
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from gladr.analysis.runner import run_parameterized_analysis
from gladr.analysis.templates import list_analysis_templates
from gladr.core.paths import (
    ProjectPaths,
    create_local_project,
    list_registered_projects,
    paths_from_project_args,
    read_project_metadata,
    set_active_project,
)
from gladr.core.run_context import DEFAULT_TIMEZONE
from gladr.dashboard.manifest_loader import load_dashboard_payload
from gladr.ingestion.workbench import (
    build_ingestion_workbench_payload,
    preview_ingestion_spec,
    run_ingestion_spec_from_ui,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.13 includes zoneinfo.
    ZoneInfo = None  # type: ignore[assignment]


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class DashboardProjectState:
    def __init__(self, initial_paths: ProjectPaths | None = None) -> None:
        self._initial_paths = initial_paths
        self._active_project_id: str | None = None

    def current_paths(self) -> ProjectPaths | None:
        if self._active_project_id:
            try:
                return paths_from_project_args(project_id=self._active_project_id)
            except (FileNotFoundError, ValueError):
                self._active_project_id = None

        if self._initial_paths:
            return self._initial_paths

        try:
            return ProjectPaths.discover()
        except FileNotFoundError:
            return None

    def create_project(self, project_id: str, label: str | None = None) -> ProjectPaths:
        context = create_local_project(project_id=project_id, label=label, set_active=True)
        self._active_project_id = context.project_id
        self._initial_paths = None
        return context.paths

    def set_active_project(self, project_id: str) -> ProjectPaths:
        context = set_active_project(project_id)
        self._active_project_id = context.project_id
        self._initial_paths = None
        return context.paths


def serve_dashboard(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, paths: ProjectPaths | None = None) -> None:
    """Serve the dashboard and dynamic artifact API until interrupted."""

    if paths:
        paths.ensure_runtime_dirs()
    project_state = DashboardProjectState(paths)
    handler = _handler_factory(project_state)
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


def _handler_factory(project_state: DashboardProjectState) -> type[BaseHTTPRequestHandler]:
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
            route = urlparse(self.path).path
            if route in {"/", "/index.html"}:
                self._send_html(_load_index_html())
                return

            if route == "/api/dashboard-data":
                self._send_json(_dashboard_payload(project_state.current_paths()))
                return

            if route == "/api/projects":
                self._send_json(list_registered_projects())
                return

            if route == "/api/ingestion-workbench":
                paths = self._active_paths_required()
                if paths is None:
                    return
                self._send_json(build_ingestion_workbench_payload(paths))
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
            route = urlparse(self.path).path
            if route == "/api/projects":
                self._handle_project_create()
                return

            if route == "/api/projects/active":
                self._handle_project_switch()
                return

            if route == "/api/ingestion-preview":
                self._handle_ingestion_preview()
                return

            if route == "/api/ingestion-runs":
                self._handle_ingestion_run()
                return

            if route == "/api/ingestion-upload":
                self._handle_ingestion_upload()
                return

            if route != "/api/analysis-runs":
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return

            self._handle_analysis_run()

        def _handle_project_create(self) -> None:
            try:
                payload = self._read_json_body()
                project_id = str(payload.get("id") or "").strip()
                label = str(payload.get("label") or "").strip() or None
                paths = project_state.create_project(project_id, label)
            except (OSError, ValueError) as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({
                "project": _project_payload(paths),
                "projects": list_registered_projects(),
                "dashboard": _dashboard_payload(paths),
            }, status=HTTPStatus.CREATED)

        def _handle_project_switch(self) -> None:
            try:
                payload = self._read_json_body()
                project_id = str(payload.get("id") or "").strip()
                paths = project_state.set_active_project(project_id)
            except (OSError, ValueError, FileNotFoundError) as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({
                "project": _project_payload(paths),
                "projects": list_registered_projects(),
                "dashboard": _dashboard_payload(paths),
            })

        def _handle_ingestion_preview(self) -> None:
            paths = self._active_paths_required()
            if paths is None:
                return
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
            paths = self._active_paths_required()
            if paths is None:
                return
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
                "dashboard": _dashboard_payload(paths),
            }, status=HTTPStatus.CREATED)

        def _handle_ingestion_upload(self) -> None:
            paths = self._active_paths_required()
            if paths is None:
                return
            try:
                payload = self._read_json_body()
                filename = _safe_upload_filename(str(payload.get("filename") or ""))
                content = payload.get("content")
                if not isinstance(content, str):
                    raise ValueError("Upload request must include CSV content.")
                upload_dir = paths.raw_data_dir / "imports"
                upload_dir.mkdir(parents=True, exist_ok=True)
                output_path = upload_dir / filename
                output_path.write_text(content, encoding="utf-8")
                workbench = build_ingestion_workbench_payload(paths)
            except (OSError, ValueError, KeyError) as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({
                "file": {
                    "name": output_path.name,
                    "path": output_path.relative_to(paths.root).as_posix(),
                },
                "workbench": workbench,
            }, status=HTTPStatus.CREATED)

        def _handle_analysis_run(self) -> None:
            paths = self._active_paths_required()
            if paths is None:
                return
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
                "dashboard": _dashboard_payload(paths),
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

        def _active_paths_required(self) -> ProjectPaths | None:
            paths = project_state.current_paths()
            if paths is None:
                self._send_json(
                    {"error": "Select or create a GLADR project first."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return None
            return paths

    return DashboardRequestHandler


def _load_index_html() -> str:
    source = resources.files("gladr.dashboard.static_app").joinpath("index.html")
    return source.read_text(encoding="utf-8")


def _safe_upload_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        raise ValueError("Upload filename is required.")
    if Path(name).suffix.lower() != ".csv":
        raise ValueError("Only CSV uploads are supported.")
    return name


def _dashboard_payload(paths: ProjectPaths | None) -> dict[str, Any]:
    if paths is None:
        return _empty_dashboard_payload()
    payload = load_dashboard_payload(paths)
    payload["project"] = _project_payload(paths)
    payload["projects"] = list_registered_projects()
    return payload


def _empty_dashboard_payload() -> dict[str, Any]:
    return {
        "generated_at": _now_iso(),
        "project": None,
        "projects": list_registered_projects(),
        "latest": {
            "clean": {},
            "stats": {},
        },
        "summary": {
            "ingestion_runs": 0,
            "analysis_artifacts": 0,
            "visualizations": 0,
        },
        "dataset_profile": {"dataset": None, "variables": []},
        "analysis_templates": list_analysis_templates(),
        "ingestion_workbench": {"adapters": [], "canonical_fields": [], "data_files": []},
        "ingestion_runs": [],
        "analyses": [],
        "pipeline": [],
        "stage_summaries": [],
    }


def _project_payload(paths: ProjectPaths) -> dict[str, Any]:
    metadata = read_project_metadata(paths.root)
    return {
        "id": paths.project_id or metadata.get("id"),
        "label": metadata.get("label") or paths.project_id or paths.root.name,
        "path": str(paths.root),
    }


def _now_iso() -> str:
    if ZoneInfo is None:
        return datetime.now().astimezone().isoformat()
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).isoformat()
