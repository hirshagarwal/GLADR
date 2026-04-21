# GLADR

GLADR is a package-first clinical registry analysis pipeline. The current scaffold is built around a GBM registry, but the structure is designed so new sources and new analyses can be added with isolated files rather than pipeline rewrites.

## Quick Start

Run the full pipeline against the current raw data:

```bash
python main.py run-all
```

Serve the dynamic dashboard:

```bash
python main.py dashboard --serve
```

Open the dashboard in a browser:

```text
http://127.0.0.1:8765
```

If you add new raw data or create new analysis outputs while the server is running, refresh the browser. The dashboard scans the runtime output folders on each request, so it does not need to be rebuilt to show new analysis artifacts.

## What The Pipeline Does

The pipeline has three stages:

1. Ingestion
   Raw files are normalized into one canonical dataset and run metadata is written to `outputs/clean/`.
2. Analysis
   Modular scripts consume the latest canonical dataset and emit self-describing stats artifacts in `outputs/stats/`.
3. Dashboard
   A local dashboard server scans `outputs/clean/` and `outputs/stats/`, lets you select analysis artifacts, renders visualization contracts, and summarizes the pipeline runs.

All stage outputs are versioned by timestamp. Nothing is overwritten. Each stage also maintains a `latest.json` pointer for downstream consumers.

The runtime flow is:

```text
data/raw/*
  -> outputs/clean/run_manifest_<timestamp>.json
  -> outputs/clean/clean_dataset_<timestamp>.json
  -> outputs/stats/<analysis_id>_<timestamp>.json
  -> dashboard API scans outputs and renders the browser UI
```

## Current Repository Layout

```text
GLADR/
├── context.md
├── plan.md
├── data/
│   └── raw/
│       ├── histology_csv/
│       ├── histology_txt/
│       ├── images/
│       ├── main_sheet/
│       ├── xlsx/
│       └── xlsx_backup/
├── notebooks/
├── outputs/
│   ├── clean/
│   ├── stats/
│   └── dashboard/
├── scripts/
├── src/
│   └── gladr/
│       ├── analysis/
│       ├── contracts/
│       ├── core/
│       ├── dashboard/
│       └── ingest/
└── tests/
```

## Core Concepts

### Canonical Dataset

The ingestion stage converts source-specific columns and values into one shared schema defined in [src/gladr/contracts/canonical_schema.json](/Users/hirsh/Documents/GLADR/src/gladr/contracts/canonical_schema.json).

The clean output is intentionally JSON so it stays human readable:

- `outputs/clean/clean_dataset_<timestamp>.json`
- `outputs/clean/run_manifest_<timestamp>.json`
- `outputs/clean/ingestion_report_<timestamp>.json`
- `outputs/clean/latest.json`

The clean dataset file has this shape:

```json
{
  "run_id": "20260419_192001",
  "run_datetime": "2026-04-19T19:20:01-04:00",
  "canonical_schema_version": "1.0.0",
  "records": [
    {
      "patient_id": "K1234567",
      "source": "gbm_registry",
      "contributor": "Hirsh"
    }
  ]
}
```

### Analysis Outputs

Each analysis script writes a standalone JSON artifact in `outputs/stats/`. These already use JSON and include both the data payload and the visualization contract needed by the dashboard.

### Dashboard

The dashboard is designed to be served dynamically. The local dashboard server scans `outputs/clean/` and `outputs/stats/` on each request, so newly generated analysis artifacts appear after a browser refresh without rebuilding the dashboard shell.

Run the dynamic dashboard:

```bash
python main.py dashboard --serve
```

Then open:

```text
http://127.0.0.1:8765
```

The dashboard includes:

- an analysis browser that discovers every stats artifact, not just `outputs/stats/latest.json`
- category and run selectors for choosing what to inspect
- renderers for current scalar cards, tables, bars, and histograms
- a pipeline page that shows ingestion runs, stats runs, and visualization contracts from left to right

The server exposes one runtime API endpoint:

- `GET /api/dashboard-data`

That endpoint returns the discovered ingestion runs, stats artifacts, latest pointers, and pipeline summary. The browser UI uses that payload to render the Analysis and Pipeline pages.

You can still refresh the static HTML shell copied to `outputs/dashboard/index.html` with:

```bash
python main.py dashboard
```

This is mainly for updating the packaged HTML file. For normal use, prefer `python main.py dashboard --serve` because browser security rules can block local `file://` pages from fetching runtime JSON files directly.

## How The Code Is Organized

### Shared Runtime

- [src/gladr/core/paths.py](/Users/hirsh/Documents/GLADR/src/gladr/core/paths.py)
  Central project path discovery.
- [src/gladr/core/run_context.py](/Users/hirsh/Documents/GLADR/src/gladr/core/run_context.py)
  Run IDs and timestamps.
- [src/gladr/core/latest_pointer.py](/Users/hirsh/Documents/GLADR/src/gladr/core/latest_pointer.py)
  Reads and writes `latest.json`.
- [src/gladr/core/discovery.py](/Users/hirsh/Documents/GLADR/src/gladr/core/discovery.py)
  Auto-discovers adapters and analysis scripts.

### Ingestion

- [src/gladr/ingest/runner.py](/Users/hirsh/Documents/GLADR/src/gladr/ingest/runner.py)
  Runs one or more adapters and writes clean-stage artifacts.
- [src/gladr/ingest/adapters/base_adapter.py](/Users/hirsh/Documents/GLADR/src/gladr/ingest/adapters/base_adapter.py)
  Adapter interface.
- [src/gladr/ingest/adapters/gbm_registry.py](/Users/hirsh/Documents/GLADR/src/gladr/ingest/adapters/gbm_registry.py)
  Current GBM registry adapter.

### Analysis

- [src/gladr/analysis/runner.py](/Users/hirsh/Documents/GLADR/src/gladr/analysis/runner.py)
  Loads the latest clean dataset and runs selected analysis scripts.
- [src/gladr/analysis/base_script.py](/Users/hirsh/Documents/GLADR/src/gladr/analysis/base_script.py)
  Base class for discoverable analysis scripts.
- [src/gladr/analysis/scripts](/Users/hirsh/Documents/GLADR/src/gladr/analysis/scripts)
  Current baseline scripts.

### Dashboard

- [src/gladr/dashboard/build.py](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/build.py)
  Copies the current dashboard shell into the outputs directory.
- [src/gladr/dashboard/server.py](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/server.py)
  Serves the dashboard HTML and dynamic dashboard API.
- [src/gladr/dashboard/manifest_loader.py](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/manifest_loader.py)
  Scans runtime artifacts and builds the dashboard payload.
- [src/gladr/dashboard/static_app/index.html](/Users/hirsh/Documents/GLADR/src/gladr/dashboard/static_app/index.html)
  Browser UI for selecting, rendering, and summarizing analysis outputs.

## Full Process

### 1. Add Or Update Raw Files

Put new raw files in the appropriate folder under `data/raw/`.

For the current GBM registry flow, the main sheet files live in:

- `data/raw/main_sheet/`

### 2. Run Ingestion

Run all available adapters:

```bash
python main.py ingest
```

Run one adapter only:

```bash
python main.py ingest --adapter gbm_registry
```

Run one adapter against a specific file:

```bash
python main.py ingest --adapter gbm_registry --file data/raw/main_sheet/main_sheet_19.04.26.csv
```

What ingestion does:

- discovers adapters
- loads raw source files
- filters stub rows
- normalizes nulls, booleans, dates, and selected categoricals
- derives fields such as `age_at_presentation`, `nlr`, `resection_type`, `qmc_local`, and `referring_centre`
- writes clean JSON artifacts
- updates `outputs/clean/latest.json`

### 3. Run Analysis

Run all current analysis scripts:

```bash
python main.py analyze
```

Run selected scripts:

```bash
python main.py analyze --scripts cohort_summary age_distribution sex_breakdown
```

What analysis does:

- loads `outputs/clean/latest.json`
- reads the latest clean dataset JSON
- executes selected scripts from `src/gladr/analysis/scripts/`
- writes versioned JSON outputs into `outputs/stats/`
- updates `outputs/stats/latest.json`

### 4. Serve The Dashboard

```bash
python main.py dashboard --serve
```

This serves:

- `http://127.0.0.1:8765`

The dashboard scans the current runtime artifacts when the page loads. Run new analysis jobs, refresh the browser, and the new outputs are selectable without rebuilding.

Useful options:

```bash
python main.py dashboard --serve --host 127.0.0.1 --port 8765
```

Use the dashboard this way:

1. Open the Analysis page to browse all stats artifacts.
2. Use the Analysis, Category, and Stats run selectors to choose what to inspect.
3. Use Refresh after running `python main.py analyze` again.
4. Open the Pipeline page to see ingestion runs on the left, stats runs in the middle, and generated visualization contracts on the right.

If you only need to refresh the packaged static shell, run:

```bash
python main.py dashboard
```

This writes `outputs/dashboard/index.html`.

### 5. Run The Whole Pipeline

```bash
python main.py run-all
```

Or via the installed CLI:

```bash
gladr run-all
```

`run-all` performs ingestion, then analysis, then refreshes `outputs/dashboard/index.html`. To view the dynamic dashboard after `run-all`, start the server with `python main.py dashboard --serve`.

## How To Add A New Source Adapter

1. Create a new module in `src/gladr/ingest/adapters/`.
2. Subclass `BaseAdapter`.
3. Set `adapter_id`.
4. Set `source_glob`.
5. Implement `load_raw`.
6. Implement `transform` so it returns canonical columns plus `data_quality_flags`.

The ingestion runner auto-discovers adapters, so no central registry file is required.

## How To Add A New Analysis Script

1. Create a new module in `src/gladr/analysis/scripts/`.
2. Subclass `BaseAnalysisScript`.
3. Set `script_id`, title, description, category, and priority.
4. Implement `build`.
5. Return a JSON-serializable artifact with:
   top-level metadata, a visualization contract, and the data payload.

The analysis runner auto-discovers scripts, so no manual registration is required.

## Running Tests

```bash
python -m unittest discover -s tests
```

Current tests cover:

- latest pointer read/write behavior
- discovery of adapters and analysis scripts
- dashboard runtime artifact discovery and pipeline summary generation

## Troubleshooting

### Dashboard Shows No Analysis

Run analysis first:

```bash
python main.py analyze
```

Then refresh the browser. Confirm `outputs/stats/` contains files named like `<analysis_id>_<timestamp>.json`.

### Dashboard API Is Not Available

Start the server instead of opening the HTML file directly:

```bash
python main.py dashboard --serve
```

Then open `http://127.0.0.1:8765`. The dynamic dashboard expects the local server because it reads runtime artifacts through `/api/dashboard-data`.

### New Outputs Do Not Appear

Refresh the browser. The server scans the output folders at request time, but the already-loaded page will not automatically update until you click Refresh or reload the page.

## Current Starting Point

The current scaffold is intentionally small:

- one real ingestion adapter
- three baseline analysis scripts
- a dynamic dashboard that renders the current visualization contracts

That is enough to keep the project coherent while the clinical normalization rules, survival analyses, and richer renderers are added incrementally.
