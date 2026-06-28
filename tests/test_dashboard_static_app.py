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


def test_analysis_variable_list_does_not_scroll_inside_card() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    start = html.index(".analysis-variable-list {")
    end = html.index("}", start)
    rule = html[start:end]
    assert "max-height: none" in rule
    assert "overflow: visible" in rule


def test_analysis_workbench_auto_fits_to_available_width() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    start = html.index(".analysis-workbench {")
    end = html.index("}", start)
    rule = html[start:end]
    assert "repeat(auto-fit, minmax(min(100%, 420px), 1fr))" in rule

    controls_start = html.index(".variable-controls {")
    controls_end = html.index("}", controls_start)
    controls_rule = html[controls_start:controls_end]
    assert "repeat(auto-fit, minmax(min(100%, 150px), 1fr))" in controls_rule


def test_analysis_variable_rows_can_shrink_to_card_width() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    start = html.index(".analysis-variable-row {")
    end = html.index("}", start)
    rule = html[start:end]
    assert "grid-template-columns: minmax(0, 32%) minmax(0, 1fr) max-content" in rule
    assert "minmax(220px" not in rule
    assert "minmax(260px" not in rule


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


def test_graph_explorer_view_and_controls_exist() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    assert 'id="graph-view"' in html
    assert 'id="graph-index-variable"' in html
    assert 'id="graph-split-variable"' in html
    assert 'id="graph-value-mode"' in html
    assert 'id="graph-comparison-list"' in html
    assert 'id="graph-board"' in html
    assert "function renderGraphExplorer" in html
    assert "function splitActiveGraphNode" in html
    assert "function graphValueDisplay" in html
    assert "dataset_graph" in html


def test_graph_stage_is_handled_as_distinct_view() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    start = html.index("function renderSelectedStageView")
    end = html.index("\n      function ", start + 1)
    body = html[start:end]
    assert 'state.selectedStage === "graph"' in body
    assert "renderGraphExplorer" in body
    assert "els.graphView.classList.toggle" in body


def test_graph_mini_chart_bars_are_block_level() -> None:
    html = STATIC_APP.read_text(encoding="utf-8")
    track_start = html.index(".graph-bar-track {")
    track_end = html.index("}", track_start)
    track_rule = html[track_start:track_end]
    assert "display: block" in track_rule

    fill_start = html.index(".graph-bar-fill {")
    fill_end = html.index("}", fill_start)
    fill_rule = html[fill_start:fill_end]
    assert "display: block" in fill_rule

    hist_start = html.index(".graph-hist-bin {")
    hist_end = html.index("}", hist_start)
    hist_rule = html[hist_start:hist_end]
    assert "display: block" in hist_rule
