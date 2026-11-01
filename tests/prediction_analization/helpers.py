"""History preparation, prediction validation, and eligibility helpers."""

from datetime import date, timedelta
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
import pandas as pd

from szakdolgozat_backend.services.predictionServices import PREDICTORS
from szakdolgozat_backend.services.predictionServices import get_prediction_history
from szakdolgozat_backend.snapshots.store import Snapshot

from .models import PredictionTestError

MIN_REFERENCE_OBSERVATIONS = 5
MIN_HISTORY_OBSERVATIONS = 30
REQUIRED_TEST_WINDOWS = 3
PREDICTION_COLUMNS = frozenset(
	{
		"Date",
		"PredictedRate",
		"LowerBound",
		"UpperBound",
	}
)


def _normalise_rate_dates(rates: pd.DataFrame) -> pd.DataFrame:
	result = rates.copy()
	result["Date"] = pd.to_datetime(
		result["Date"], errors="coerce"
	).dt.normalize()
	result["Rate"] = pd.to_numeric(result["Rate"], errors="coerce")
	return (
		result.sort_values("Date", na_position="last")
		.reset_index(drop=True)
	)


def _prediction_error(
	model_name: str | None,
	base_currency: str,
	target_currency: str,
	reference_start: date,
	reference_end: date,
	status: str,
	message: str,
) -> PredictionTestError:
	return PredictionTestError(
		model_name=model_name,
		base_currency=base_currency,
		target_currency=target_currency,
		reference_from_date=reference_start,
		reference_to_date=reference_end,
		status=status,
		message=message,
	)


def _validate_actual_window(
	rates: pd.DataFrame,
	base_currency: str,
	target_currency: str,
	window_start: date,
	window_end: date,
	status: str,
) -> tuple[pd.DataFrame, PredictionTestError | None]:
	invalid_dates = rates["Date"].isna()
	invalid_rates = (
		rates["Rate"].isna()
		| ~np.isfinite(rates["Rate"])
		| rates["Rate"].eq(0)
	)
	if invalid_dates.any() or invalid_rates.any():
		return rates.iloc[0:0].copy(), _prediction_error(
			None,
			base_currency,
			target_currency,
			window_start,
			window_end,
			status,
			"Actual data contains missing, zero, NaN, or infinite values.",
		)

	return (
		rates.sort_values("Date")
		.drop_duplicates(subset=["Date"], keep="last")
		.reset_index(drop=True),
		None,
	)


def _get_rate_window(
	snapshot: Snapshot,
	base_currency: str,
	target_currency: str,
	from_date: date | None = None,
	to_date: date | None = None,
) -> pd.DataFrame:
	rates = _normalise_rate_dates(
		get_prediction_history(
			snapshot,
			base_currency,
			target_currency,
		)
	)

	if from_date is not None:
		rates = rates.loc[rates["Date"] >= pd.Timestamp(from_date)]
	if to_date is not None:
		rates = rates.loc[rates["Date"] <= pd.Timestamp(to_date)]

	return rates.reset_index(drop=True)


def _validate_prediction(
	prediction: pd.DataFrame,
	reference: pd.DataFrame,
	model_name: str,
	base_currency: str,
	target_currency: str,
	reference_start: date,
	reference_end: date,
) -> tuple[pd.DataFrame | None, PredictionTestError | None]:
	if prediction.empty:
		return None, _prediction_error(
			model_name,
			base_currency,
			target_currency,
			reference_start,
			reference_end,
			"EMPTY_PREDICTION",
			"The predictor returned an empty DataFrame.",
		)

	missing_columns = sorted(PREDICTION_COLUMNS - set(prediction.columns))
	if missing_columns:
		return None, _prediction_error(
			model_name,
			base_currency,
			target_currency,
			reference_start,
			reference_end,
			"MISSING_COLUMNS",
			f"Missing prediction columns: {missing_columns}",
		)

	result = prediction.copy()
	result["Date"] = pd.to_datetime(
		result["Date"], errors="coerce"
	).dt.normalize()
	if result["Date"].isna().any():
		return None, _prediction_error(
			model_name,
			base_currency,
			target_currency,
			reference_start,
			reference_end,
			"INVALID_PREDICTION_DATE",
			"The prediction contains an invalid date.",
		)

	if result["Date"].duplicated().any():
		return None, _prediction_error(
			model_name,
			base_currency,
			target_currency,
			reference_start,
			reference_end,
			"DUPLICATE_PREDICTION_DATES",
			"The prediction contains duplicate dates.",
		)

	if result["Date"].gt(pd.Timestamp(reference_end)).any():
		return None, _prediction_error(
			model_name,
			base_currency,
			target_currency,
			reference_start,
			reference_end,
			"PREDICTION_DATE_OUT_OF_RANGE",
			"The prediction contains dates outside the reference period.",
		)

	result = result.loc[
		result["Date"] >= pd.Timestamp(reference_start)
	].copy()
	if result.empty:
		return None, _prediction_error(
			model_name,
			base_currency,
			target_currency,
			reference_start,
			reference_end,
			"NO_PREDICTIONS_IN_REFERENCE_PERIOD",
			"The prediction has no dates in the reference period.",
		)

	for column in PREDICTION_COLUMNS - {"Date"}:
		result[column] = pd.to_numeric(result[column], errors="coerce")
	numeric_columns = list(PREDICTION_COLUMNS - {"Date"})
	if result[numeric_columns].isna().any().any() or not np.isfinite(
		result[numeric_columns].to_numpy()
	).all():
		return None, _prediction_error(
			model_name,
			base_currency,
			target_currency,
			reference_start,
			reference_end,
			"INVALID_PREDICTION_VALUE",
			"The prediction contains a non-numeric or missing rate value.",
		)

	if (result["LowerBound"] > result["UpperBound"]).any():
		return None, _prediction_error(
			model_name,
			base_currency,
			target_currency,
			reference_start,
			reference_end,
			"INVALID_PREDICTION_INTERVAL",
			"A prediction lower bound is greater than its upper bound.",
		)

	if not set(reference["Date"]).intersection(result["Date"]):
		return None, _prediction_error(
			model_name,
			base_currency,
			target_currency,
			reference_start,
			reference_end,
			"NO_DATE_OVERLAP",
			"The prediction has no dates matching actual reference observations.",
		)

	actual_values = reference[["Date", "Rate"]].rename(
		columns={"Rate": "ActualRate"}
	)
	result = result.merge(
		actual_values,
		on="Date",
		how="inner",
		validate="one_to_one",
	)
	if len(result) < MIN_REFERENCE_OBSERVATIONS:
		return None, _prediction_error(
			model_name,
			base_currency,
			target_currency,
			reference_start,
			reference_end,
			"INSUFFICIENT_MATCHED_OBSERVATIONS",
			(
				f"Only {len(result)} actual-prediction matches are available; "
				f"minimum is {MIN_REFERENCE_OBSERVATIONS}."
			),
		)

	return result.sort_values("Date").reset_index(drop=True), None


def prepare_prediction_test_data(
	snapshot: Snapshot,
	currency_pairs: list[tuple[str, str]],
	reference_start_dates: list[date],
	horizon: int = 30,
	model_names: Iterable[str] | None = None,
	progress_callback: Callable[[str, str], None] | None = None,
) -> list[dict[str, Any]]:
	"""Prepare level-0 data for all pairs and fixed reference windows."""
	if horizon <= 0:
		raise ValueError("horizon must be greater than zero")
	selected_models = list(model_names) if model_names is not None else list(PREDICTORS)
	unknown_models = set(selected_models) - set(PREDICTORS)
	if unknown_models:
		raise ValueError(f"Unknown prediction models: {sorted(unknown_models)}")

	test_cases: list[dict[str, Any]] = []

	for base_currency, target_currency in currency_pairs:
		for reference_start in reference_start_dates:
			reference_end = reference_start + timedelta(days=horizon - 1)
			history_end = reference_start - timedelta(days=1)
			history = _get_rate_window(
				snapshot,
				base_currency,
				target_currency,
				to_date=history_end,
			)
			reference = _get_rate_window(
				snapshot,
				base_currency,
				target_currency,
				from_date=reference_start,
				to_date=reference_end,
			)

			predictions: dict[str, pd.DataFrame] = {}
			prediction_errors: list[PredictionTestError] = []
			prediction_coverage: dict[str, int] = {
				model_name: 0 for model_name in selected_models
			}
			history, history_error = _validate_actual_window(
				history,
				base_currency,
				target_currency,
				reference_start,
				reference_end,
				"INVALID_HISTORY_DATA",
			)
			reference, reference_error = _validate_actual_window(
				reference,
				base_currency,
				target_currency,
				reference_start,
				reference_end,
				"INVALID_ACTUAL_DATA",
			)
			history_observation_count = len(history)
			reference_observation_count = len(reference)

			if history_error is not None:
				test_status = history_error.status
				prediction_errors.append(history_error)
			elif history_observation_count < MIN_HISTORY_OBSERVATIONS:
				test_status = "INSUFFICIENT_HISTORY"
				prediction_errors.append(
					_prediction_error(
						None,
						base_currency,
						target_currency,
						reference_start,
						reference_end,
						test_status,
						(
							f"History contains {history_observation_count} observations; "
							f"minimum is {MIN_HISTORY_OBSERVATIONS}."
						),
					)
				)
			elif reference_error is not None:
				test_status = reference_error.status
				prediction_errors.append(reference_error)
			elif reference_observation_count < MIN_REFERENCE_OBSERVATIONS:
				test_status = "INSUFFICIENT_ACTUAL_OBSERVATIONS"
				prediction_errors.append(
					_prediction_error(
						None,
						base_currency,
						target_currency,
						reference_start,
						reference_end,
						test_status,
						(
							f"Reference period contains {reference_observation_count} "
							f"actual observations; minimum is "
							f"{MIN_REFERENCE_OBSERVATIONS}."
						),
					)
				)
			else:
				test_status = "READY"

			if test_status == "READY":
				for model_name in selected_models:
					predictor = PREDICTORS[model_name]
					if not callable(predictor):
						if progress_callback is not None:
							progress_callback(model_name, "failed")
						prediction_errors.append(
							_prediction_error(
								model_name,
								base_currency,
								target_currency,
								reference_start,
								reference_end,
								"NON_CALLABLE_PREDICTOR",
								"Registered predictor is not callable.",
							)
						)
						continue

					if progress_callback is not None:
						progress_callback(model_name, "started")

					try:
						prediction_kwargs = {"horizon": horizon}

						if model_name == "PROPHET":
							prediction_kwargs["validate_freshness"] = False

						prediction = predictor(
							history.copy(),
							**prediction_kwargs,
						)
						validated_prediction, validation_error = _validate_prediction(
							prediction,
							reference,
							model_name,
							base_currency,
							target_currency,
							reference_start,
							reference_end,
						)
						if validation_error is not None:
							if progress_callback is not None:
								progress_callback(model_name, "failed")
							prediction_errors.append(validation_error)
						else:
							if progress_callback is not None:
								progress_callback(model_name, "completed")
							predictions[model_name] = validated_prediction
							prediction_coverage[model_name] = len(
								validated_prediction
							)
					except Exception as exc:
						if progress_callback is not None:
							progress_callback(model_name, "failed")
						prediction_errors.append(
							_prediction_error(
								model_name,
								base_currency,
								target_currency,
								reference_start,
								reference_end,
								"PREDICTOR_EXCEPTION",
								str(exc),
							)
						)

			test_cases.append(
				{
					"base_currency": base_currency,
					"target_currency": target_currency,
					"history_from_date": (
						history["Date"].min().date()
						if not history.empty
						else None
					),
					"history_to_date": history_end,
					"history_observation_count": history_observation_count,
					"reference_from_date": reference_start,
					"reference_to_date": reference_end,
					"reference_observation_count": reference_observation_count,
					"status": test_status,
					"reference": reference,
					"predictions": predictions,
					"prediction_coverage": prediction_coverage,
					"prediction_errors": prediction_errors,
				}
			)

	return test_cases


def is_currency_pair_eligible_for_analysis(
	test_cases: list[dict[str, Any]],
	required_windows: int = REQUIRED_TEST_WINDOWS,
) -> bool:
	if len(test_cases) != required_windows:
		return False

	return all(test_case["status"] == "READY" for test_case in test_cases)


def is_model_eligible_for_90_day_summary(
	test_cases: list[dict[str, Any]],
	model_name: str,
	required_windows: int = REQUIRED_TEST_WINDOWS,
) -> bool:
	if not is_currency_pair_eligible_for_analysis(test_cases, required_windows):
		return False

	return all(
		model_name in test_case["predictions"]
		and test_case["prediction_coverage"].get(model_name, 0)
		>= MIN_REFERENCE_OBSERVATIONS
		for test_case in test_cases
	)