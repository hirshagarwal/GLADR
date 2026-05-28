# Ingestion Module

This module converts raw project source files into the canonical clean dataset used by downstream GLADR stages.

## LLM edit scope

An LLM working on ingestion should normally read only this folder plus the raw source sample it was asked about.

Safe edit points:
- `adapters/`: source-specific loading and transformation logic.
- `specs/`: default executable ingestion specs built from predefined operations.
- `spec_engine.py`: shared execution engine for spec-defined transforms.
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
<project>/data/raw/registry/main_sheet/*.csv
```

The histology ingestion stage reads text reports from:

```text
<project>/data/raw/histology/text_reports/*.txt
```

It writes per-report marker CSVs to `<project>/data/interim/histology/extracted_marker_csv/` and compiles those CSVs into one combined JSON histology dataset with a `k_number` identifier column derived from each filename. Passing an `--output` path ending in `.csv` writes the combined dataset as CSV instead.

## Outputs

Canonical ingestion writes versioned artifacts into `<project>/outputs/ingestion/canonical/`:

```text
datasets/clean_dataset_<run_id>.json
manifests/manifest_<run_id>.json
reports/quality_report_<run_id>.json
latest.json
```

Histology ingestion writes versioned artifacts into `<project>/outputs/ingestion/histology/`:

```text
datasets/histology_dataset_<run_id>.json
manifests/manifest_<run_id>.json
reports/extraction_report_<run_id>.json
latest.json
```

The clean dataset must follow `contracts/canonical_schema.json`. The run artifacts are described in `contracts/ingestion_artifact_schema.json`.

Run manifests include a `summary` object and ordered `steps` array. The dashboard uses these fields as the source of truth for the "What happened" flow; it only falls back to inferred steps for older manifests.

## Run command

```bash
python main.py ingest --project-root /path/to/project
python main.py ingest --project-root /path/to/project --adapter gbm_registry
python main.py ingest --project-root /path/to/project --adapter gbm_registry --file data/raw/registry/main_sheet/example.csv
python main.py ingest-histology --project-root /path/to/project
python main.py ingest-histology --project-root /path/to/project --no-generate
```

## Implementation pattern

Adapters subclass `BaseAdapter` and return `AdapterRunResult`. Registry adapters can run from an executable spec so the same transform chain can be previewed, edited transiently in the dashboard, run from the UI, or run from the CLI default:

- `dataframe`: canonical records with all canonical fields present.
- `ingestion_report`: row-level quality flag records.
- `source_summary`: source-level row counts and metadata.

The runner concatenates all adapter dataframes, writes artifacts, and updates `<project>/outputs/ingestion/canonical/latest.json`.

The dashboard may trigger ingestion through the local server, but transform behavior must stay in ingestion-owned Python modules and packaged specs. UI-submitted specs are transient unless an explicit save flow is added later.

Specs should prefer generic operations such as mapping, normalization, derivation, joins, and canonical field selection. Source-specific transforms should be exposed as allowlisted `static_code` functions so they can appear in the same chain without pretending to be reusable generic operations. The join operation can combine another workspace CSV/JSON data file, including long-form histology marker datasets that are pivoted before joining.
