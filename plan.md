# GLADR Project Plan

## Scope

This repository is being reorganized from a prototype into a package-first clinical registry pipeline with three explicit stages:

1. Ingestion into a canonical dataset
2. Analysis scripts that emit self-describing JSON artifacts
3. A generic dashboard that renders from visualization contracts

## Items Worth Adding To The Original Plan

The earlier architecture was directionally right, but a few important implementation concerns needed to be made explicit:

- Contract validation
  Every stage should validate its inputs and outputs against a machine-readable contract, not just rely on conventions.

- Blocking vs non-blocking data issues
  Some ingestion problems should stop a run, while others should become row-level `data_quality_flags`.

- Provenance and reproducibility
  Run manifests should eventually include source file hashes, adapter versions, and software version metadata.

- Shared runtime services
  Timestamp generation, path resolution, artifact writing, latest-pointer updates, and plugin discovery should live in a shared core layer rather than inside stage-specific scripts.

- Test boundaries
  The minimum useful tests are contract loading, latest-pointer updates, adapter discovery, and at least one adapter smoke test.

- Backward compatibility while reorganizing
  Thin wrapper entry points are useful during the transition so the repository can move to `src/` layout without breaking every old command immediately.

- Dashboard strategy
  The dashboard should start as a contract-driven shell first. Rich interactions can come later, but the renderer registry and manifest loading need to exist from day one.

- Operational hygiene
  Logging, consistent CLI commands, and deterministic output paths matter early because the pipeline is versioned by design.

## Starting Structure

```text
GLADR/
├── data/
│   └── raw/
├── notebooks/
├── outputs/
│   ├── clean/
│   ├── stats/
│   └── dashboard/
├── scripts/
├── src/
│   └── gladr/
│       ├── core/
│       ├── contracts/
│       ├── ingest/
│       ├── analysis/
│       └── dashboard/
└── tests/
```

## Core Runtime Components

- `gladr.core.paths`
  Central path registry for `data/`, `outputs/`, and package assets.

- `gladr.core.run_context`
  Generates `run_id`, run timestamps, and stage metadata.

- `gladr.core.latest_pointer`
  Reads and writes `latest.json` files consistently across stages.

- `gladr.core.discovery`
  Auto-discovers adapters and analysis scripts from package modules.

## Ingestion Starting Point

- Implement one real adapter: `gbm_registry`
- Normalize nulls, booleans, dates, and selected categorical fields
- Filter stub rows
- Derive initial computed fields:
  `age_at_presentation`, `nlr`, `resection_type`, `qmc_local`, `referring_centre`
- Emit three artifacts per run:
  clean dataset JSON, run manifest, ingestion report

## Analysis Starting Point

Start with a small set of scripts that prove the end-to-end pattern:

- `cohort_summary`
- `age_distribution`
- `sex_breakdown`

Each script should emit:

- top-level metadata
- a visualization contract
- a data payload matching that contract

## Dashboard Starting Point

- Keep the dashboard generic
- Load `outputs/stats/latest.json`
- Render a minimal panel per analysis artifact
- Support a small initial renderer set:
  `scalar_cards`, `table`, `bar`, `histogram`

## Execution Plan

1. Establish `src/` layout and shared runtime utilities.
2. Move exploratory work into `notebooks/` and raw files into `data/raw/`.
3. Implement the GBM ingestion adapter and clean output writer.
4. Implement the analysis runner and a few baseline scripts.
5. Add a minimal contract-driven dashboard shell.
6. Add smoke tests for the shared runtime and discovery mechanisms.

## Immediate Next Work After This Reorganization

- Expand the GBM adapter’s clinical normalization rules
- Add survival analysis helpers and Kaplan-Meier outputs
- Introduce JSON schema validation for analysis outputs
- Replace the dashboard shell with a richer renderer registry
- Add manifest hashing and source fingerprints
