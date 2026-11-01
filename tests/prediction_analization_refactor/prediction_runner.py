"""Run predictors on truncated history and turn them into daily results.

For one currency pair and one test window:
1. history   = every actual rate before the window start,
   reference = the actual rates inside the window,
2. both are validated (no NaN/zero/infinite values, enough observations),
3. each model predicts from the history,
4. the prediction is validated and matched with the reference by date,
5. every matched day becomes a DailyPredictionTestResult.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from szakdolgozat_backend.services.predictionServices import (
	PREDICTORS,
	get_prediction_history,
)
from szakdolgozat_backend.snapshots.store import Snapshot

from .config import (
	MIN_HISTORY_OBSERVATIONS,
	MIN_REFERENCE_OBSERVATIONS,
	BacktestConfig,
	TestWindow,
)
from .models import DailyPredictionTestResult, PredictionTestError

logger = logging.getLogger(__name__)

PREDICTION_COLUMNS = frozenset({"Date", "PredictedRate", "LowerBound", "UpperBound"})
NUMERIC_COLUMNS = list(PREDICTION_COLUMNS - {"Date"})

# pair -> model -> window id -> date -> daily result dict
PredictionTree = dict[str, dict[str, dict[str, dict[str, Any]]]]
# (pair, model name or "" for pair-level errors, error data)
ErrorRecord = tuple[str, str, dict[str, Any]]
# (base, target, window, models still to run)
PendingTest = tuple[str, str, TestWindow, tuple[str, ...]]
ProgressCallback = Callable[[str, str], None]


class _TestFailure(Exception):
	def __init__(self, status: str, message: str) -> None:
		super().__init__(message)
		self.status = status
		self.message = message


def _load_rates(snapshot: Snapshot, base: str, target: str) -> pd.DataFrame:
	rates = get_prediction_history(snapshot, base, target).copy()
	rates["Date"] = pd.to_datetime(rates["Date"], errors="coerce").dt.normalize()
	rates["Rate"] = pd.to_numeric(rates["Rate"], errors="coerce")
	return rates.sort_values("Date", na_position="last").reset_index(drop=True)


def _clean_actual(rates: pd.DataFrame) -> pd.DataFrame | None:
	"""Return deduplicated rates, or None if any value is unusable."""
	invalid = (
		rates["Date"].isna()
		| rates["Rate"].isna()
		| ~np.isfinite(rates["Rate"])
		| rates["Rate"].eq(0)
	)
	if invalid.any():
		return None
	return (
		rates.sort_values("Date")
		.drop_duplicates(subset=["Date"], keep="last")
		.reset_index(drop=True)
	)


def _validate_prediction(
	prediction: pd.DataFrame,
	reference: pd.DataFrame,
	reference_start: date,
	reference_end: date,
) -> pd.DataFrame:
	"""Return the prediction joined with ActualRate, or raise _TestFailure."""
	if prediction.empty:
		raise _TestFailure("EMPTY_PREDICTION", "The predictor returned an empty DataFrame.")

	missing_columns = sorted(PREDICTION_COLUMNS - set(prediction.columns))
	if missing_columns:
		raise _TestFailure("MISSING_COLUMNS", f"Missing prediction columns: {missing_columns}")

	result = prediction.copy()
	result["Date"] = pd.to_datetime(result["Date"], errors="coerce").dt.normalize()
	if result["Date"].isna().any():
		raise _TestFailure("INVALID_PREDICTION_DATE", "The prediction contains an invalid date.")
	if result["Date"].duplicated().any():
		raise _TestFailure("DUPLICATE_PREDICTION_DATES", "The prediction contains duplicate dates.")
	if result["Date"].gt(pd.Timestamp(reference_end)).any():
		raise _TestFailure(
			"PREDICTION_DATE_OUT_OF_RANGE",
			"The prediction contains dates outside the reference period.",
		)

	result = result.loc[result["Date"] >= pd.Timestamp(reference_start)].copy()
	if result.empty:
		raise _TestFailure(
			"NO_PREDICTIONS_IN_REFERENCE_PERIOD",
			"The prediction has no dates in the reference period.",
		)

	for column in NUMERIC_COLUMNS:
		result[column] = pd.to_numeric(result[column], errors="coerce")
	values = result[NUMERIC_COLUMNS]
	if values.isna().any().any() or not np.isfinite(values.to_numpy()).all():
		raise _TestFailure(
			"INVALID_PREDICTION_VALUE",
			"The prediction contains a non-numeric or missing rate value.",
		)
	if (result["LowerBound"] > result["UpperBound"]).any():
		raise _TestFailure(
			"INVALID_PREDICTION_INTERVAL",
			"A prediction lower bound is greater than its upper bound.",
		)
	if not set(reference["Date"]).intersection(result["Date"]):
		raise _TestFailure(
			"NO_DATE_OVERLAP",
			"The prediction has no dates matching actual reference observations.",
		)

	actual_values = reference[["Date", "Rate"]].rename(columns={"Rate": "ActualRate"})
	result = result.merge(actual_values, on="Date", how="inner", validate="one_to_one")
	if len(result) < MIN_REFERENCE_OBSERVATIONS:
		raise _TestFailure(
			"INSUFFICIENT_MATCHED_OBSERVATIONS",
			(
				f"Only {len(result)} actual-prediction matches are available; "
				f"minimum is {MIN_REFERENCE_OBSERVATIONS}."
			),
		)
	return result.sort_values("Date").reset_index(drop=True)


def _check_actual_data(
	history: pd.DataFrame | None,
	reference: pd.DataFrame | None,
) -> _TestFailure | None:
	"""Pair-level checks, in the order they are reported."""
	if history is None:
		return _TestFailure(
			"INVALID_HISTORY_DATA",
			"Actual data contains missing, zero, NaN, or infinite values.",
		)
	if len(history) < MIN_HISTORY_OBSERVATIONS:
		return _TestFailure(
			"INSUFFICIENT_HISTORY",
			(
				f"History contains {len(history)} observations; "
				f"minimum is {MIN_HISTORY_OBSERVATIONS}."
			),
		)
	if reference is None:
		return _TestFailure(
			"INVALID_ACTUAL_DATA",
			"Actual data contains missing, zero, NaN, or infinite values.",
		)
	if len(reference) < MIN_REFERENCE_OBSERVATIONS:
		return _TestFailure(
			"INSUFFICIENT_ACTUAL_OBSERVATIONS",
			(
				f"Reference period contains {len(reference)} "
				f"actual observations; minimum is "
				f"{MIN_REFERENCE_OBSERVATIONS}."
			),
		)
	return None


def run_test_case(
	snapshot: Snapshot,
	base: str,
	target: str,
	reference_start: date,
	horizon: int,
	model_names: tuple[str, ...],
	progress: ProgressCallback,
) -> tuple[bool, dict[str, pd.DataFrame], list[PredictionTestError]]:
	"""Run every model for one pair and window.

	Returns (pair data was usable, validated predictions by model, errors).
	"""
	reference_end = reference_start + timedelta(days=horizon - 1)

	def make_error(model_name: str | None, status: str, message: str) -> PredictionTestError:
		return PredictionTestError(
			model_name, base, target, reference_start, reference_end, status, message
		)

	rates = _load_rates(snapshot, base, target)
	history = _clean_actual(
		rates.loc[rates["Date"] <= pd.Timestamp(reference_start - timedelta(days=1))]
		.reset_index(drop=True)
	)
	reference = _clean_actual(
		rates.loc[
			(rates["Date"] >= pd.Timestamp(reference_start))
			& (rates["Date"] <= pd.Timestamp(reference_end))
		].reset_index(drop=True)
	)

	failure = _check_actual_data(history, reference)
	if failure is not None:
		return False, {}, [make_error(None, failure.status, failure.message)]

	predictions: dict[str, pd.DataFrame] = {}
	errors: list[PredictionTestError] = []
	for model_name in model_names:
		predictor = PREDICTORS[model_name]
		if not callable(predictor):
			progress(model_name, "failed")
			errors.append(make_error(
				model_name, "NON_CALLABLE_PREDICTOR", "Registered predictor is not callable."
			))
			continue

		progress(model_name, "started")
		try:
			kwargs: dict[str, Any] = {"horizon": horizon}
			if model_name == "PROPHET":
				kwargs["validate_freshness"] = False
			prediction = predictor(history.copy(), **kwargs)
			predictions[model_name] = _validate_prediction(
				prediction, reference, reference_start, reference_end
			)
			progress(model_name, "completed")
		except _TestFailure as failure:
			progress(model_name, "failed")
			errors.append(make_error(model_name, failure.status, failure.message))
		except Exception as exc:
			predictions.pop(model_name, None)
			progress(model_name, "failed")
			errors.append(make_error(model_name, "PREDICTOR_EXCEPTION", str(exc)))
	return True, predictions, errors


def _daily_results(
	prediction: pd.DataFrame,
	base: str,
	target: str,
	model_name: str,
) -> dict[str, dict[str, Any]]:
	results = (
		DailyPredictionTestResult.from_values(
			date=row.Date.date(),
			base_currency=base,
			target_currency=target,
			model_name=model_name,
			actual_rate=float(row.ActualRate),
			predicted_rate=float(row.PredictedRate),
			lower_bound=float(row.LowerBound),
			upper_bound=float(row.UpperBound),
		)
		for row in prediction.itertuples()
	)
	return {result.date.isoformat(): result.to_dict() for result in results}


def execute_backtests(
	snapshot: Snapshot,
	config: BacktestConfig,
	pending_tests: list[PendingTest],
) -> tuple[PredictionTree, list[ErrorRecord]]:
	"""Run predictors only for the pending pair/window/model work."""
	new_predictions: PredictionTree = {}
	errors: list[ErrorRecord] = []
	total = sum(len(models) for *_, models in pending_tests)
	completed = 0
	logger.info("[PREDICTION] analysis queue: total=%d pending model runs", total)

	for base, target, window, models in pending_tests:
		pair = f"{base}/{target}"
		started_at: dict[str, float] = {}

		def log_progress(model_name: str, status: str) -> None:
			nonlocal completed
			if status == "started":
				started_at[model_name] = perf_counter()
				logger.info(
					"[PREDICTION] %d/%d started pair=%s window=%s model=%s",
					completed + 1, total, pair, window.id, model_name,
				)
				return
			completed += 1
			logger.info(
				"[PREDICTION] %d/%d %s pair=%s window=%s model=%s duration=%.2fs",
				completed, total, status, pair, window.id, model_name,
				perf_counter() - started_at.get(model_name, perf_counter()),
			)

		ready, predictions, case_errors = run_test_case(
			snapshot, base, target, window.from_date, config.horizon, models, log_progress
		)
		if not ready:
			for model_name in models:
				log_progress(model_name, "skipped")

		for error in case_errors:
			errors.append((pair, error.model_name or "", error.to_dict() | {
				"window_id": window.id,
				"from_date": window.from_date.isoformat(),
				"to_date": window.to_date.isoformat(),
			}))

		for model_name, prediction in predictions.items():
			new_predictions.setdefault(pair, {}).setdefault(model_name, {})[window.id] = (
				_daily_results(prediction, base, target, model_name)
			)
	return new_predictions, errors
