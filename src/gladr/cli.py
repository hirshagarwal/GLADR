"""Command-line entry point for GLADR."""

from __future__ import annotations

import argparse

from gladr.analysis.runner import run_analysis
from gladr.core.paths import paths_from_project_args
from gladr.dashboard.build import build_dashboard
from gladr.dashboard.server import DEFAULT_HOST, DEFAULT_PORT, serve_dashboard
from gladr.ingestion.histology import run_histology_ingestion
from gladr.ingestion.runner import run_ingestion


def add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", help="Registered local project id")
    parser.add_argument("--project-root", help="Path to a GLADR project workspace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gladr")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Run ingestion adapters")
    add_project_args(ingest_parser)
    ingest_parser.add_argument("--adapter", help="Specific adapter id to run")
    ingest_parser.add_argument("--file", help="Optional source file path override")

    histology_parser = subparsers.add_parser("ingest-histology", help="Run histology text report ingestion")
    add_project_args(histology_parser)
    histology_parser.add_argument("--txt-dir", help="Directory containing raw histology .txt files")
    histology_parser.add_argument("--csv-dir", help="Directory for per-report histology CSV files")
    histology_parser.add_argument("--output", help="Optional combined histology report CSV path")
    histology_parser.add_argument("--model", default="gpt-5-nano", help="OpenAI model for per-report extraction")
    histology_parser.add_argument("--override", action="store_true", help="Regenerate per-report CSVs that already exist")
    histology_parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Compile existing per-report CSVs without generating missing CSVs",
    )

    analyze_parser = subparsers.add_parser("analyze", help="Run analysis scripts")
    add_project_args(analyze_parser)
    analyze_parser.add_argument("--scripts", nargs="+", help="Specific analysis script ids")

    dashboard_parser = subparsers.add_parser("dashboard", help="Build or serve the dashboard")
    add_project_args(dashboard_parser)
    dashboard_parser.add_argument("--serve", action="store_true", help="Run a local dynamic dashboard server")
    dashboard_parser.add_argument("--host", default=DEFAULT_HOST, help="Dashboard server host")
    dashboard_parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Dashboard server port")

    run_all_parser = subparsers.add_parser("run-all", help="Run ingestion, analysis, and dashboard")
    add_project_args(run_all_parser)
    run_all_parser.add_argument("--adapter", help="Specific adapter id to run")
    run_all_parser.add_argument("--file", help="Optional source file path override")
    run_all_parser.add_argument("--scripts", nargs="+", help="Specific analysis script ids")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        paths = paths_from_project_args(project_root=args.project_root, project_id=args.project)
        run_ingestion(adapter_id=args.adapter, source_file=args.file, paths=paths)
        return

    if args.command == "ingest-histology":
        paths = paths_from_project_args(project_root=args.project_root, project_id=args.project)
        run_histology_ingestion(
            txt_dir=args.txt_dir,
            csv_dir=args.csv_dir,
            output_file=args.output,
            csv_override=args.override,
            generate_reports=not args.no_generate,
            model=args.model,
            paths=paths,
        )
        return

    if args.command == "analyze":
        paths = paths_from_project_args(project_root=args.project_root, project_id=args.project)
        run_analysis(script_ids=args.scripts, paths=paths)
        return

    if args.command == "dashboard":
        paths = paths_from_project_args(project_root=args.project_root, project_id=args.project)
        if args.serve:
            serve_dashboard(host=args.host, port=args.port, paths=paths)
            return
        build_dashboard(paths)
        return

    if args.command == "run-all":
        paths = paths_from_project_args(project_root=args.project_root, project_id=args.project)
        run_ingestion(adapter_id=args.adapter, source_file=args.file, paths=paths)
        run_analysis(script_ids=args.scripts, paths=paths)
        build_dashboard(paths)
        return

    parser.error(f"Unknown command: {args.command}")
