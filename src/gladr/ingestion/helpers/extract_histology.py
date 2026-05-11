"""Extract structured histology marker CSVs from text reports."""

from __future__ import annotations

import csv
import os
import re
import time
from io import StringIO
from pathlib import Path
from typing import Any


MARKER_ORDER = [
    "IDH1 or IDH2 mutated",
    "MGMT promoter methylation status",
    "EGFR amplification",
    "ATRX mutation",
    "Subtype",
]

CSV_COLUMNS = ["marker", "value", "notes"]


def _extract_csv(text: str) -> str:
    """Return raw CSV content, stripping Markdown code fences if present."""
    if not text:
        return ""
    fence = re.search(r"```(?:csv)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text.strip()


def build_report(
    report_txt_file: str | Path,
    csv_override: bool = False,
    *,
    model: str = "gpt-5-nano",
    txt_dir: str | Path = "data/raw/histology/text_reports",
    csv_dir: str | Path = "data/interim/histology/extracted_marker_csv",
    client: Any | None = None,
) -> Path:
    """
    Convert one histology text report into a marker CSV.

    ``report_txt_file`` may be either a filename inside ``txt_dir`` or a direct
    path to a ``.txt`` file. The output CSV is written to ``csv_dir`` using the
    text file stem.
    """
    txt_path = _resolve_txt_path(report_txt_file, txt_dir)
    if txt_path.suffix.lower() != ".txt":
        raise ValueError(f"Expected a .txt file, got: {txt_path}")
    if not txt_path.exists():
        raise FileNotFoundError(f"Text report not found: {txt_path.resolve()}")

    csv_path = Path(csv_dir) / f"{txt_path.stem}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    if csv_path.exists() and not csv_override:
        print(f"[build_report] CSV already exists, skipping (set csv_override=True to regenerate): {csv_path}")
        return csv_path

    report_text = txt_path.read_text(encoding="utf-8")
    model_client = client or _create_openai_client()

    system_prompt = (
        "You are given a histopathology / molecular pathology report for a GBM biopsy.\n"
        "Your only task is to output a CSV.\n\n"
        "The CSV must always contain exactly 6 rows:\n"
        "1 header row + 5 rows for the following markers, in this exact order:\n"
        "- IDH1 or IDH2 mutated\n"
        "- MGMT promoter methylation status\n"
        "- EGFR amplification\n"
        "- ATRX mutation\n"
        "- Subtype\n\n"
        "Formatting rules:\n"
        "- Header row must be: marker,value,notes\n"
        "- Marker column: use exactly the names shown above, in this exact order.\n"
        "- Value column:\n"
        "  - IDH1 or IDH2 mutated: yes/no/Not Reported\n"
        "  - MGMT promoter methylation status: methylated/unmethylated/Not Reported\n"
        "  - EGFR amplification: yes/no/Not Reported\n"
        "  - ATRX mutation: yes/no/Not Reported\n"
        "  - Subtype: classical/mesenchymal/proneural/neural/other/Not Reported\n"
        "- Notes column: leave blank unless the wording is unclear. If unclear, copy the exact ambiguous wording.\n\n"
        "Hard rules:\n"
        "1. Output valid RFC4180 CSV only, with no prose, Markdown, or commentary.\n"
        "2. The CSV must contain exactly 6 rows: header + 5 marker rows.\n"
        "3. Never add markers other than the 5 listed above.\n"
        "4. If the report does not mention a marker, set its value to Not Reported.\n"
        "5. Do not reorder or rename markers."
    )

    user_prompt = "Convert the following report to CSV per the instructions.\n" f"{report_text}\n"

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            response = model_client.responses.create(
                model=model,
                instructions=system_prompt,
                input=[{"role": "user", "content": user_prompt}],
                service_tier="flex",
            )
            csv_text = _extract_csv(getattr(response, "output_text", "").strip())
            normalized_csv = _normalize_marker_csv(csv_text)
            csv_path.write_text(normalized_csv, encoding="utf-8", newline="\n")
            print(f"[build_report] Wrote CSV: {csv_path}")
            return csv_path
        except Exception as exc:
            last_err = exc
            wait = 1.5 * (attempt + 1)
            print(f"[build_report] Attempt {attempt + 1}/3 failed: {exc} - retrying in {wait:.1f}s")
            time.sleep(wait)

    raise RuntimeError(f"Failed to build CSV for {txt_path.name}") from last_err


def _resolve_txt_path(report_txt_file: str | Path, txt_dir: str | Path) -> Path:
    candidate = Path(report_txt_file)
    if candidate.is_absolute() or candidate.parent != Path("."):
        return candidate
    return Path(txt_dir) / candidate


def _create_openai_client() -> Any:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Histology extraction requires the openai package. Install project dependencies with OpenAI support."
        ) from exc

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to generate histology CSVs.")
    return OpenAI(api_key=api_key)


def _normalize_marker_csv(csv_text: str) -> str:
    if not csv_text:
        raise RuntimeError("Model returned empty output_text or failed to produce CSV.")

    first_line = csv_text.splitlines()[0].strip().lower()
    if not first_line.startswith("marker,value"):
        csv_text = "marker,value,notes\n" + csv_text.lstrip()

    reader = csv.DictReader(StringIO(csv_text))
    if reader.fieldnames is None:
        raise RuntimeError("Model output did not include a CSV header.")

    fieldnames = [field.strip() for field in reader.fieldnames]
    missing = [column for column in ("marker", "value") if column not in fieldnames]
    if missing:
        raise RuntimeError(f"Model output is missing required CSV columns: {', '.join(missing)}")

    rows = []
    for row in reader:
        rows.append(
            {
                "marker": (row.get("marker") or "").strip(),
                "value": (row.get("value") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
            }
        )

    if [row["marker"] for row in rows] != MARKER_ORDER:
        raise RuntimeError("Model output did not contain the required marker rows in order.")

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
