"""Parameterized analysis templates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from gladr.core.run_context import RunContext


@dataclass(frozen=True)
class AnalysisTemplate:
    template_id: str
    title: str
    description: str
    output: str
    category: str
    icon: str
    parameters: list[dict[str, Any]]
    run_label: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "title": self.title,
            "description": self.description,
            "output": self.output,
            "category": self.category,
            "icon": self.icon,
            "parameters": self.parameters,
            "run_label": self.run_label,
        }


UNIVARIATE_AUC_TEMPLATE = AnalysisTemplate(
    template_id="univariate_auc_screen",
    title="Univariate AUC Screen",
    description="Ranks candidate variables by apparent AUC from one logistic model per predictor.",
    output="AUC leaderboard, ROC curves, model warnings, and per-predictor inclusion counts.",
    category="Model Screening",
    icon="AUC",
    run_label="Run AUC screen",
    parameters=[
        {
            "name": "outcome",
            "label": "Binary outcome",
            "kind": "single_variable",
            "accepted_types": ["binary"],
            "required": True,
        },
        {
            "name": "predictors",
            "label": "Candidate predictors",
            "kind": "multi_variable",
            "accepted_types": ["binary", "categorical", "numeric"],
            "required": True,
        },
    ],
)

COX_REGRESSION_TEMPLATE = AnalysisTemplate(
    template_id="cox_regression",
    title="COX Regression",
    description="Fits a Cox proportional hazards model from an index date to an event date with optional censoring.",
    output="Hazard-ratio forest view, coefficient table, model warnings, and time-to-event cohort counts.",
    category="Survival Modeling",
    icon="COX",
    run_label="Run COX regression",
    parameters=[
        {
            "name": "start_date",
            "label": "Index date",
            "kind": "single_variable",
            "accepted_types": ["date"],
            "required": True,
            "preferred": ["resection_date", "presentation_date", "first_mri_date"],
        },
        {
            "name": "event_date",
            "label": "Event date",
            "kind": "single_variable",
            "accepted_types": ["date"],
            "required": True,
            "preferred": ["recurrence_date", "dod"],
        },
        {
            "name": "censor_date",
            "label": "Censor date",
            "kind": "single_variable",
            "accepted_types": ["date"],
            "required": False,
            "allow_empty": True,
            "preferred": ["dod", "postop_mri_date"],
        },
        {
            "name": "predictors",
            "label": "Model predictors",
            "kind": "multi_variable",
            "accepted_types": ["binary", "categorical", "numeric"],
            "required": True,
        },
    ],
)


def list_analysis_templates() -> list[dict[str, Any]]:
    return [UNIVARIATE_AUC_TEMPLATE.as_dict(), COX_REGRESSION_TEMPLATE.as_dict()]


def run_analysis_template(
    template_id: str,
    parameters: dict[str, Any],
    dataframe: pd.DataFrame,
    run_context: RunContext,
    manifest_run_id: str,
) -> dict[str, object]:
    if template_id == UNIVARIATE_AUC_TEMPLATE.template_id:
        return build_univariate_auc_screen(dataframe, run_context, manifest_run_id, parameters)
    if template_id == COX_REGRESSION_TEMPLATE.template_id:
        return build_cox_regression(dataframe, run_context, manifest_run_id, parameters)
    raise ValueError(f"Unknown analysis template: {template_id}")


def build_univariate_auc_screen(
    dataframe: pd.DataFrame,
    run_context: RunContext,
    manifest_run_id: str,
    parameters: dict[str, Any],
) -> dict[str, object]:
    outcome = str(parameters.get("outcome") or "")
    predictors = [str(value) for value in parameters.get("predictors") or []]
    if outcome not in dataframe.columns:
        raise ValueError(f"Outcome variable is not in the clean dataset: {outcome}")
    if not predictors:
        raise ValueError("Select at least one predictor variable.")

    outcome_encoded, outcome_levels = _encode_binary_outcome(dataframe[outcome])
    models = []
    roc_curves = []
    skipped = []

    for predictor in predictors:
        if predictor == outcome:
            skipped.append({"predictor": predictor, "reason": "Predictor matches the outcome."})
            continue
        if predictor not in dataframe.columns:
            skipped.append({"predictor": predictor, "reason": "Predictor is not in the clean dataset."})
            continue
        result = _fit_univariate_auc(dataframe[predictor], outcome_encoded, predictor)
        if result.get("status") == "skipped":
            skipped.append(result)
            continue
        models.append(result["model"])
        roc_curves.append({"predictor": predictor, "points": result["roc_points"]})

    models.sort(key=lambda item: item.get("auc") or -1, reverse=True)
    top_auc = models[0]["auc"] if models else None
    return {
        "script_id": UNIVARIATE_AUC_TEMPLATE.template_id,
        "run_id": run_context.run_id,
        "manifest_run_id": manifest_run_id,
        "run_datetime": run_context.run_datetime,
        "title": f"AUC screen for {outcome}",
        "description": "Univariate logistic models ranked by apparent AUC for a binary outcome.",
        "category": "Model Screening",
        "priority": 10,
        "metadata": {
            "n": int(outcome_encoded.notna().sum()),
            "template_id": UNIVARIATE_AUC_TEMPLATE.template_id,
            "outcome": outcome,
            "event_level": outcome_levels["event"],
            "reference_level": outcome_levels["reference"],
            "predictor_count": len(predictors),
            "fit_count": len(models),
            "top_auc": top_auc,
            "exclusions": "Each model uses complete cases for its outcome and predictor.",
            "notes": "AUC is apparent AUC on the same dataset used for fitting; cross-validation is not yet applied.",
        },
        "visualization": {
            "type": "multi",
            "library": "generic",
            "panels": [
                {
                    "type": "auc_leaderboard",
                    "config": {
                        "predictor_field": "predictor",
                        "auc_field": "auc",
                    },
                },
                {
                    "type": "roc_overlay",
                    "config": {
                        "predictor_field": "predictor",
                    },
                },
                {
                    "type": "table",
                    "config": {
                        "columns": [
                            {"field": "rank", "label": "Rank", "format": "int"},
                            {"field": "predictor", "label": "Predictor", "format": "string"},
                            {"field": "auc", "label": "AUC", "format": "float3"},
                            {"field": "n", "label": "N", "format": "int"},
                            {"field": "events", "label": "Events", "format": "int"},
                            {"field": "missing", "label": "Missing", "format": "int"},
                        ],
                    },
                },
            ],
        },
        "data": {
            "outcome": outcome,
            "outcome_levels": outcome_levels,
            "rows": [
                {**model, "rank": index + 1}
                for index, model in enumerate(models)
            ],
            "roc_curves": roc_curves,
            "skipped": skipped,
        },
    }


def build_cox_regression(
    dataframe: pd.DataFrame,
    run_context: RunContext,
    manifest_run_id: str,
    parameters: dict[str, Any],
) -> dict[str, object]:
    start_date = str(parameters.get("start_date") or "")
    event_date = str(parameters.get("event_date") or "")
    censor_date = str(parameters.get("censor_date") or "")
    predictors = [str(value) for value in parameters.get("predictors") or []]
    for field, label in [(start_date, "Index date"), (event_date, "Event date")]:
        if field not in dataframe.columns:
            raise ValueError(f"{label} variable is not in the clean dataset: {field}")
    if censor_date and censor_date not in dataframe.columns:
        raise ValueError(f"Censor date variable is not in the clean dataset: {censor_date}")
    if not predictors:
        raise ValueError("Select at least one predictor variable.")

    survival_frame, survival_exclusions = _build_survival_frame(dataframe, start_date, event_date, censor_date)
    if survival_frame.empty:
        raise ValueError("No valid time-to-event rows are available for the selected date fields.")
    if int(survival_frame["event"].sum()) == 0:
        raise ValueError("At least one observed event is required for COX regression.")

    design, terms, predictor_exclusions = _build_cox_design_matrix(dataframe, survival_frame.index, predictors)
    skipped = survival_exclusions + predictor_exclusions
    if design.shape[1] == 0:
        raise ValueError("No usable predictor terms are available after encoding.")

    model_frame = survival_frame.loc[design.index].copy()
    if model_frame.empty:
        raise ValueError("No complete cases remain after applying the selected predictors.")
    if int(model_frame["event"].sum()) == 0:
        raise ValueError("Complete cases do not include an observed event.")

    beta, standard_errors, converged, fit_warning, log_likelihood = _fit_cox_ph(
        design.to_numpy(dtype=float),
        model_frame["duration_days"].to_numpy(dtype=float),
        model_frame["event"].to_numpy(dtype=int),
    )
    rows = []
    for index, term in enumerate(terms):
        coef = float(beta[index])
        se = float(standard_errors[index]) if standard_errors is not None else math.nan
        z_value = coef / se if se and not math.isnan(se) and se > 0 else math.nan
        p_value = _two_sided_normal_p(z_value) if not math.isnan(z_value) else None
        rows.append({
            "term": term["name"],
            "predictor": term["predictor"],
            "kind": term["kind"],
            "reference_level": term.get("reference"),
            "coefficient": round(coef, 4),
            "hazard_ratio": round(float(math.exp(np.clip(coef, -30, 30))), 3),
            "ci_low": round(float(math.exp(np.clip(coef - 1.96 * se, -30, 30))), 3) if not math.isnan(se) else None,
            "ci_high": round(float(math.exp(np.clip(coef + 1.96 * se, -30, 30))), 3) if not math.isnan(se) else None,
            "standard_error": round(se, 4) if not math.isnan(se) else None,
            "z": round(z_value, 3) if not math.isnan(z_value) else None,
            "p_value": round(p_value, 4) if p_value is not None else None,
        })

    warnings = []
    if fit_warning:
        warnings.append(fit_warning)
    if not converged:
        warnings.append("Model did not fully converge.")
    if int(model_frame["event"].sum()) <= max(len(terms) * 5, 5):
        warnings.append("Low event count relative to model terms; estimates may be unstable.")

    duration = model_frame["duration_days"]
    return {
        "script_id": COX_REGRESSION_TEMPLATE.template_id,
        "run_id": run_context.run_id,
        "manifest_run_id": manifest_run_id,
        "run_datetime": run_context.run_datetime,
        "title": f"COX regression for {event_date}",
        "description": f"Proportional hazards model from {start_date} to {event_date}.",
        "category": "Survival Modeling",
        "priority": 9,
        "metadata": {
            "n": int(len(model_frame)),
            "template_id": COX_REGRESSION_TEMPLATE.template_id,
            "start_date": start_date,
            "event_date": event_date,
            "censor_date": censor_date or None,
            "events": int(model_frame["event"].sum()),
            "censored": int(len(model_frame) - model_frame["event"].sum()),
            "predictor_count": len(predictors),
            "term_count": len(terms),
            "log_likelihood": round(float(log_likelihood), 4),
            "exclusions": "Rows require valid index dates, positive follow-up time, and complete selected predictors.",
            "notes": "Cox estimates use Breslow handling for tied event times. If no censor date is selected, censored rows use the latest valid date available on that row.",
        },
        "visualization": {
            "type": "multi",
            "library": "generic",
            "panels": [
                {
                    "type": "cox_forest",
                    "config": {
                        "term_field": "term",
                        "hr_field": "hazard_ratio",
                        "ci_low_field": "ci_low",
                        "ci_high_field": "ci_high",
                    },
                },
                {
                    "type": "table",
                    "config": {
                        "columns": [
                            {"field": "term", "label": "Term", "format": "string"},
                            {"field": "hazard_ratio", "label": "HR", "format": "float3"},
                            {"field": "ci_low", "label": "95% CI low", "format": "float3"},
                            {"field": "ci_high", "label": "95% CI high", "format": "float3"},
                            {"field": "p_value", "label": "P", "format": "pvalue"},
                        ],
                    },
                },
            ],
        },
        "data": {
            "start_date": start_date,
            "event_date": event_date,
            "censor_date": censor_date or None,
            "rows": rows,
            "survival_summary": {
                "duration_min_days": int(duration.min()),
                "duration_median_days": int(duration.median()),
                "duration_max_days": int(duration.max()),
                "events": int(model_frame["event"].sum()),
                "censored": int(len(model_frame) - model_frame["event"].sum()),
            },
            "warnings": warnings,
            "skipped": skipped,
        },
    }


def _build_survival_frame(
    dataframe: pd.DataFrame,
    start_date: str,
    event_date: str,
    censor_date: str,
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    date_columns = [column for column in dataframe.columns if "date" in column.lower() or column.lower() in {"dob", "dod"}]
    start_values = pd.to_datetime(dataframe[start_date], errors="coerce")
    event_values = pd.to_datetime(dataframe[event_date], errors="coerce")
    censor_values = pd.to_datetime(dataframe[censor_date], errors="coerce") if censor_date else pd.Series(pd.NaT, index=dataframe.index)
    row_latest_dates = dataframe[date_columns].apply(lambda row: pd.to_datetime(row, errors="coerce").max(), axis=1) if date_columns else pd.Series(pd.NaT, index=dataframe.index)

    rows = []
    exclusions: list[dict[str, str]] = []
    for index in dataframe.index:
        start = start_values.loc[index]
        if pd.isna(start):
            exclusions.append({"predictor": str(index), "reason": "Missing index date."})
            continue
        event = event_values.loc[index]
        has_event = not pd.isna(event)
        if has_event:
            end = event
        else:
            end = censor_values.loc[index] if not pd.isna(censor_values.loc[index]) else row_latest_dates.loc[index]
        if pd.isna(end):
            exclusions.append({"predictor": str(index), "reason": "Missing event or censor date."})
            continue
        duration = (end - start).days
        if duration <= 0:
            exclusions.append({"predictor": str(index), "reason": "Non-positive follow-up time."})
            continue
        rows.append({"index": index, "duration_days": float(duration), "event": int(has_event)})

    if not rows:
        return pd.DataFrame(columns=["duration_days", "event"]), exclusions
    return pd.DataFrame(rows).set_index("index"), exclusions


def _build_cox_design_matrix(
    dataframe: pd.DataFrame,
    eligible_index: pd.Index,
    predictors: list[str],
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, str]]]:
    source = dataframe.loc[eligible_index]
    skipped: list[dict[str, str]] = []
    columns: list[pd.Series] = []
    terms: list[dict[str, Any]] = []

    for predictor in predictors:
        if predictor not in source.columns:
            skipped.append({"predictor": predictor, "reason": "Predictor is not in the clean dataset."})
            continue
        series = source[predictor]
        if series.dropna().nunique() < 2:
            skipped.append({"predictor": predictor, "reason": "Predictor has fewer than two observed levels."})
            continue
        design, predictor_terms, reference = _build_design_matrix(series.dropna())
        if design.shape[1] < 2:
            skipped.append({"predictor": predictor, "reason": "No usable predictor columns after encoding."})
            continue
        term_frame = pd.DataFrame(design[:, 1:], index=series.dropna().index)
        for term_index, term in enumerate(predictor_terms):
            term_name = predictor if term["kind"] == "numeric" else f"{predictor}: {term['name']}"
            column_name = f"{predictor}__{term_index}"
            column = pd.Series(np.nan, index=source.index, name=column_name)
            column.loc[term_frame.index] = term_frame.iloc[:, term_index]
            columns.append(column)
            terms.append({
                "name": term_name,
                "predictor": predictor,
                "kind": term["kind"],
                "reference": term.get("reference", reference),
            })

    if not columns:
        return pd.DataFrame(index=source.index), terms, skipped
    matrix = pd.concat(columns, axis=1).dropna()
    return matrix, terms, skipped


def _fit_cox_ph(
    x: np.ndarray,
    duration: np.ndarray,
    event: np.ndarray,
) -> tuple[np.ndarray, np.ndarray | None, bool, str | None, float]:
    beta = np.zeros(x.shape[1])
    warning = None
    hessian = np.eye(x.shape[1]) * -1
    log_likelihood = math.nan
    for _ in range(80):
        log_likelihood, gradient, hessian = _cox_loglik_gradient_hessian(beta, x, duration, event)
        ridge = np.eye(x.shape[1]) * 1e-6
        try:
            step = np.linalg.solve(hessian - ridge, gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.pinv(hessian - ridge) @ gradient
            warning = "Used pseudo-inverse due to an unstable model matrix."
        beta_next = beta - step
        if np.max(np.abs(beta_next - beta)) < 1e-6:
            _, _, final_hessian = _cox_loglik_gradient_hessian(beta_next, x, duration, event)
            return beta_next, _cox_standard_errors(final_hessian), True, warning, log_likelihood
        beta = beta_next
    _, _, final_hessian = _cox_loglik_gradient_hessian(beta, x, duration, event)
    return beta, _cox_standard_errors(final_hessian), False, warning, log_likelihood


def _cox_loglik_gradient_hessian(
    beta: np.ndarray,
    x: np.ndarray,
    duration: np.ndarray,
    event: np.ndarray,
) -> tuple[float, np.ndarray, np.ndarray]:
    eta = np.clip(x @ beta, -30, 30)
    weights = np.exp(eta)
    gradient = np.zeros(x.shape[1])
    hessian = np.zeros((x.shape[1], x.shape[1]))
    log_likelihood = 0.0

    for event_time in sorted(set(duration[event == 1].tolist())):
        event_mask = (duration == event_time) & (event == 1)
        risk_mask = duration >= event_time
        event_count = int(event_mask.sum())
        risk_weights = weights[risk_mask]
        risk_x = x[risk_mask]
        risk_sum = float(risk_weights.sum())
        if risk_sum <= 0:
            continue
        weighted_mean = (risk_weights[:, None] * risk_x).sum(axis=0) / risk_sum
        weighted_second = (risk_x.T @ (risk_weights[:, None] * risk_x)) / risk_sum
        log_likelihood += float(eta[event_mask].sum() - event_count * math.log(risk_sum))
        gradient += x[event_mask].sum(axis=0) - event_count * weighted_mean
        hessian -= event_count * (weighted_second - np.outer(weighted_mean, weighted_mean))
    return log_likelihood, gradient, hessian


def _cox_standard_errors(hessian: np.ndarray) -> np.ndarray | None:
    information = -hessian
    try:
        variance = np.linalg.inv(information)
    except np.linalg.LinAlgError:
        variance = np.linalg.pinv(information)
    diagonal = np.diag(variance)
    if np.any(diagonal < 0):
        return None
    return np.sqrt(diagonal)


def _two_sided_normal_p(z_value: float) -> float:
    tail = 0.5 * math.erfc(abs(z_value) / math.sqrt(2))
    return min(max(2 * tail, 0.0), 1.0)


def _encode_binary_outcome(series: pd.Series) -> tuple[pd.Series, dict[str, object]]:
    non_null = series.dropna()
    normalized = non_null.map(_normalize_binary_label)
    unique_values = sorted(normalized.dropna().unique().tolist(), key=str)
    if len(unique_values) != 2:
        raise ValueError("Outcome must have exactly two non-missing levels.")

    reference, event = _choose_binary_levels(unique_values)
    encoded = series.map(_normalize_binary_label).map({reference: 0, event: 1})
    return encoded, {"reference": reference, "event": event}


def _choose_binary_levels(values: list[object]) -> tuple[object, object]:
    preferred_event = [True, 1, "1", "yes", "y", "true", "date", "death", "recurrence", "recurred"]
    for value in preferred_event:
        if value in values:
            reference = next(item for item in values if item != value)
            return reference, value
    return values[0], values[1]


def _fit_univariate_auc(predictor_series: pd.Series, outcome_encoded: pd.Series, predictor: str) -> dict[str, Any]:
    frame = pd.DataFrame({"outcome": outcome_encoded, "predictor": predictor_series}).dropna()
    if frame.empty:
        return {"status": "skipped", "predictor": predictor, "reason": "No complete cases."}
    if int(frame["outcome"].nunique()) != 2:
        return {"status": "skipped", "predictor": predictor, "reason": "Complete cases do not include both outcome classes."}
    if int(frame["predictor"].nunique(dropna=True)) < 2:
        return {"status": "skipped", "predictor": predictor, "reason": "Predictor has fewer than two observed levels."}

    design, terms, reference = _build_design_matrix(frame["predictor"])
    if design.shape[1] < 2:
        return {"status": "skipped", "predictor": predictor, "reason": "No usable predictor columns after encoding."}

    y = frame["outcome"].astype(float).to_numpy()
    beta, converged, fit_warning = _fit_logistic(design, y)
    probabilities = _sigmoid(design @ beta)
    auc = _auc_score(y, probabilities)
    roc_points = _roc_points(y, probabilities)
    warnings = [fit_warning] if fit_warning else []
    if not converged:
        warnings.append("Model did not fully converge.")
    event_count = int(y.sum())
    non_event_count = int(len(y) - event_count)
    if min(event_count, non_event_count) < 5:
        warnings.append("Low event or non-event count.")

    return {
        "status": "fit",
        "model": {
            "predictor": predictor,
            "auc": round(float(auc), 3) if auc is not None else None,
            "n": int(len(y)),
            "events": event_count,
            "non_events": non_event_count,
            "missing": int(len(predictor_series) - len(frame)),
            "term_count": len(terms),
            "terms": terms,
            "reference_level": reference,
            "warnings": warnings,
        },
        "roc_points": roc_points,
    }


def _build_design_matrix(series: pd.Series) -> tuple[np.ndarray, list[dict[str, Any]], object | None]:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all() and series.nunique(dropna=True) > 2:
        values = numeric.astype(float).to_numpy()
        return np.column_stack([np.ones(len(values)), values]), [{"name": series.name or "predictor", "kind": "numeric"}], None

    categorical = series.astype(str)
    levels = sorted(categorical.unique().tolist(), key=str)
    reference = levels[0]
    columns = [np.ones(len(categorical))]
    terms = []
    for level in levels[1:]:
        columns.append((categorical == level).astype(float).to_numpy())
        terms.append({"name": str(level), "kind": "indicator", "reference": str(reference)})
    return np.column_stack(columns), terms, reference


def _fit_logistic(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, bool, str | None]:
    beta = np.zeros(x.shape[1])
    warning = None
    for _ in range(80):
        probabilities = np.clip(_sigmoid(x @ beta), 1e-8, 1 - 1e-8)
        weights = probabilities * (1 - probabilities)
        gradient = x.T @ (y - probabilities)
        hessian = -(x.T @ (weights[:, None] * x))
        ridge = np.eye(x.shape[1]) * 1e-6
        ridge[0, 0] = 0
        try:
            step = np.linalg.solve(hessian - ridge, gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.pinv(hessian - ridge) @ gradient
            warning = "Used pseudo-inverse due to an unstable model matrix."
        beta_next = beta - step
        if np.max(np.abs(beta_next - beta)) < 1e-6:
            return beta_next, True, warning
        beta = beta_next
    return beta, False, warning


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(values, -35, 35)))


def _auc_score(y: np.ndarray, scores: np.ndarray) -> float | None:
    positives = scores[y == 1]
    negatives = scores[y == 0]
    if len(positives) == 0 or len(negatives) == 0:
        return None
    wins = 0.0
    for positive_score in positives:
        wins += float(np.sum(positive_score > negatives))
        wins += 0.5 * float(np.sum(positive_score == negatives))
    return wins / (len(positives) * len(negatives))


def _roc_points(y: np.ndarray, scores: np.ndarray) -> list[dict[str, float]]:
    thresholds = [math.inf] + sorted(set(scores.tolist()), reverse=True) + [-math.inf]
    positives = max(int(y.sum()), 1)
    negatives = max(int(len(y) - y.sum()), 1)
    points = []
    for threshold in thresholds:
        predicted = scores >= threshold
        true_positive = int(np.sum(predicted & (y == 1)))
        false_positive = int(np.sum(predicted & (y == 0)))
        points.append({
            "fpr": round(false_positive / negatives, 4),
            "tpr": round(true_positive / positives, 4),
        })
    compact: list[dict[str, float]] = []
    for point in points:
        if not compact or compact[-1] != point:
            compact.append(point)
    return compact


def _normalize_binary_label(value: object) -> object | None:
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) in {0.0, 1.0}:
            return int(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "yes", "y"}:
        return "yes"
    if normalized in {"false", "no", "n"}:
        return "no"
    return normalized
