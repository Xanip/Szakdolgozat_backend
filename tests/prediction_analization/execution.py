"""Execute pending prediction backtests."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from szakdolgozat_backend.snapshots.store import Snapshot

from .calculations import calculate_daily_result
from .configuration import BacktestConfig, PendingTest
from .helpers import prepare_prediction_test_data


PredictionTree = dict[str, dict[str, dict[str, dict[str, Any]]]]
ErrorRecord = tuple[str, str, dict[str, Any]]
logger = logging.getLogger(__name__)


def execute_backtests(
	snapshot: Snapshot,
	config: BacktestConfig,
	pending_tests: list[PendingTest],
) -> tuple[PredictionTree, list[ErrorRecord]]:
	"""Execute predictors only for the pending pair/window/model work."""
	new_predictions: PredictionTree = {}
	errors: list[ErrorRecord] = []
	total_predictions = sum(len(models) for *_, models in pending_tests)
	completed_predictions = 0

	logger.info(
		"[PREDICTION] analysis queue: total=%d pending model runs",
		total_predictions,
	)

	for base_currency, target_currency, window, models in pending_tests:
		pair = f"{base_currency}/{target_currency}"
		model_started_at: dict[str, float] = {}

		def log_progress(model_name: str, status: str) -> None:
			nonlocal completed_predictions
			if status == "started":
				model_started_at[model_name] = perf_counter()
				logger.info(
					"[PREDICTION] %d/%d started pair=%s window=%s model=%s",
					completed_predictions + 1,
					total_predictions,
					pair,
					window.id,
					model_name,
				)
				return

			completed_predictions += 1
			logger.info(
				"[PREDICTION] %d/%d %s pair=%s window=%s model=%s duration=%.2fs",
				completed_predictions,
				total_predictions,
				status,
				pair,
				window.id,
				model_name,
				perf_counter() - model_started_at.get(model_name, perf_counter()),
			)

		test_case = prepare_prediction_test_data(
			snapshot,
			[(base_currency, target_currency)],
			[window.from_date],
			horizon=config.horizon,
			model_names=models,
			progress_callback=log_progress,
		)[0]

		if test_case["status"] != "READY":
			for model_name in models:
				log_progress(model_name, "skipped")
		for error in test_case["prediction_errors"]:
			error_data = error.to_dict() | {
				"window_id": window.id,
				"from_date": window.from_date.isoformat(),
				"to_date": window.to_date.isoformat(),
			}
			errors.append((pair, error.model_name or "", error_data))

		for model_name, prediction in test_case["predictions"].items():
			daily_results = [
				calculate_daily_result(
					date=row.Date.date(),
					base_currency=base_currency,
					target_currency=target_currency,
					model_name=model_name,
					actual_rate=float(row.ActualRate),
					predicted_rate=float(row.PredictedRate),
					lower_bound=float(row.LowerBound),
					upper_bound=float(row.UpperBound),
				)
				for row in prediction.itertuples()
			]
			new_predictions.setdefault(pair, {}).setdefault(model_name, {})[
				window.id
			] = {result.date.isoformat(): result.to_dict() for result in daily_results}
	return new_predictions, errors
