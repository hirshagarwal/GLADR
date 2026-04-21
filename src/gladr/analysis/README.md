# Analysis Module

This module reads the latest clean dataset and writes versioned stats artifacts for dashboard discovery.

## LLM edit scope

An LLM adding or changing a statistic should normally read only this folder:

- `README.md`
- `module.yaml`
- `base_script.py`
- one similar file in `scripts/`
- `contracts/`
- `examples/`

Safe edit points:
- `scripts/`: add or update analysis scripts.
- `base_script.py`: only for shared analysis contract changes.
- `contracts/analysis_artifact_schema.json`: only when the artifact contract intentionally changes.
- `examples/`: update examples when adding a new output pattern.

Avoid by default:
- Do not edit ingestion internals for a stats-only task.
- Do not edit dashboard code unless a new visualization type or artifact shape is required.
- Do not edit generated files in `outputs/stats/` manually.

## Inputs

The runner reads the latest clean dataset from `outputs/clean/latest.json`. Analysis code should treat the clean dataset as a stable input contract described by `contracts/clean_dataset_schema.json`.

## Outputs

Each script emits one JSON artifact into `outputs/stats/`:

```text
<script_id>_<run_id>.json
```

The runner updates:

```text
outputs/stats/latest.json
```

Each artifact should follow `contracts/analysis_artifact_schema.json` and may include a visualization contract described by `contracts/visualization_schema.json`.

## Run command

```bash
python main.py analyze
python main.py analyze --scripts cohort_summary
```

## Script pattern

Create a `BaseAnalysisScript` subclass in `scripts/`:

- set `script_id`, `title`, `description`, `category`, and `priority`
- implement `build(dataframe, run_context, manifest_run_id)`
- return a JSON-serializable dict with metadata, data, and optional visualization

Prefer adding one focused script per analysis question so experiments can be versioned and compared independently.

