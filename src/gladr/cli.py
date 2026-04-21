"""Command-line entry point for GLADR."""

from __future__ import annotations

import argparse

from gladr.analysis.runner import run_analysis
from gladr.dashboard.build import build_dashboard
from gladr.dashboard.server import DEFAULT_HOST, DEFAULT_PORT, serve_dashboard
from gladr.ingest.runner import run_ingestion


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gladr")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Run ingestion adapters")
    ingest_parser.add_argument("--adapter", help="Specific adapter id to run")
    ingest_parser.add_argument("--file", help="Optional source file path override")

    analyze_parser = subparsers.add_parser("analyze", help="Run analysis scripts")
    analyze_parser.add_argument("--scripts", nargs="+", help="Specific analysis script ids")

    dashboard_parser = subparsers.add_parser("dashboard", help="Build or serve the dashboard")
    dashboard_parser.add_argument("--serve", action="store_true", help="Run a local dynamic dashboard server")
    dashboard_parser.add_argument("--host", default=DEFAULT_HOST, help="Dashboard server host")
    dashboard_parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Dashboard server port")

    run_all_parser = subparsers.add_parser("run-all", help="Run ingestion, analysis, and dashboard")
    run_all_parser.add_argument("--adapter", help="Specific adapter id to run")
    run_all_parser.add_argument("--file", help="Optional source file path override")
    run_all_parser.add_argument("--scripts", nargs="+", help="Specific analysis script ids")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        run_ingestion(adapter_id=args.adapter, source_file=args.file)
        return

    if args.command == "analyze":
        run_analysis(script_ids=args.scripts)
        return

    if args.command == "dashboard":
        if args.serve:
            serve_dashboard(host=args.host, port=args.port)
            return
        build_dashboard()
        return

    if args.command == "run-all":
        run_ingestion(adapter_id=args.adapter, source_file=args.file)
        run_analysis(script_ids=args.scripts)
        build_dashboard()
        return

    parser.error(f"Unknown command: {args.command}")
