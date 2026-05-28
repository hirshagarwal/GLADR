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
    cohort_display: str = "none"

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
            "cohort_display": self.cohort_display,
        }


UNIVARIATE_AUC_TEMPLATE = AnalysisTemplate(
    template_id="univariate_auc_screen",
    title="Univariate AUC Screen",
    description="Ranks candidate variables by apparent AUC from one logistic model per predictor.",
    output="AUC leaderboard, ROC curves, model warnings, and per-predictor inclusion counts.",
    category="Model Screening",
    icon="AUC",
    run_label="Run AUC screen",
    cohort_display="none",
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

MULTIVARIABLE_LOGISTIC_TEMPLATE = AnalysisTemplate(
    template_id="multivariable_logistic_regression",
    title="Multivariable Logistic Regression",
    description="Fits one user-selected multivariable logistic model for a binary outcome.",
    output="Apparent AUC, cross-validated AUC when feasible, odds ratios, confidence intervals, and model warnings.",
    category="Regression Modeling",
    icon="LR",
    run_label="Run logistic regression",
    cohort_display="shared_model_frame",
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
            "label": "Model predictors",
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
    cohort_display="shared_model_frame",
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


LASSO_LOGISTIC_TEMPLATE = AnalysisTemplate(
    template_id="lasso_logistic_regression",
    title="LASSO Logistic Regression",
    description="Selects predictors for a binary outcome using cross-validated L1-regularized logistic regression.",
    output="CV-selected lambda, selected terms, standardized coefficients, odds ratios, apparent AUC, and model-fit warnings.",
    category="Model Selection",
    icon="L1",
    run_label="Run LASSO regression",
    cohort_display="shared_model_frame",
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


def list_analysis_templates() -> list[dict[str, Any]]:
    return [
        UNIVARIATE_AUC_TEMPLATE.as_dict(),
        MULTIVARIABLE_LOGISTIC_TEMPLATE.as_dict(),
        LASSO_LOGISTIC_TEMPLATE.as_dict(),
        COX_REGRESSION_TEMPLATE.as_dict(),
    ]


def run_analysis_template(
    template_id: str,
    parameters: dict[str, Any],
    dataframe: pd.DataFrame,
    run_context: RunContext,
    manifest_run_id: str,
) -> dict[str, object]:
    if template_id == UNIVARIATE_AUC_TEMPLATE.template_id:
        return build_univariate_auc_screen(dataframe, run_context, manifest_run_id, parameters)
    if template_id == MULTIVARIABLE_LOGISTIC_TEMPLATE.template_id:
        return build_multivariable_logistic_regression(dataframe, run_context, manifest_run_id, parameters)
    if template_id == LASSO_LOGISTIC_TEMPLATE.template_id:
        return build_lasso_logistic_regression(dataframe, run_context, manifest_run_id, parameters)
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
        "cohort_display": UNIVARIATE_AUC_TEMPLATE.cohort_display,
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


def build_multivariable_logistic_regression(
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
    design, terms, skipped = _build_lasso_design_matrix(dataframe, predictors, outcome)
    if design.shape[1] == 0:
        raise ValueError("No usable predictor terms are available after encoding.")

    model_frame = design.copy()
    model_frame["outcome"] = outcome_encoded
    model_frame = model_frame.dropna()
    if model_frame.empty:
        raise ValueError("No complete cases remain after applying the selected predictors.")
    if int(model_frame["outcome"].nunique()) != 2:
        raise ValueError("Complete cases do not include both outcome classes.")

    x_terms = model_frame.drop(columns=["outcome"]).to_numpy(dtype=float)
    y = model_frame["outcome"].astype(float).to_numpy()
    usable_mask = np.isfinite(x_terms.std(axis=0)) & (x_terms.std(axis=0) > 1e-12)
    if not np.any(usable_mask):
        raise ValueError("No predictor terms vary within the complete-case model frame.")
    x_terms = x_terms[:, usable_mask]
    terms = [term for term, usable in zip(terms, usable_mask, strict=True) if usable]
    x = np.column_stack([np.ones(len(y)), x_terms])

    beta, converged, fit_warning = _fit_logistic(x, y)
    probabilities = _sigmoid(x @ beta)
    auc = _auc_score(y, probabilities)
    roc_points = _roc_points(y, probabilities)
    standard_errors = _logistic_standard_errors(x, beta)

    rows = []
    for index, term in enumerate(terms, start=1):
        coefficient = float(beta[index])
        se = float(standard_errors[index]) if standard_errors is not None else math.nan
        z_value = coefficient / se if se and not math.isnan(se) and se > 0 else math.nan
        p_value = _two_sided_normal_p(z_value) if not math.isnan(z_value) else None
        rows.append({
            "term": term["name"],
            "predictor": term["predictor"],
            "kind": term["kind"],
            "reference_level": term.get("reference"),
            "coefficient": round(coefficient, 4),
            "odds_ratio": round(float(math.exp(np.clip(coefficient, -30, 30))), 3),
            "ci_low": round(float(math.exp(np.clip(coefficient - 1.96 * se, -30, 30))), 3) if not math.isnan(se) else None,
            "ci_high": round(float(math.exp(np.clip(coefficient + 1.96 * se, -30, 30))), 3) if not math.isnan(se) else None,
            "standard_error": round(se, 4) if not math.isnan(se) else None,
            "z": round(z_value, 3) if not math.isnan(z_value) else None,
            "p_value": round(p_value, 4) if p_value is not None else None,
        })

    warnings = []
    if fit_warning:
        warnings.append(fit_warning)
    if not converged:
        warnings.append("Model did not fully converge.")
    if standard_errors is None:
        warnings.append("Confidence intervals are unavailable because the model information matrix is unstable.")

    event_count = int(y.sum())
    non_event_count = int(len(y) - event_count)
    if min(event_count, non_event_count) < 5:
        warnings.append("Low event or non-event count.")
    if event_count <= max(len(terms) * 5, 5):
        warnings.append("Low event count relative to model terms; estimates may be unstable.")

    cv_result = _cross_validated_logistic_auc(x_terms, y)
    if cv_result["status"] == "fallback":
        warnings.append(f"Cross-validated AUC was not estimated: {cv_result['reason']}.")
    cohort = _complete_case_cohort(
        input_rows=len(dataframe),
        included_rows=len(model_frame),
        required_fields=[outcome, *predictors],
        rule_description="Rows require complete outcome and selected predictor values.",
    )

    return {
        "script_id": MULTIVARIABLE_LOGISTIC_TEMPLATE.template_id,
        "run_id": run_context.run_id,
        "manifest_run_id": manifest_run_id,
        "run_datetime": run_context.run_datetime,
        "title": f"Multivariable logistic regression for {outcome}",
        "description": "User-selected multivariable logistic regression for a binary outcome.",
        "category": "Regression Modeling",
        "priority": 8,
        "metadata": {
            "n": int(len(y)),
            "template_id": MULTIVARIABLE_LOGISTIC_TEMPLATE.template_id,
            "outcome": outcome,
            "event_level": outcome_levels["event"],
            "reference_level": outcome_levels["reference"],
            "events": event_count,
            "non_events": non_event_count,
            "predictor_count": len(predictors),
            "term_count": len(terms),
            "auc": round(float(auc), 3) if auc is not None else None,
            "cv_auc": _round_optional(cv_result.get("cv_auc"), 3),
            "cv_auc_se": _round_optional(cv_result.get("cv_auc_se"), 3),
            "cv_folds": cv_result.get("fold_count", 0),
            "exclusions": "Rows require complete outcome and selected predictor values; categorical predictors are indicator encoded.",
            "notes": "Predictors are user-selected. AUC is apparent AUC on the fitting data; stratified cross-validated AUC is reported when each class has enough complete cases.",
        },
        "cohort_display": MULTIVARIABLE_LOGISTIC_TEMPLATE.cohort_display,
        "cohort": cohort,
        "visualization": {
            "type": "multi",
            "library": "generic",
            "panels": [
                {
                    "type": "table",
                    "config": {
                        "columns": [
                            {"field": "term", "label": "Term", "format": "string"},
                            {"field": "odds_ratio", "label": "OR", "format": "float3"},
                            {"field": "ci_low", "label": "95% CI low", "format": "float3"},
                            {"field": "ci_high", "label": "95% CI high", "format": "float3"},
                            {"field": "p_value", "label": "P", "format": "pvalue"},
                        ],
                    },
                },
            ],
        },
        "data": {
            "outcome": outcome,
            "outcome_levels": outcome_levels,
            "n": int(len(y)),
            "events": event_count,
            "non_events": non_event_count,
            "predictor_count": len(predictors),
            "term_count": len(terms),
            "auc": round(float(auc), 3) if auc is not None else None,
            "cv_auc": _round_optional(cv_result.get("cv_auc"), 3),
            "cv_auc_se": _round_optional(cv_result.get("cv_auc_se"), 3),
            "cv_folds": cv_result.get("fold_count", 0),
            "cv_fold_aucs": [_round_optional(value, 3) for value in cv_result.get("fold_aucs", [])],
            "cv_fallback_reason": cv_result.get("reason"),
            "roc_curves": [{"predictor": "Multivariable model", "points": roc_points}],
            "rows": rows,
            "warnings": warnings,
            "skipped": skipped,
        },
    }


def build_lasso_logistic_regression(
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
    design, terms, skipped = _build_lasso_design_matrix(dataframe, predictors, outcome)
    if design.shape[1] == 0:
        raise ValueError("No usable predictor terms are available after encoding.")

    model_frame = design.copy()
    model_frame["outcome"] = outcome_encoded
    model_frame = model_frame.dropna()
    if model_frame.empty:
        raise ValueError("No complete cases remain after applying the selected predictors.")
    if int(model_frame["outcome"].nunique()) != 2:
        raise ValueError("Complete cases do not include both outcome classes.")

    x_raw = model_frame.drop(columns=["outcome"]).to_numpy(dtype=float)
    y = model_frame["outcome"].astype(float).to_numpy()
    x_standardized, _, _, usable_mask = _standardize_lasso_design(x_raw)
    if x_standardized.shape[1] == 0:
        raise ValueError("No predictor terms vary within the complete-case model frame.")

    terms = [term for term, usable in zip(terms, usable_mask, strict=True) if usable]
    x_model = x_raw[:, usable_mask]
    result = _fit_lasso_logistic_path(x_model, y)
    beta_standardized = result["beta"]
    beta_original = beta_standardized / result["scales"]
    intercept = float(result["intercept"] - np.sum(beta_standardized * result["means"] / result["scales"]))
    probabilities = _sigmoid(intercept + x_model @ beta_original)
    auc = _auc_score(y, probabilities)

    rows = []
    for index, term in enumerate(terms):
        coefficient = float(beta_original[index])
        standardized = float(beta_standardized[index])
        selected = abs(standardized) > 1e-5
        rows.append({
            "term": term["name"],
            "predictor": term["predictor"],
            "kind": term["kind"],
            "reference_level": term.get("reference"),
            "coefficient": round(coefficient, 4),
            "standardized_coefficient": round(standardized, 4),
            "abs_standardized_coefficient": round(abs(standardized), 4),
            "odds_ratio": round(float(math.exp(np.clip(coefficient, -30, 30))), 3),
            "selected": selected,
            "selected_rank": None,
        })

    rows.sort(key=lambda row: (not row["selected"], -abs(float(row["standardized_coefficient"])), row["term"]))
    selected_count = 0
    for row in rows:
        if row["selected"]:
            selected_count += 1
            row["selected_rank"] = selected_count

    warnings = []
    if result.get("fallback_reason"):
        warnings.append(f"Cross-validation was not feasible ({result['fallback_reason']}); used BIC-selected penalty.")
    if not result["converged"]:
        warnings.append("LASSO optimizer did not fully converge at the selected penalty.")
    if selected_count == 0:
        warnings.append("No candidate terms were selected at the automatically chosen penalty.")
    if len(y) <= max(selected_count * 5, 10):
        warnings.append("Low complete-case count relative to selected terms; estimates may be unstable.")

    event_count = int(y.sum())
    non_event_count = int(len(y) - event_count)
    selection_note = (
        f"Penalty strength selected by stratified {result['cv_folds']}-fold cross-validation using "
        f"{result['selection_rule']} on log loss. AUC is apparent AUC on the fitting data."
        if result["selection_method"] == "cross_validation"
        else f"Penalty strength selected by BIC because cross-validation was not feasible: {result['fallback_reason']}. "
        "AUC is apparent AUC on the fitting data."
    )
    cohort = _complete_case_cohort(
        input_rows=len(dataframe),
        included_rows=len(model_frame),
        required_fields=[outcome, *predictors],
        rule_description="Rows require complete outcome and selected predictor values.",
    )
    return {
        "script_id": LASSO_LOGISTIC_TEMPLATE.template_id,
        "run_id": run_context.run_id,
        "manifest_run_id": manifest_run_id,
        "run_datetime": run_context.run_datetime,
        "title": f"LASSO logistic regression for {outcome}",
        "description": "L1-regularized logistic regression for binary-outcome predictor selection.",
        "category": "Model Selection",
        "priority": 8,
        "metadata": {
            "n": int(len(y)),
            "template_id": LASSO_LOGISTIC_TEMPLATE.template_id,
            "outcome": outcome,
            "event_level": outcome_levels["event"],
            "reference_level": outcome_levels["reference"],
            "predictor_count": len(predictors),
            "candidate_terms": len(terms),
            "selected_terms": selected_count,
            "penalty": round(float(result["penalty"]), 6),
            "selection_method": result["selection_method"],
            "selection_rule": result["selection_rule"],
            "cv_folds": result["cv_folds"],
            "cv_metric": result["cv_metric"],
            "cv_mean_loss": _round_optional(result.get("cv_mean_loss"), 4),
            "cv_se_loss": _round_optional(result.get("cv_se_loss"), 4),
            "lambda_min": _round_optional(result.get("lambda_min"), 6),
            "lambda_1se": _round_optional(result.get("lambda_1se"), 6),
            "bic_penalty": round(float(result["bic_penalty"]), 6),
            "bic": round(float(result["bic"]), 4),
            "auc": round(float(auc), 3) if auc is not None else None,
            "exclusions": "Rows require complete outcome and selected predictor values; categorical predictors are indicator encoded.",
            "notes": selection_note,
        },
        "cohort_display": LASSO_LOGISTIC_TEMPLATE.cohort_display,
        "cohort": cohort,
        "visualization": {
            "type": "multi",
            "library": "generic",
            "panels": [
                {
                    "type": "table",
                    "config": {
                        "columns": [
                            {"field": "selected_rank", "label": "Rank", "format": "int"},
                            {"field": "term", "label": "Term", "format": "string"},
                            {"field": "standardized_coefficient", "label": "Std coef (1 SD)", "format": "float3"},
                            {"field": "coefficient", "label": "Raw log-odds coef", "format": "float3"},
                            {"field": "odds_ratio", "label": "OR", "format": "float3"},
                            {"field": "selected", "label": "Selected", "format": "string"},
                        ],
                    },
                },
            ],
        },
        "data": {
            "outcome": outcome,
            "outcome_levels": outcome_levels,
            "n": int(len(y)),
            "events": event_count,
            "non_events": non_event_count,
            "candidate_terms": len(terms),
            "selected_terms": selected_count,
            "penalty": round(float(result["penalty"]), 6),
            "selection_method": result["selection_method"],
            "selection_rule": result["selection_rule"],
            "cv_folds": result["cv_folds"],
            "cv_metric": result["cv_metric"],
            "cv_mean_loss": _round_optional(result.get("cv_mean_loss"), 4),
            "cv_se_loss": _round_optional(result.get("cv_se_loss"), 4),
            "lambda_min": _round_optional(result.get("lambda_min"), 6),
            "lambda_1se": _round_optional(result.get("lambda_1se"), 6),
            "lambda_min_cv_loss": _round_optional(result.get("lambda_min_cv_loss"), 4),
            "lambda_1se_cv_loss": _round_optional(result.get("lambda_1se_cv_loss"), 4),
            "bic_penalty": round(float(result["bic_penalty"]), 6),
            "bic": round(float(result["bic"]), 4),
            "fallback_reason": result.get("fallback_reason"),
            "cv_path": result.get("cv_path", []),
            "auc": round(float(auc), 3) if auc is not None else None,
            "rows": rows,
            "warnings": warnings,
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
    cohort = _cox_cohort(
        input_rows=len(dataframe),
        survival_rows=len(survival_frame),
        included_rows=len(model_frame),
        required_fields=[field for field in [start_date, event_date, censor_date, *predictors] if field],
    )
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
        "cohort_display": COX_REGRESSION_TEMPLATE.cohort_display,
        "cohort": cohort,
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


def _complete_case_cohort(
    *,
    input_rows: int,
    included_rows: int,
    required_fields: list[str],
    rule_description: str,
) -> dict[str, object]:
    excluded_rows = max(input_rows - included_rows, 0)
    return {
        "display": "shared_model_frame",
        "basis": "complete_case",
        "input_rows": int(input_rows),
        "included_rows": int(included_rows),
        "excluded_rows": int(excluded_rows),
        "required_fields": list(dict.fromkeys(required_fields)),
        "rules": [
            {
                "rule": "missing_required_model_field",
                "count": int(excluded_rows),
                "description": rule_description,
            }
        ],
    }


def _cox_cohort(
    *,
    input_rows: int,
    survival_rows: int,
    included_rows: int,
    required_fields: list[str],
) -> dict[str, object]:
    time_excluded = max(input_rows - survival_rows, 0)
    predictor_excluded = max(survival_rows - included_rows, 0)
    return {
        "display": "shared_model_frame",
        "basis": "valid_time_to_event_complete_case",
        "input_rows": int(input_rows),
        "included_rows": int(included_rows),
        "excluded_rows": int(max(input_rows - included_rows, 0)),
        "required_fields": list(dict.fromkeys(required_fields)),
        "rules": [
            {
                "rule": "invalid_time_to_event",
                "count": int(time_excluded),
                "description": "Rows require valid index dates, event or censor dates, and positive follow-up time.",
            },
            {
                "rule": "missing_required_model_field",
                "count": int(predictor_excluded),
                "description": "Rows require complete selected predictor values.",
            },
        ],
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


def _round_optional(value: object, digits: int) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return round(numeric, digits)


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


def _cross_validated_logistic_auc(x_terms: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    class_counts = [int(np.sum(y == value)) for value in np.unique(y)]
    min_class_count = min(class_counts) if class_counts else 0
    if min_class_count < 3:
        return {
            "status": "fallback",
            "reason": "fewer than 3 complete cases in at least one outcome class",
        }

    fold_count = min(5, min_class_count)
    fold_aucs = []
    for validation_index in _stratified_folds(y, fold_count):
        training_mask = np.ones(len(y), dtype=bool)
        training_mask[validation_index] = False
        x_train_terms = x_terms[training_mask]
        x_validation_terms = x_terms[validation_index]
        y_train = y[training_mask]
        y_validation = y[validation_index]
        if int(np.unique(y_train).size) != 2 or int(np.unique(y_validation).size) != 2:
            return {
                "status": "fallback",
                "reason": "stratified folds could not preserve both outcome classes",
            }

        x_train_terms, x_validation_terms = _standardize_lasso_fold(x_train_terms, x_validation_terms)
        x_train = np.column_stack([np.ones(len(y_train)), x_train_terms])
        x_validation = np.column_stack([np.ones(len(y_validation)), x_validation_terms])
        beta, _, _ = _fit_logistic(x_train, y_train)
        auc = _auc_score(y_validation, _sigmoid(x_validation @ beta))
        if auc is None:
            return {"status": "fallback", "reason": "fold AUC could not be estimated"}
        fold_aucs.append(float(auc))

    return {
        "status": "fit",
        "fold_count": fold_count,
        "cv_auc": float(np.mean(fold_aucs)),
        "cv_auc_se": float(np.std(fold_aucs, ddof=1) / math.sqrt(fold_count)),
        "fold_aucs": fold_aucs,
    }


def _build_lasso_design_matrix(
    dataframe: pd.DataFrame,
    predictors: list[str],
    outcome: str,
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, str]]]:
    skipped: list[dict[str, str]] = []
    columns: list[pd.Series] = []
    terms: list[dict[str, Any]] = []

    for predictor in predictors:
        if predictor == outcome:
            skipped.append({"predictor": predictor, "reason": "Predictor matches the outcome."})
            continue
        if predictor not in dataframe.columns:
            skipped.append({"predictor": predictor, "reason": "Predictor is not in the clean dataset."})
            continue
        series = dataframe[predictor]
        non_null = series.dropna()
        if non_null.nunique() < 2:
            skipped.append({"predictor": predictor, "reason": "Predictor has fewer than two observed levels."})
            continue

        design, predictor_terms, reference = _build_design_matrix(non_null)
        if design.shape[1] < 2:
            skipped.append({"predictor": predictor, "reason": "No usable predictor columns after encoding."})
            continue
        term_frame = pd.DataFrame(design[:, 1:], index=non_null.index)
        for term_index, term in enumerate(predictor_terms):
            term_name = predictor if term["kind"] == "numeric" else f"{predictor}: {term['name']}"
            column_name = f"{predictor}__{term_index}"
            column = pd.Series(np.nan, index=dataframe.index, name=column_name)
            column.loc[term_frame.index] = term_frame.iloc[:, term_index]
            columns.append(column)
            terms.append({
                "name": term_name,
                "predictor": predictor,
                "kind": term["kind"],
                "reference": term.get("reference", reference),
            })

    if not columns:
        return pd.DataFrame(index=dataframe.index), terms, skipped
    return pd.concat(columns, axis=1), terms, skipped


def _standardize_lasso_design(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    means = x.mean(axis=0)
    scales = x.std(axis=0)
    usable = np.isfinite(scales) & (scales > 1e-12)
    if not np.any(usable):
        return np.empty((x.shape[0], 0)), np.array([]), np.array([]), usable
    return (x[:, usable] - means[usable]) / scales[usable], means[usable], scales[usable], usable


def _fit_lasso_logistic_path(x_raw: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    x, means, scales, usable = _standardize_lasso_design(x_raw)
    if x.shape[1] == 0:
        raise ValueError("No predictor terms vary within the complete-case model frame.")

    penalties = _lasso_penalty_path(x, y)
    full_fits = _fit_lasso_penalty_path(x, y, penalties)
    bic_index, bic_fit = min(enumerate(full_fits), key=lambda item: item[1]["bic"])
    cv_result = _select_lasso_penalty_by_cv(x_raw[:, usable], y, penalties)

    if cv_result["status"] == "fit":
        selected_index = int(cv_result["selected_index"])
        selected_fit = full_fits[selected_index]
        return {
            **selected_fit,
            "means": means,
            "scales": scales,
            "selection_method": "cross_validation",
            "selection_rule": "lambda_1se",
            "cv_folds": cv_result["fold_count"],
            "cv_metric": "log_loss",
            "cv_mean_loss": cv_result["selected_mean_loss"],
            "cv_se_loss": cv_result["selected_se_loss"],
            "lambda_min": cv_result["lambda_min"],
            "lambda_1se": cv_result["lambda_1se"],
            "lambda_min_cv_loss": cv_result["lambda_min_cv_loss"],
            "lambda_1se_cv_loss": cv_result["lambda_1se_cv_loss"],
            "bic_penalty": float(bic_fit["penalty"]),
            "bic": float(bic_fit["bic"]),
            "selected_bic": float(selected_fit["bic"]),
            "bic_selected": selected_index == bic_index,
            "fallback_reason": None,
            "cv_path": cv_result["path"],
        }

    return {
        **bic_fit,
        "means": means,
        "scales": scales,
        "selection_method": "bic_fallback",
        "selection_rule": "bic",
        "cv_folds": 0,
        "cv_metric": "log_loss",
        "cv_mean_loss": None,
        "cv_se_loss": None,
        "lambda_min": None,
        "lambda_1se": None,
        "lambda_min_cv_loss": None,
        "lambda_1se_cv_loss": None,
        "bic_penalty": float(bic_fit["penalty"]),
        "bic": float(bic_fit["bic"]),
        "selected_bic": float(bic_fit["bic"]),
        "bic_selected": True,
        "fallback_reason": cv_result["reason"],
        "cv_path": [],
    }


def _lasso_penalty_path(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    centered = y - y.mean()
    lambda_max = float(np.max(np.abs(x.T @ centered)) / len(y)) if x.shape[1] else 0.0
    if not np.isfinite(lambda_max) or lambda_max <= 1e-8:
        return np.array([0.0])
    return np.geomspace(lambda_max, max(lambda_max * 0.02, 1e-5), 30)


def _fit_lasso_penalty_path(x: np.ndarray, y: np.ndarray, penalties: np.ndarray) -> list[dict[str, Any]]:
    event_rate = float(np.clip(y.mean(), 1e-4, 1 - 1e-4))
    intercept = math.log(event_rate / (1 - event_rate))
    beta = np.zeros(x.shape[1])
    fits = []
    for penalty in penalties:
        beta, intercept, converged = _fit_lasso_logistic(x, y, float(penalty), beta, intercept)
        probabilities = np.clip(_sigmoid(intercept + x @ beta), 1e-8, 1 - 1e-8)
        log_likelihood = float(np.sum(y * np.log(probabilities) + (1 - y) * np.log(1 - probabilities)))
        nonzero = int(np.sum(np.abs(beta) > 1e-5))
        bic = -2 * log_likelihood + (nonzero + 1) * math.log(len(y))
        fits.append({
            "beta": beta.copy(),
            "intercept": float(intercept),
            "penalty": float(penalty),
            "converged": converged,
            "log_likelihood": log_likelihood,
            "bic": float(bic),
        })

    return fits


def _select_lasso_penalty_by_cv(x_raw: np.ndarray, y: np.ndarray, penalties: np.ndarray) -> dict[str, Any]:
    class_counts = [int(np.sum(y == value)) for value in np.unique(y)]
    min_class_count = min(class_counts) if class_counts else 0
    if min_class_count < 3:
        return {
            "status": "fallback",
            "reason": "fewer than 3 complete cases in at least one outcome class",
        }

    fold_count = min(5, min_class_count)
    folds = _stratified_folds(y, fold_count)
    losses = np.full((len(penalties), fold_count), np.nan)
    for fold_index, validation_index in enumerate(folds):
        training_mask = np.ones(len(y), dtype=bool)
        training_mask[validation_index] = False
        x_train = x_raw[training_mask]
        x_validation = x_raw[validation_index]
        y_train = y[training_mask]
        y_validation = y[validation_index]
        if int(np.unique(y_train).size) != 2 or int(np.unique(y_validation).size) != 2:
            return {
                "status": "fallback",
                "reason": "stratified folds could not preserve both outcome classes",
            }

        x_train, x_validation = _standardize_lasso_fold(x_train, x_validation)
        event_rate = float(np.clip(y_train.mean(), 1e-4, 1 - 1e-4))
        intercept = math.log(event_rate / (1 - event_rate))
        beta = np.zeros(x_train.shape[1])
        for penalty_index, penalty in enumerate(penalties):
            beta, intercept, _ = _fit_lasso_logistic(x_train, y_train, float(penalty), beta, intercept)
            probabilities = _sigmoid(intercept + x_validation @ beta)
            losses[penalty_index, fold_index] = _binomial_log_loss(y_validation, probabilities)

    mean_losses = np.nanmean(losses, axis=1)
    se_losses = np.nanstd(losses, axis=1, ddof=1) / math.sqrt(fold_count)
    if np.all(np.isnan(mean_losses)):
        return {"status": "fallback", "reason": "cross-validation losses could not be estimated"}

    lambda_min_index = int(np.nanargmin(mean_losses))
    one_se_threshold = mean_losses[lambda_min_index] + se_losses[lambda_min_index]
    eligible = np.where(mean_losses <= one_se_threshold)[0]
    lambda_1se_index = int(eligible[0]) if len(eligible) else lambda_min_index

    return {
        "status": "fit",
        "fold_count": fold_count,
        "selected_index": lambda_1se_index,
        "selected_mean_loss": float(mean_losses[lambda_1se_index]),
        "selected_se_loss": float(se_losses[lambda_1se_index]),
        "lambda_min": float(penalties[lambda_min_index]),
        "lambda_1se": float(penalties[lambda_1se_index]),
        "lambda_min_cv_loss": float(mean_losses[lambda_min_index]),
        "lambda_1se_cv_loss": float(mean_losses[lambda_1se_index]),
        "path": [
            {
                "penalty": round(float(penalty), 6),
                "mean_log_loss": round(float(mean), 4),
                "se_log_loss": round(float(se), 4),
            }
            for penalty, mean, se in zip(penalties, mean_losses, se_losses, strict=True)
        ],
    }


def _stratified_folds(y: np.ndarray, fold_count: int) -> list[np.ndarray]:
    rng = np.random.default_rng(20260526)
    folds: list[list[int]] = [[] for _ in range(fold_count)]
    for value in sorted(np.unique(y).tolist()):
        indices = np.where(y == value)[0]
        rng.shuffle(indices)
        for offset, index in enumerate(indices):
            folds[offset % fold_count].append(int(index))
    return [np.array(sorted(fold), dtype=int) for fold in folds]


def _standardize_lasso_fold(x_train: np.ndarray, x_validation: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    means = x_train.mean(axis=0)
    scales = x_train.std(axis=0)
    scales = np.where(np.isfinite(scales) & (scales > 1e-12), scales, 1.0)
    return (x_train - means) / scales, (x_validation - means) / scales


def _binomial_log_loss(y: np.ndarray, probabilities: np.ndarray) -> float:
    probabilities = np.clip(probabilities, 1e-8, 1 - 1e-8)
    return float(-np.mean(y * np.log(probabilities) + (1 - y) * np.log(1 - probabilities)))


def _fit_lasso_logistic(
    x: np.ndarray,
    y: np.ndarray,
    penalty: float,
    beta: np.ndarray,
    intercept: float,
) -> tuple[np.ndarray, float, bool]:
    augmented = np.column_stack([np.ones(len(y)), x])
    lipschitz = 0.25 * (np.linalg.norm(augmented, ord=2) ** 2) / len(y) + 1e-6
    step = 1 / lipschitz

    for _ in range(1000):
        probabilities = _sigmoid(intercept + x @ beta)
        residual = probabilities - y
        intercept_next = intercept - step * float(residual.mean())
        beta_next = _soft_threshold(beta - step * (x.T @ residual / len(y)), step * penalty)
        if max(abs(intercept_next - intercept), float(np.max(np.abs(beta_next - beta)))) < 1e-6:
            return beta_next, intercept_next, True
        beta = beta_next
        intercept = intercept_next
    return beta, intercept, False


def _soft_threshold(values: np.ndarray, threshold: float) -> np.ndarray:
    return np.sign(values) * np.maximum(np.abs(values) - threshold, 0.0)


def _build_design_matrix(series: pd.Series) -> tuple[np.ndarray, list[dict[str, Any]], object | None]:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all() and series.nunique(dropna=True) > 2:
        values = numeric.astype(float).to_numpy()
        return np.column_stack([np.ones(len(values)), values]), [{"name": series.name or "predictor", "kind": "numeric"}], None

    binary = series.map(_normalize_binary_label)
    binary_levels = sorted(binary.dropna().unique().tolist(), key=str)
    if binary.notna().all() and len(binary_levels) == 2:
        reference, event = _choose_binary_levels(binary_levels)
        values = binary.map({reference: 0, event: 1}).astype(float).to_numpy()
        return (
            np.column_stack([np.ones(len(values)), values]),
            [{"name": str(event), "kind": "indicator", "reference": str(reference)}],
            str(reference),
        )

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


def _logistic_standard_errors(x: np.ndarray, beta: np.ndarray) -> np.ndarray | None:
    probabilities = np.clip(_sigmoid(x @ beta), 1e-8, 1 - 1e-8)
    weights = probabilities * (1 - probabilities)
    information = x.T @ (weights[:, None] * x)
    try:
        variance = np.linalg.inv(information)
    except np.linalg.LinAlgError:
        variance = np.linalg.pinv(information)
    diagonal = np.diag(variance)
    if np.any(diagonal < 0):
        return None
    return np.sqrt(diagonal)


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
    leading_token = normalized.replace("–", "-").replace("—", "-").split(maxsplit=1)[0].strip(":-;,.")
    if leading_token in {"true", "yes", "y"}:
        return "yes"
    if leading_token in {"false", "no", "n"}:
        return "no"
    return normalized
