# Dashboard Module

This module serves and builds the GLADR dashboard. The dashboard is a reader over pipeline artifacts; it should not own ingestion or analysis behavior.

## LLM edit scope

An LLM changing dashboard behavior should normally read only this folder plus the artifact contracts in `contracts/`.

Safe edit points:
- `static_app/index.html`: browser UI, rendering, filtering, and interactions.
- `manifest_loader.py`: runtime artifact discovery and dashboard payload shaping.
- `server.py`: local development server and API routing.
- `build.py`: static dashboard shell build.
- `contracts/`: local context copies of dashboard-facing contracts.
- `examples/`: small dashboard payload examples.

Avoid by default:
- Do not change ingestion or analysis code to solve a display-only issue.
- Do not edit generated outputs manually.
- Do not make the dashboard the source of truth for pipeline state.

## Inputs

The dashboard reads runtime artifacts from:

```text
<project>/outputs/ingestion/
<project>/outputs/analysis/
```

The dashboard API payload is described by `contracts/dashboard_payload_schema.json`.

## Outputs

`python main.py dashboard --project-root /path/to/project` copies the dashboard shell to:

```text
<project>/outputs/dashboard/builds/index.html
```

`python main.py dashboard --serve` starts the local dynamic dashboard. It can start without an active project, then create or switch projects through the UI. The server exposes:

```text
/
/api/dashboard-data
/api/projects
```

## Design principle

Pipeline code writes artifacts. The dashboard discovers, summarizes, and renders artifacts.
