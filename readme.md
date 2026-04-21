# GLADR

GLADR is a package-first clinical registry analysis pipeline. It is currently built around a GBM registry, but the code is organized so new data sources, statistics, and dashboard views can be added through isolated pipeline modules rather than broad rewrites.

The system has three runtime stages:

1. **Ingestion** converts raw source files into a canonical clean dataset.
2. **Analysis** reads the latest clean dataset and writes versioned stats artifacts.
3. **Dashboard** discovers generated artifacts and renders pipeline status, history, stats, and visualization contracts.

Every pipeline output is versioned by run id. `latest.json` files point downstream code to the current artifact, but older outputs remain available for history and comparison.

## Quick Start

Run the full pipeline:

```bash
python main.py run-all
```

Serve the dynamic dashboard:

```bash
python main.py dashboard --serve
```

Open:

```text
http://127.0.0.1:8765
```

If you generate new ingestion or analysis artifacts while the server is running, refresh the browser. The dashboard API scans `outputs/clean/` and `outputs/stats/` on each request.

## Current Commands

```bash
# Ingestion
python main.py ingest
python main.py ingest --adapter gbm_registry
python main.py ingest --adapter gbm_registry --file data/raw/main_sheet/main_sheet_19.04.26.csv

# Analysis
python main.py analyze
python main.py analyze --scripts cohort_summary age_distribution sex_breakdown

# Dashboard
python main.py dashboard
python main.py dashboard --serve

# Full pipeline
python main.py run-all
```

## Runtime Flow

```text
data/raw/main_sheet/*.csv
  -> outputs/clean/clean_dataset_<run_id>.json
  -> outputs/clean/run_manifest_<run_id>.json
  -> outputs/clean/ingestion_report_<run_id>.json
  -> outputs/clean/latest.json
  -> outputs/stats/<script_id>_<run_id>.json
  -> outputs/stats/latest.json
  -> dashboard API discovers artifacts and renders the browser UI
```

The dashboard shell can be rebuilt into `outputs/dashboard/index.html` with:

```bash
python main.py dashboard
```

For normal use, prefer `python main.py dashboard --serve`; the dynamic server exposes `/api/dashboard-data`, which the browser uses to load current artifacts.

## Repository Layout

```text
GLADR/
├── data/
│   └── raw/
├── notebooks/
├── outputs/
│   ├── clean/
│   ├── stats/
│   └── dashboard/
├── src/
│   └── gladr/
│       ├── analysis/
│       ├── contracts/
│       ├── core/
│       ├── dashboard/
│       └── ingest/
├── tests/
├── main.py
├── pyproject.toml
└── readme.md
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

- [src/gladr/ingest](/Users/hirsh/Documents/GLADR/src/gladr/ingest)

Primary files:

- [src/gladr/ingest/README.md](/Users/hirsh/Documents/GLADR/src/gladr/ingest/README.md)
- [src/gladr/ingest/module.yaml](/Users/hirsh/Documents/GLADR/src/gladr/ingest/module.yaml)
- [src/gladr/ingest/adapters/base_adapter.py](/Users/hirsh/Documents/GLADR/src/gladr/ingest/adapters/base_adapter.py)
- [src/gladr/ingest/adapters/gbm_registry.py](/Users/hirsh/Documents/GLADR/src/gladr/ingest/adapters/gbm_registry.py)
- [src/gladr/ingest/contracts/canonical_schema.json](/Users/hirsh/Documents/GLADR/src/gladr/ingest/contracts/canonical_schema.json)

Use this module when changing how raw source data is read, normalized, validated, flagged, or converted into canonical records.

Ingestion writes:

```text
outputs/clean/clean_dataset_<run_id>.json
outputs/clean/run_manifest_<run_id>.json
outputs/clean/ingestion_report_<run_id>.json
outputs/clean/latest.json
```

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
outputs/stats/<script_id>_<run_id>.json
outputs/stats/latest.json
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

The dashboard should remain a reader over artifacts. It should not become the source of truth for pipeline state or execute pipeline logic.

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

- A new ingestion run creates a new clean dataset, manifest, and ingestion report.
- A new analysis run creates new stats artifacts.
- `latest.json` files move forward to point at the current artifacts.
- The dashboard discovers both latest and historical artifacts.

There is no pruning command yet. Old outputs should be kept unless intentionally archived or deleted in a future artifact-management command.

Recommended future cleanup behavior:

```bash
python main.py artifacts list
python main.py artifacts prune --keep-latest 10 --archive
```

That command does not exist yet; for now, artifact cleanup is manual and should be done carefully.

## Adding A New Data Source

1. Read [src/gladr/ingest/README.md](/Users/hirsh/Documents/GLADR/src/gladr/ingest/README.md).
2. Review the canonical schema in `src/gladr/ingest/contracts/`.
3. Add a new adapter under `src/gladr/ingest/adapters/`.
4. Return an `AdapterRunResult` with a canonical dataframe, ingestion report, and source summary.
5. Run ingestion.
6. Verify the clean artifacts and dashboard overview.

The adapter discovery system picks up `BaseAdapter` subclasses automatically.

## Adding A New Analysis

1. Read [src/gladr/analysis/README.md](/Users/hirsh/Documents/GLADR/src/gladr/analysis/README.md).
2. Review `contracts/clean_dataset_schema.json`, `contracts/analysis_artifact_schema.json`, and `contracts/visualization_schema.json`.
3. Inspect one similar script in `src/gladr/analysis/scripts/`.
4. Add a new `BaseAnalysisScript` subclass.
5. Run:

```bash
python main.py analyze --scripts <script_id>
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
python main.py dashboard
```

6. Serve and verify:

```bash
python main.py dashboard --serve
```

## Testing

Run the test suite:

```bash
python -B -m unittest discover -s tests
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

