# Ingestion Module

This module converts raw registry source files into the canonical clean dataset used by downstream GLADR stages.

## LLM edit scope

An LLM working on ingestion should normally read only this folder plus the raw source sample it was asked about.

Safe edit points:
- `adapters/`: source-specific loading and transformation logic.
- `normalizers.py`: reusable parsing and normalization helpers.
- `validators.py`: source and row validation helpers.
- `quality_flags.py`: row-level quality flag helpers.
- `contracts/`: local context copies of the output contracts.
- `examples/`: small input/output examples for task orientation.

Avoid by default:
- Do not edit `outputs/` manually. Run ingestion to create new artifacts.
- Do not change the canonical schema unless the task explicitly asks for a schema change.
- Do not change downstream analysis or dashboard files for a pure ingestion change.

## Inputs

Raw source files are matched by adapters. The current GBM registry adapter reads CSV files from:

```text
data/raw/main_sheet/*.csv
```

## Outputs

Running ingestion writes versioned artifacts into `outputs/clean/`:

```text
clean_dataset_<run_id>.json
run_manifest_<run_id>.json
ingestion_report_<run_id>.json
latest.json
```

The clean dataset must follow `contracts/canonical_schema.json`. The run artifacts are described in `contracts/ingestion_artifact_schema.json`.

## Run command

```bash
python main.py ingest
python main.py ingest --adapter gbm_registry
python main.py ingest --adapter gbm_registry --file data/raw/main_sheet/example.csv
```

## Implementation pattern

Adapters subclass `BaseAdapter` and return `AdapterRunResult`:

- `dataframe`: canonical records with all canonical fields present.
- `ingestion_report`: row-level quality flag records.
- `source_summary`: source-level row counts and metadata.

The runner concatenates all adapter dataframes, writes artifacts, and updates `outputs/clean/latest.json`.

