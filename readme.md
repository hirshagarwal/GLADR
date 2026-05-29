# GLADR

GLADR is a package-first clinical research analysis pipeline. The committed repository contains reusable code, contracts, tests, and sanitized examples. Local research projects live in separate project workspaces that own private data, saved specs, outputs, notebooks, and deliverables.

The system has three runtime stages:

1. **Ingestion** converts raw source files into a canonical clean dataset.
2. **Analysis** reads the latest clean dataset and writes versioned stats artifacts.
3. **Dashboard** discovers generated artifacts and renders pipeline status, history, stats, and visualization contracts.

Every pipeline output is versioned by run id. `latest.json` files point downstream code to the current artifact, but older outputs remain available for history and comparison.

## Quick Start

Commands can be run either through uv or through an already prepared Python environment:

- Preferred: `uv run python main.py ...`, which uses the locked project environment.
- Also valid: `python main.py ...`, after activating an environment with the project dependencies installed.

The examples below use `uv run python`. Drop `uv run` if you are intentionally using raw Python from your active environment.

Run the full pipeline:

```bash
uv run python main.py run-all --project-root /path/to/project
```

Serve the dynamic dashboard:

```bash
uv run python main.py dashboard --serve
```

Open:

```text
http://127.0.0.1:8765
```

If you generate new ingestion or analysis artifacts while the server is running, refresh the browser. The dashboard API scans the active project's `outputs/ingestion/` and `outputs/analysis/` directories on each request.

On first run, the served dashboard opens without requiring a project root. Create a project from the dashboard UI; new local projects default to `projects/<project_id>/`, which is gitignored along with the local `.gladr/` project registry.

## Current Commands

```bash
# Ingestion
uv run python main.py ingest --project-root /path/to/project
uv run python main.py ingest --project-root /path/to/project --adapter gbm_registry
uv run python main.py ingest --project-root /path/to/project --adapter gbm_registry --file data/raw/registry/main_sheet/example.csv

# Analysis
uv run python main.py analyze --project-root /path/to/project
uv run python main.py analyze --project-root /path/to/project --scripts cohort_summary age_distribution sex_breakdown

# Dashboard
uv run python main.py dashboard --project-root /path/to/project
uv run python main.py dashboard --serve
uv run python main.py dashboard --serve --project-root /path/to/project

# Full pipeline
uv run python main.py run-all --project-root /path/to/project
```

## Runtime Flow

```text
<project>/data/raw/registry/main_sheet/*.csv
  -> <project>/outputs/ingestion/canonical/datasets/clean_dataset_<run_id>.json
  -> <project>/outputs/ingestion/canonical/manifests/manifest_<run_id>.json
  -> <project>/outputs/ingestion/canonical/reports/quality_report_<run_id>.json
  -> <project>/outputs/ingestion/canonical/latest.json
  -> <project>/outputs/analysis/artifacts/<script_id>_<run_id>.json
  -> <project>/outputs/analysis/manifests/analysis_manifest_<run_id>.json
  -> <project>/outputs/analysis/latest.json
  -> dashboard API discovers artifacts and renders the browser UI
```

Histology text reports follow their own ingestion source lane:

```text
<project>/data/raw/histology/text_reports/*.txt
  -> <project>/data/interim/histology/extracted_marker_csv/*.csv
  -> <project>/outputs/ingestion/histology/datasets/histology_dataset_<run_id>.json
  -> <project>/outputs/ingestion/histology/manifests/manifest_<run_id>.json
  -> <project>/outputs/ingestion/histology/reports/extraction_report_<run_id>.json
  -> <project>/outputs/ingestion/histology/latest.json
```

The dashboard shell can be rebuilt into the active project's `outputs/dashboard/builds/index.html` with:

```bash
uv run python main.py dashboard --project-root /path/to/project
```

For normal use, prefer `uv run python main.py dashboard --serve`; the dynamic server exposes `/api/dashboard-data`, which the browser uses to load current artifacts for the selected project.

## Repository Layout

```text
GLADR/
├── examples/
│   └── starter_project/
├── src/
│   └── gladr/
│       ├── analysis/
│       ├── contracts/
│       ├── core/
│       ├── dashboard/
│       └── ingestion/
├── tests/
├── main.py
├── pyproject.toml
└── readme.md
```

Local project workspaces are intentionally gitignored:

```text
projects/<project_id>/
├── project.json
├── specs/
├── data/
├── outputs/
├── notebooks/
└── deliverables/
```

## Module-Local LLM Context

The pipeline is designed so a small LLM can work inside one stage folder with enough local context to make safe changes.

Each stage module now contains:

- `README.md`: human and LLM-oriented instructions.
- `module.yaml`: machine-readable module metadata, commands, ownership, contracts, examples, and LLM rules.
- `contracts/`: local copies or module-specific contracts.
- `examples/`: small representative inputs and outputs.
- implementation files for that stage.

The intended rule is:

> A small LLM should be able to make a safe stage-specific change by reading only that module's README, module.yaml, contracts, examples, tests, and one nearby implementation file.

### Ingestion Module

Location:

- [src/gladr/ingestion](/Users/hirsh/Documents/GLADR/src/gladr/ingestion)

Primary files:

- [src/gladr/ingestion/README.md](/Users/hirsh/Documents/GLADR/src/gladr/ingestion/README.md)
- [src/gladr/ingestion/module.yaml](/Users/hirsh/Documents/GLADR/src/gladr/ingestion/module.yaml)
- [src/gladr/ingestion/adapters/base_adapter.py](/Users/hirsh/Documents/GLADR/src/gladr/ingestion/adapters/base_adapter.py)
- [src/gladr/ingestion/adapters/gbm_registry.py](/Users/hirsh/Documents/GLADR/src/gladr/ingestion/adapters/gbm_registry.py)
- [src/gladr/ingestion/contracts/canonical_schema.json](/Users/hirsh/Documents/GLADR/src/gladr/ingestion/contracts/canonical_schema.json)

Use this module when changing how raw source data is read, normalized, validated, flagged, or converted into canonical records.

Canonical ingestion writes:

```text
outputs/ingestion/canonical/datasets/clean_dataset_<run_id>.json
outputs/ingestion/canonical/manifests/manifest_<run_id>.json
outputs/ingestion/canonical/reports/quality_report_<run_id>.json
outputs/ingestion/canonical/latest.json
```

Histology ingestion writes under `outputs/ingestion/histology/` in the active project and keeps generated per-report marker CSVs in the project's `data/interim/histology/extracted_marker_csv/`.

Do not edit these generated files manually. Change ingestion code and rerun ingestion.

### Analysis Module

Location:

- [src/gladr/analysis](/Users/hirsh/Documents/GLADR/src/gladr/analysis)

Primary files:

- [src/gladr/analysis/README.md](/Users/hirsh/Documents/GLADR/src/gladr/analysis/README.md)
- [src/gladr/analysis/module.yaml](/Users/hirsh/Documents/GLADR/src/gladr/analysis/module.yaml)
- [src/gladr/analysis/base_script.py](/Users/hirsh/Documents/GLADR/src/gladr/analysis/base_script.py)
- [src/gladr/analysis/runner.py](/Users/hirsh/Documents/GLADR/src/gladr/analysis/runner.py)
- [src/gladr/analysis/scripts](/Users/hirsh/Documents/GLADR/src/gladr/analysis/scripts)
- [src/gladr/analysis/contracts/analysis_artifact_schema.json](/Users/hirsh/Documents/GLADR/src/gladr/analysis/contracts/analysis_artifact_schema.json)

Use this module when adding or changing stats, experiments, or visualization contracts emitted by analysis scripts.

Current scripts:

- `cohort_summary`
- `age_distribution`
- `sex_breakdown`

Analysis writes:

```text
<project>/outputs/analysis/artifacts/<script_id>_<run_id>.json
<project>/outputs/analysis/manifests/analysis_manifest_<run_id>.json
<project>/outputs/analysis/latest.json
```

Each stats artifact is self-describing. It includes metadata, data, and optionally a `visualization` block that tells the dashboard how to render it.

### Dashboard Module

Location:

- [src/gladr/dashboard](/Users/hirsh/Documents/GLADR/src/gladr/dashboard)

Primary files:

- [src/gladr/dashboard/README.md](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/README.md)
- [src/gladr/dashboard/module.yaml](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/module.yaml)
- [src/gladr/dashboard/manifest_loader.py](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/manifest_loader.py)
- [src/gladr/dashboard/server.py](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/server.py)
- [src/gladr/dashboard/static_app/index.html](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/static_app/index.html)
- [src/gladr/dashboard/contracts/dashboard_payload_schema.json](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/contracts/dashboard_payload_schema.json)

Use this module when changing how artifacts are discovered, summarized, or rendered.

The current dashboard has:

- a default overview page with a visual pipeline stage summary
- stage status marks for ingestion, stats, and visualization
- clickable stage details
- previous/next history cycling for stage outputs
- summary metrics
- an analysis browser with filters
- renderers for scalar cards, tables, bars, histograms, and multi-panel outputs
- a runs view showing versioned ingestion lanes and downstream artifacts

The dashboard should remain a reader over artifacts and a thin control surface for server-owned runners. It should not become the source of truth for pipeline state or contain ingestion, analysis, or visualization logic in browser code.

## Shared Runtime

Shared utilities live under [src/gladr/core](/Users/hirsh/Documents/GLADR/src/gladr/core):

- [paths.py](/Users/hirsh/Documents/GLADR/src/gladr/core/paths.py): project path discovery.
- [run_context.py](/Users/hirsh/Documents/GLADR/src/gladr/core/run_context.py): run ids and timestamps.
- [latest_pointer.py](/Users/hirsh/Documents/GLADR/src/gladr/core/latest_pointer.py): `latest.json` reads and writes.
- [discovery.py](/Users/hirsh/Documents/GLADR/src/gladr/core/discovery.py): adapter and analysis script discovery.

Central runtime contracts live under [src/gladr/contracts](/Users/hirsh/Documents/GLADR/src/gladr/contracts). Module folders mirror relevant contracts locally so stage-specific agents can stay folder-scoped.

Tests verify that mirrored contracts remain synchronized.

## Artifact Versioning

The current policy is append-only:

- A new ingestion run creates source-scoped datasets, manifests, and reports.
- A new analysis run creates new stats artifacts.
- `latest.json` files move forward to point at the current artifacts.
- The dashboard discovers both latest and historical artifacts.

There is no pruning command yet. Old outputs should be kept unless intentionally archived or deleted in a future artifact-management command.

Recommended future cleanup behavior:

```bash
uv run python main.py artifacts list
uv run python main.py artifacts prune --keep-latest 10 --archive
```

That command does not exist yet; for now, artifact cleanup is manual and should be done carefully.

## Adding A New Data Source

1. Read [src/gladr/ingestion/README.md](/Users/hirsh/Documents/GLADR/src/gladr/ingestion/README.md).
2. Review the canonical schema in `src/gladr/ingestion/contracts/`.
3. Add a new adapter under `src/gladr/ingestion/adapters/`.
4. Return an `AdapterRunResult` with a canonical dataframe, quality report, and source summary.
5. Run ingestion.
6. Verify the source-scoped ingestion artifacts and dashboard overview.

The adapter discovery system picks up `BaseAdapter` subclasses automatically.

## Adding A New Analysis

1. Read [src/gladr/analysis/README.md](/Users/hirsh/Documents/GLADR/src/gladr/analysis/README.md).
2. Review `contracts/clean_dataset_schema.json`, `contracts/analysis_artifact_schema.json`, and `contracts/visualization_schema.json`.
3. Inspect one similar script in `src/gladr/analysis/scripts/`.
4. Add a new `BaseAnalysisScript` subclass.
5. Run:

```bash
uv run python main.py analyze --scripts <script_id>
```

6. Open the dashboard and inspect the artifact in the Analysis tab and pipeline overview.

Prefer one focused script per analysis question so outputs stay easy to version and compare.

## Updating The Dashboard

1. Read [src/gladr/dashboard/README.md](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/README.md).
2. If the data is already present in artifacts, update only dashboard code.
3. If the dashboard needs a new payload field, add it in `manifest_loader.py`.
4. If a new visualization type is needed, update the visualization contract and renderer.
5. Rebuild the static shell:

```bash
uv run python main.py dashboard --project-root /path/to/project
```

6. Serve and verify:

```bash
uv run python main.py dashboard --serve --project-root /path/to/project
```

## Testing

Run the test suite:

```bash
uv run python -B -m unittest discover -s tests
```

Current test coverage includes:

- adapter and analysis discovery
- latest-pointer reads and writes
- dashboard payload discovery
- module-local LLM context packet integrity
- mirrored contract synchronization

## Design Direction

The most important design constraint is that pipeline behavior should live in small, stage-owned modules:

- ingestion owns source normalization and clean artifacts
- analysis owns statistics and visualization contracts
- dashboard owns artifact discovery and rendering

Generated artifacts should be produced by running the pipeline, not by editing output files directly. This keeps the system reproducible, easier to automate with small LLMs, and easier to open source later.
