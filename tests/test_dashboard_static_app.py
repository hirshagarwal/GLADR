from pathlib import Path


STATIC_APP = Path(__file__).resolve().parents[1] / "src" / "gladr" / "dashboard" / "static_app" / "index.html"


def test_column_mapping_editor_does_not_cap_rendered_rows() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    render_start = html.index("function renderOperationParams")
    start = html.index('if (["rename_columns", "map_columns"].includes(step.operation))', render_start)
    end = html.index('if (step.operation === "normalize_fields")', start)
    mapping_editor = html[start:end]

    assert "Object.entries(params.columns ?? {})" in mapping_editor
    assert ".slice(0, 18)" not in mapping_editor
    assert "const unmappedSources = sourceOptions.filter((field) => !mappedSources.has(field));" in mapping_editor
    assert 'const rows = unmappedSources.length ? [...mappings, ["", ""]] : mappings;' in mapping_editor
