from pathlib import Path


STATIC_APP = Path(__file__).resolve().parents[1] / "src" / "gladr" / "dashboard" / "static_app" / "index.html"


def test_column_mapping_editor_delegates_to_dedicated_function() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    # The rename_columns branch delegates to renderColumnMappingEditor
    render_start = html.index("function renderOperationParams")
    start = html.index('if (["rename_columns", "map_columns"].includes(step.operation))', render_start)
    end = html.index('if (step.operation === "normalize_fields")', start)
    branch = html[start:end]
    assert "renderColumnMappingEditor" in branch
    # Does NOT inline the old slice-based approach
    assert ".slice(0, 18)" not in branch
    assert "data-param-index" not in branch


def test_column_mapping_editor_function_exists_and_is_keyed() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    # The function must exist
    assert "function renderColumnMappingEditor" in html
    # It must use source-key-based data attributes, not index-based
    start = html.index("function renderColumnMappingEditor")
    end = html.index("\n      function ", start + 1)
    body = html[start:end]
    assert "data-mapping-source-key" in body
    assert "data-mapping-filter" in body
    assert "data-ingestion-action=\"map-all-columns\"" in body
    assert "data-ingestion-action=\"tidy-column-names\"" in body


def test_variable_search_and_type_filter_controls_exist() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    # Analysis panel has search + type filter for variables
    assert 'id="variable-search"' in html
    assert 'id="variable-type-filter"' in html
    assert 'id="variable-count"' in html
    assert "function renderVariableList" in html


def test_results_variable_filter_exists() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    # Results view has the variable filter section
    assert 'id="var-filter-input"' in html
    assert 'id="var-filter-chips"' in html
    assert 'id="var-filter-active"' in html
    assert "function populateVariableFilter" in html
    assert "function artifactVariableNames" in html
    # applyFilters uses the variable filter
    start = html.index("function applyFilters")
    end = html.index("\n      function ", start + 1)
    body = html[start:end]
    assert "variableFilter" in body
    assert "artifactVariableNames" in body


def test_type_badges_and_presence_bars() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    assert "function typeBadge" in html
    assert "function presenceBar" in html
    assert "type-numeric" in html
    assert "type-date" in html
    assert "presence-track" in html
    assert "presence-fill" in html
