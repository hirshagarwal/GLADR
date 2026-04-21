# GBM Registry Analysis Pipeline — Context

## Project Overview

This project is a **generic, extensible clinical research analysis pipeline** built initially around a Glioblastoma Multiforme (GBM) patient registry from a regional neurosurgical unit (QMC / Nottingham-based, with referrals from Derby, Leicester, Lincoln, King's Mill). The pipeline is designed to accommodate multiple heterogeneous data sources over time, with each source plugged in via a self-contained adapter.

The pipeline has three stages:
1. **Ingestion** — source adapters normalise raw data into a shared canonical schema
2. **Stats / Analysis** — modular scripts consume the canonical dataset and emit versioned JSON outputs
3. **Visualisation** — a generic dashboard renders all JSON outputs based on embedded rendering contracts

Every run is **fully versioned by timestamp**. No files are overwritten. The system is designed so that new data sources and new analyses can be added by generating a single new file — nothing else in the pipeline changes.

---

## Dataset: `main_sheet_<DD_MM_YY>.csv`

### Structure
- **258 rows**, **27 columns**
- Each row = one patient (identified by K-number)
- Multiple contributors (Hirsh, Caed, April, Rhiannon) — each responsible for a cohort of patients
- Data spans approximately **2022–2026** based on presentation dates

### Column Reference

| Column | Type | Notes |
|---|---|---|
| `Histo Report?` | Boolean/String | Whether histology report is available; often `?` or blank |
| `Contributor` | Categorical | Clinician responsible for data entry |
| `QMC Local` | Categorical | Encodes both local/non-local boolean and referring centre — split at ingestion |
| `K-number` | String (ID) | Primary patient identifier |
| `DOB` | Date (DD/MM/YYYY) | Variable formatting |
| `Sex` | Categorical | M/F |
| `Presentation Date` | Date | Variable formatting |
| `Age at presentation` | Float | Sometimes blank; derivable from DOB + Presentation Date |
| `Neutrophils (presentation)` | Float | Missing in earlier cohorts |
| `Lymphocytes (presentation)` | Float | Missing in earlier cohorts |
| `First contrast MRI` | Date | Pre-op MRI date |
| `Side` | Categorical | L / R / R+L / Midline / etc. |
| `Lobe` | String | Free-text; highly variable — mapped to controlled vocabulary at ingestion |
| `Peri-ventricular` | Boolean | Yes/No/yes/no |
| `Multifocal` | Boolean | Yes/No |
| `Resection` | Date | Date of surgery; NA if biopsy only or no resection |
| `Post-op MRI Date` | Date | |
| `5-ALA` | Boolean | Whether 5-ALA fluorescence used |
| `Residual contrast enhancement` | Boolean/String | "Yes", "No", "Yes - anterior margin", etc. |
| `Radiotherapy` | Boolean | Yes/No/ND/Not documented |
| `TMZ` | Boolean/String | Temozolomide; Yes/No/ND/Discontinued |
| `First recurrence evidence` | Date/String | Date or "Residual"/"Progression"/NA — needs special handling |
| `Recurrence side` | Categorical | L/R/NA/Progression |
| `Recurrence lobe` | String | Free-text, same issues as Lobe |
| `Local` | Boolean | Whether recurrence is local |
| `DOD` | Date/String | Date of death; "NA" if alive/unknown; future dates valid (ongoing study) |
| `Notes` | Free text | Clinical notes; rich but unstructured |

### Known Data Quality Issues

1. **Stub rows** — Many rows contain only a K-number with all other fields blank. Must be filtered at ingestion.
2. **Inconsistent null representations** — `NA`, `n/a`, `N/A`, `ND`, `Not documented`, `not documented`, blank, `?` all mean "missing" in different contexts.
3. **Date format inconsistency** — `DD/MM/YYYY`, `D/M/YYYY`, `DD/MM/YY`, `D/M/YY` all present.
4. **Invalid dates** — e.g. `25/21/2024` (month = 21). Must be caught by validity check, not just format parsing.
5. **Case inconsistency** — `Parietal` vs `parietal`, `Yes` vs `yes`, etc.
6. **Free-text lobe encoding** — Needs mapping to a controlled vocabulary (`ingest/lobe_mapping.json`).
7. **`QMC Local` dual encoding** — Contains both a boolean and a referring centre string; split into `qmc_local` (bool) + `referring_centre` (str).
8. **Age at presentation** — Not always populated; derivable from DOB + Presentation Date when missing.
9. **NLR** — Derived field (Neutrophils / Lymphocytes); not a raw column. Missing for earlier cohort (~pre-mid-2023).
10. **Recurrence field dual encoding** — `First recurrence evidence` sometimes contains a date, sometimes "Residual" or "Progression".
11. **DOD future dates** — Valid data (ongoing study), not errors.
12. **`Histo Report?`** — `?` means unknown, not False.

---

## Pipeline Architecture

### Core Principles

- **One canonical schema** — all sources normalise to the same column set and types before any analysis
- **Adapter-per-source** — adding a new data source means writing one new adapter file; nothing else changes
- **Immutable versioned outputs** — every run appends timestamped files; nothing is overwritten
- **Latest pointer** — a `latest.json` pointer file in each output directory allows downstream scripts to always find the most recent version without scanning
- **Self-describing outputs** — every stats output carries its own rendering contract; the dashboard has zero domain knowledge

---

### Stage 1: Ingestion (`ingest/`)

#### Source Adapter Pattern

Each data source has a dedicated adapter file in `ingest/adapters/`. An adapter is responsible for everything specific to that source: reading the raw file, mapping columns to the canonical schema, handling that source's null conventions, date formats, and quirks.

The ingestion runner (`ingest/ingest.py`) **discovers adapters automatically** by scanning `ingest/adapters/`. To add a new data source, generate a new adapter file — nothing else changes.

**Generating a new adapter with an LLM:**
Provide the LLM with:
- The raw data file (or a sample)
- `ingest/canonical_schema.json` (the target schema)
- `ingest/adapters/base_adapter.py` (abstract base class)
- An existing adapter (e.g. `gbm_registry.py`) as a template

The LLM produces a new adapter file. Drop it into `ingest/adapters/` and it is picked up on the next run.

#### Canonical Schema (`ingest/canonical_schema.json`)

Defines the shared output format all adapters must produce. Each field specifies name, type, nullable, and description. Current fields (from GBM registry):

```
patient_id, source, contributor, dob, sex, presentation_date, age_at_presentation,
neutrophils, lymphocytes, nlr, first_mri_date, tumour_side, tumour_lobe,
periventricular, multifocal, resection_date, resection_type, postop_mri_date,
five_ala, residual_enhancement, radiotherapy, tmz, recurrence_date,
recurrence_type, recurrence_side, recurrence_lobe, recurrence_local,
dod, qmc_local, referring_centre, histo_report, notes, data_quality_flags
```

When a new source introduces genuinely new fields, the canonical schema is updated and all existing adapters are patched to emit `null` for that field.

#### Outputs (all timestamped)

```
outputs/clean/
├── clean_dataset_<YYYYMMDD_HHMMSS>.parquet   # canonical merged dataset
├── run_manifest_<YYYYMMDD_HHMMSS>.json       # run metadata
├── ingestion_report_<YYYYMMDD_HHMMSS>.json   # data quality report per row
└── latest.json                               # pointer to most recent run
```

`latest.json` schema:
```json
{
  "clean_dataset": "clean_dataset_20260419_100000.parquet",
  "run_manifest": "run_manifest_20260419_100000.json",
  "ingestion_report": "ingestion_report_20260419_100000.json"
}
```

#### Run Manifest Schema

```json
{
  "run_id": "20260419_100000",
  "pipeline_version": "1.0.0",
  "run_datetime": "2026-04-19T10:00:00",
  "sources": [
    {
      "adapter": "gbm_registry",
      "file": "main_sheet_19_04_26.csv",
      "rows_raw": 258,
      "rows_stub": 74,
      "rows_ingested": 184
    }
  ],
  "total_rows": 184,
  "canonical_schema_version": "1.0.0",
  "notes": ""
}
```

#### Adapter Responsibilities

Each adapter must:
- Read its raw source file
- Filter invalid/stub rows
- Map all columns to canonical schema field names
- Normalise all null representations → `None`
- Parse and validate all dates → ISO 8601 or `None`
- Normalise booleans → `True` / `False` / `None`
- Normalise categoricals → Title Case controlled vocabulary
- Derive computed fields (`age_at_presentation`, `nlr`, `resection_type`, etc.)
- Emit a `data_quality_flags` list per row (non-blocking warnings)
- Return a `pd.DataFrame` conforming to the canonical schema

---

### Stage 2: Analysis (`stats/`)

**Input**: `outputs/clean/latest.json` → resolves to latest `clean_dataset_*.parquet`  
**Output per script**: `outputs/stats/<script_id>_<YYYYMMDD_HHMMSS>.json`

Each script is independently runnable. The stats runner (`stats/run_stats.py`) discovers scripts automatically by scanning `stats/scripts/`. To add a new analysis, generate a new script file — nothing else changes.

A `latest.json` pointer in `outputs/stats/` lists the most recent output file for each `script_id`.

#### Standard Output Contract

Every stats script emits a JSON file with this top-level schema:

```json
{
  "script_id": "nlr_survival",
  "run_id": "20260419_100000",
  "manifest_run_id": "20260419_100000",
  "run_datetime": "2026-04-19T10:00:00",
  "title": "NLR vs Overall Survival",
  "description": "Kaplan-Meier overall survival stratified by NLR dichotomised at median.",
  "category": "Inflammatory Markers",
  "priority": 2,

  "metadata": {
    "n": 142,
    "exclusions": "Patients with missing NLR excluded (n=42)",
    "notes": "NLR dichotomised at median value of 8.3"
  },

  "visualization": { ... },

  "data": { ... }
}
```

#### Visualization Contract

The `visualization` block gives the dashboard **complete rendering instructions**. The dashboard does not interpret `script_id`, `category`, or `data` structure — it only reads `visualization` to decide how to render.

```json
"visualization": {
  "type": "kaplan_meier",
  "library": "plotly",
  "config": {
    "x_field": "time_days",
    "x_label": "Time from Presentation (days)",
    "y_field": "survival_probability",
    "y_label": "Overall Survival Probability",
    "group_field": "group",
    "group_labels": { "high": "NLR ≥ 8.3", "low": "NLR < 8.3" },
    "confidence_intervals": true,
    "show_censoring_marks": true,
    "annotations": [
      { "label": "p-value (log-rank)", "value_field": "p_value" },
      { "label": "Median OS (high NLR)", "value_field": "median_os_high" },
      { "label": "Median OS (low NLR)", "value_field": "median_os_low" }
    ],
    "color_scheme": "group"
  }
}
```

**Supported visualization types and their config fields:**

| Type | Required config fields |
|---|---|
| `kaplan_meier` | `x_field`, `y_field`, `group_field`, `confidence_intervals`, `show_censoring_marks`, `annotations` |
| `histogram` | `x_field`, `x_label`, `bin_count`, `overlay_normal` |
| `bar` | `x_field`, `y_field`, `x_label`, `y_label`, `orientation`, `sort_by` |
| `scatter` | `x_field`, `y_field`, `x_label`, `y_label`, `group_field`, `regression_line` |
| `table` | `columns` (list of `{ field, label, format }`) |
| `scalar_cards` | `cards` (list of `{ label, value_field, unit, format }`) |
| `multi` | `panels` (list of nested visualization blocks, each with `type` + `config`) |

The `multi` type allows a single stats script to output composite results (e.g. a summary table + a KM curve together).

#### Stats Output: `data` Block

The `data` block structure corresponds to the `visualization.type`. The dashboard maps config field names onto the data to render. Examples:

**`kaplan_meier`**:
```json
"data": {
  "series": [
    {
      "group": "high",
      "points": [
        { "time_days": 0, "survival_probability": 1.0, "censored": false },
        { "time_days": 45, "survival_probability": 0.94, "censored": false }
      ]
    }
  ],
  "p_value": 0.023,
  "median_os_high": 287,
  "median_os_low": 412
}
```

**`scalar_cards`**:
```json
"data": {
  "total_patients": 184,
  "median_age": 62.4,
  "pct_male": 58.7,
  "median_os_days": 342
}
```

#### Planned Analysis Scripts

| Script ID | Title | Category | Output Type |
|---|---|---|---|
| `cohort_summary` | Cohort Demographics | Demographics | `multi` (scalar_cards + table) |
| `age_distribution` | Age at Presentation | Demographics | `histogram` |
| `sex_breakdown` | Sex Distribution | Demographics | `bar` |
| `lobe_distribution` | Tumour Location | Tumour Characteristics | `bar` |
| `side_distribution` | Tumour Laterality | Tumour Characteristics | `bar` |
| `periventricular_distribution` | Periventricular Involvement | Tumour Characteristics | `bar` |
| `multifocal_distribution` | Multifocal Disease | Tumour Characteristics | `bar` |
| `resection_rates` | Resection vs Biopsy | Treatment | `bar` |
| `five_ala_usage` | 5-ALA Usage | Treatment | `bar` |
| `residual_enhancement` | Residual Contrast Enhancement | Treatment | `bar` |
| `rt_tmz_rates` | Radiotherapy & TMZ Uptake | Treatment | `bar` |
| `os_overall` | Overall Survival | Survival | `kaplan_meier` |
| `os_by_resection` | OS by Resection Type | Survival | `kaplan_meier` |
| `os_by_5ala` | OS by 5-ALA Use | Survival | `kaplan_meier` |
| `os_by_lobe` | OS by Tumour Lobe | Survival | `kaplan_meier` |
| `os_by_age_group` | OS by Age Group (<60 vs ≥60) | Survival | `kaplan_meier` |
| `os_by_sex` | OS by Sex | Survival | `kaplan_meier` |
| `os_by_periventricular` | OS by Periventricular Involvement | Survival | `kaplan_meier` |
| `os_by_multifocal` | OS by Multifocal Disease | Survival | `kaplan_meier` |
| `nlr_distribution` | NLR Distribution | Inflammatory Markers | `histogram` |
| `nlr_survival` | NLR vs Overall Survival | Inflammatory Markers | `multi` (kaplan_meier + scatter) |
| `nlr_by_resection` | NLR by Resection Type | Inflammatory Markers | `scatter` |
| `time_to_recurrence` | Time to Recurrence | Recurrence | `histogram` |
| `recurrence_location` | Local vs Distant Recurrence | Recurrence | `bar` |
| `recurrence_survival` | Post-Recurrence Survival | Recurrence | `kaplan_meier` |
| `contributor_audit` | Data Completeness by Contributor | Audit | `table` |
| `temporal_trends` | Presentations Over Time | Audit | `bar` |

---

### Stage 3: Visualisation (`dashboard/`)

**Input**: `outputs/stats/latest.json` → loads all current script outputs  
**Output**: Self-contained `outputs/dashboard/index.html`

#### Architecture

- Single-page app (vanilla JS or React)
- On load: reads `outputs/stats/latest.json`, fetches each referenced JSON file
- Renders each output as a panel using only the `visualization` block — **no domain knowledge, pure rendering**
- Auto-organises panels by `category` (sidebar navigation) and `priority` (sort order within category)
- Each panel displays: title, description, chart/table, n, exclusions, run datetime
- Manifest panel: dataset provenance, pipeline version, row counts, source list

#### Rendering Logic (pseudocode)

```
for each output in latest.json:
    load output JSON
    create panel with title, description, metadata footer
    switch output.visualization.type:
        case "kaplan_meier" → render KM curve using config field mappings
        case "histogram"    → render histogram
        case "bar"          → render bar chart
        case "scatter"      → render scatter plot
        case "table"        → render sortable table
        case "scalar_cards" → render stat cards
        case "multi"        → render each panel in output.visualization.panels
```

The dashboard **never** reads `script_id` or `category` for rendering decisions. Only `visualization` drives rendering.

---

## Versioning & History

Every output file is timestamped at creation. Nothing is overwritten. The `latest.json` pointer in each output directory always references the most recent successful run.

```
outputs/
├── clean/
│   ├── clean_dataset_20260419_100000.parquet
│   ├── clean_dataset_20260501_143022.parquet   ← new run after data update
│   ├── run_manifest_20260419_100000.json
│   ├── run_manifest_20260501_143022.json
│   └── latest.json                             ← always points to most recent
├── stats/
│   ├── os_overall_20260419_100000.json
│   ├── os_overall_20260501_143022.json         ← re-run after new data
│   ├── nlr_survival_20260419_100000.json
│   └── latest.json                             ← { "os_overall": "os_overall_20260501...", ... }
```

`outputs/stats/latest.json` schema:
```json
{
  "os_overall": "os_overall_20260501_143022.json",
  "nlr_survival": "nlr_survival_20260419_100000.json"
}
```

Individual scripts can be re-run without re-running the full pipeline. The latest pointer updates per `script_id` only.

---

## Directory Structure

```
project/
├── data/                                         # Raw input files (read-only)
│   └── main_sheet_19_04_26.csv
│
├── ingest/
│   ├── ingest.py                                 # Runner: discovers + executes adapters
│   ├── canonical_schema.json                     # Shared canonical field definitions
│   ├── lobe_mapping.json                         # Controlled vocabulary for lobe normalisation
│   └── adapters/
│       ├── base_adapter.py                       # Abstract base class all adapters extend
│       └── gbm_registry.py                       # Adapter for main_sheet_*.csv
│
├── stats/
│   ├── run_stats.py                              # Runner: discovers + executes scripts
│   ├── base_script.py                            # Base class: loads data, writes output, updates latest.json
│   └── scripts/
│       ├── cohort_summary.py
│       ├── os_overall.py
│       ├── nlr_survival.py
│       └── ...
│
├── dashboard/
│   └── index.html                                # Generic renderer; reads outputs/stats/latest.json
│
├── outputs/
│   ├── clean/
│   │   ├── clean_dataset_<timestamp>.parquet
│   │   ├── run_manifest_<timestamp>.json
│   │   ├── ingestion_report_<timestamp>.json
│   │   └── latest.json
│   ├── stats/
│   │   ├── <script_id>_<timestamp>.json
│   │   └── latest.json
│   └── dashboard/
│       └── index.html
│
├── context.md                                    # This file
└── README.md
```

---

## Running the Pipeline

```bash
# Stage 1: Ingest all sources
python ingest/ingest.py

# Stage 1: Ingest a specific source
python ingest/ingest.py --adapter gbm_registry --file data/main_sheet_19_04_26.csv

# Stage 2: Run all stats scripts against latest clean dataset
python stats/run_stats.py --all

# Stage 2: Run specific scripts
python stats/run_stats.py --scripts os_overall nlr_survival cohort_summary

# Stage 2: Run against a specific (non-latest) clean dataset
python stats/run_stats.py --all --manifest outputs/clean/run_manifest_20260419_100000.json

# Stage 3: View dashboard
python -m http.server 8000 --directory outputs/dashboard/
```

---

## Adding a New Data Source

1. Obtain raw data file; place in `data/`
2. Provide LLM with: the raw file (or sample) + `canonical_schema.json` + `base_adapter.py` + an existing adapter as template
3. LLM generates `ingest/adapters/<new_source>.py`
4. Drop into `ingest/adapters/` — discovered automatically on next run
5. If the new source introduces new canonical fields, update `canonical_schema.json` and patch existing adapters to emit `None` for those fields

## Adding a New Analysis

1. Provide LLM with: `canonical_schema.json` + `base_script.py` + an existing script as template + description of the desired analysis
2. LLM generates `stats/scripts/<script_id>.py`
3. Drop into `stats/scripts/` — discovered automatically on next run

---

## Clinical Context

- **Disease**: Glioblastoma Multiforme (GBM), WHO Grade 4 — the most aggressive primary brain tumour
- **Standard of care**: Maximal safe resection → concurrent radiotherapy + temozolomide (TMZ) → adjuvant TMZ (Stupp protocol)
- **Key prognostic variables**: Age, extent of resection, MGMT methylation (not in this dataset), performance status, multifocality, periventricular involvement
- **NLR**: Neutrophil-to-Lymphocyte Ratio — systemic inflammatory marker with emerging prognostic significance in GBM
- **5-ALA**: Aminolevulinic acid — intraoperative fluorescence agent used to improve extent of resection
- **Survival**: Median OS ~15 months with Stupp; poor prognosis overall
- **Recurrence**: Almost universal; local vs distant patterns have therapeutic implications

---

## Key Conventions

| Decision | Convention |
|---|---|
| Stub row definition | Row where all fields except K-number (and optionally Contributor) are blank |
| Alive / censored | DOD = "NA" or missing → censored; survival time = days from presentation to DOD or last known date |
| Resection classification | Surgery date present + not biopsy-only in notes → resection; else biopsy or none |
| NLR dichotomisation | Median split (or literature threshold ~4.0) — documented per script in metadata |
| Boolean normalisation | Yes/yes/Y → `True`; No/no/N → `False`; ND/Not documented/n/a/NA/? → `None` |
| Date parsing | All dates → ISO 8601 string; invalid or unparseable → `None` + data quality flag |
| Null representation | All nulls → Python `None` in parquet; `null` in JSON |
| Survival time unit | Days from presentation date to DOD |
| Output timestamps | `YYYYMMDD_HHMMSS` format |

---

*Last updated: 2026-04-19 | Pipeline version: 1.0.0*