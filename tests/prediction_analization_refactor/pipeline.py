"""The full backtest workflow.

1. Load the existing AllPredictionTestsData.json.
2. Decide which pair/window/model combinations are missing. Everything is
   recalculated with force=True or when horizon/test windows changed.
3. Run the missing predictions.
4. Merge them into the stored results (a recalculated window replaces the
   old window completely).
5. Rebuild every window and 90-day summary from the stored daily results.
6. Save the four JSON documents and the Markdown report.
"""

from __future__ import annotations

import logging
from typing import Any

from szakdolgozat_backend.snapshots.store import Snapshot

from .config import BacktestConfig
from .models import DailyPredictionTestResult, PredictionSummaryResult
from .prediction_runner import ErrorRecord, PendingTest, PredictionTree, execute_backtests
from .report import write_report
from .storage import (
	BEST_MODEL_FILENAME,
	NOT_IN_TESTS_FILENAME,
	PREDICTIONS_FILENAME,
	REPORT_FILENAME,
	SUMMARY_FILENAME,
	load_json,
	write_json_atomic,
)

logger = logging.getLogger(__name__)


def _has_window(document: dict[str, Any], pair: str, model: str, window_id: str) -> bool:
	"""True if the stored window contains at least one daily result."""
	try:
		days = document["results"][pair][model][window_id]
	except (KeyError, TypeError):
		return False
	return isinstance(days, dict) and bool(days)


def get_pending_tests(
	predictions: dict[str, Any],
	config: BacktestConfig,
	force: bool = False,
) -> list[PendingTest]:
	stored = predictions.get("metadata", {}).get("test_configuration", {})
	current = config.test_configuration()
	refresh_all = force or not (
		stored.get("horizon") == current["horizon"]
		and stored.get("test_windows") == current["test_windows"]
	)

	pending: list[PendingTest] = []
	for base, target in config.currency_pairs:
		pair = f"{base}/{target}"
		for window in config.test_windows:
			models = tuple(
				model
				for model in config.model_names
				if refresh_all or not _has_window(predictions, pair, model, window.id)
			)
			if models:
				pending.append((base, target, window, models))
	return pending


def merge_predictions(
	existing: dict[str, Any],
	new_predictions: PredictionTree,
	metadata: dict[str, Any],
) -> dict[str, Any]:
	document = {"metadata": metadata, "results": existing.get("results", {})}
	for pair, models in new_predictions.items():
		for model, windows in models.items():
			stored = document["results"].setdefault(pair, {}).setdefault(model, {})
			stored.update(windows)
	return document


def build_summaries(
	predictions: dict[str, Any],
	config: BacktestConfig,
	metadata: dict[str, Any],
) -> dict[str, Any]:
	"""Summaries per window, plus 90_days when every window has results."""
	window_ids = [window.id for window in config.test_windows]
	results: dict[str, dict[str, dict[str, Any]]] = {}
	for pair, models in predictions["results"].items():
		for model_name, windows in models.items():
			model_summaries = results.setdefault(pair, {}).setdefault(model_name, {})
			all_days: list[DailyPredictionTestResult] = []
			for window_id, days in windows.items():
				if window_id not in window_ids or not days:
					continue
				daily = [DailyPredictionTestResult.from_dict(day) for day in days.values()]
				summary = PredictionSummaryResult.from_daily_results(daily)
				model_summaries[window_id] = summary.to_entry(len(daily))
				all_days.extend(daily)

			if all_days and all(
				_has_window(predictions, pair, model_name, window_id)
				for window_id in window_ids
			):
				summary = PredictionSummaryResult.from_daily_results(all_days)
				model_summaries["90_days"] = summary.to_entry(len(all_days))
	return {"metadata": metadata, "results": results}


def build_best_model(summaries: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
	"""Best model per pair and globally, by 90-day MAPE (lower is better)."""
	results: dict[str, Any] = {}
	mapes_by_model: dict[str, list[float]] = {}
	for pair, models in summaries["results"].items():
		model_mapes: dict[str, float] = {}
		for model, windows in models.items():
			ninety_days = windows.get("90_days")
			if isinstance(ninety_days, dict):
				mape = ninety_days.get("summary_metrics", {}).get("mape")
				if isinstance(mape, (int, float)):
					model_mapes[model] = float(mape)
		if not model_mapes:
			continue
		for model, mape in model_mapes.items():
			mapes_by_model.setdefault(model, []).append(mape)
		results[pair] = {
			"best_model": min(sorted(model_mapes), key=model_mapes.get),
			"model_mapes": dict(sorted(model_mapes.items())),
		}

	averages = {
		model: sum(mapes) / len(mapes)
		for model, mapes in sorted(mapes_by_model.items())
	}
	return {
		"metadata": metadata,
		"global_best_model": min(sorted(averages), key=averages.get) if averages else None,
		"global_model_average_mapes": averages,
		"results": results,
	}


def build_not_in_tests(errors: list[ErrorRecord], metadata: dict[str, Any]) -> dict[str, Any]:
	"""Errors of the current run: pair-level skips and model-level failures."""
	currency_pairs: dict[str, Any] = {}
	model_failures: dict[str, dict[str, list[dict[str, Any]]]] = {}
	for pair, model_name, error in errors:
		if model_name:
			model_failures.setdefault(pair, {}).setdefault(model_name, []).append(error)
		else:
			currency_pairs.setdefault(
				pair, {"status": "SKIPPED", "failed_test_windows": []}
			)["failed_test_windows"].append(error)
	return {
		"metadata": metadata,
		"currency_pairs": currency_pairs,
		"model_failures": model_failures,
	}


def _configure_logging() -> None:
	"""Make progress visible for both Uvicorn and CLI runs."""
	if not logging.getLogger().handlers:
		logging.basicConfig(
			level=logging.INFO,
			format="%(asctime)s %(levelname)s %(name)s: %(message)s",
		)
	logging.getLogger(__package__).setLevel(logging.INFO)


def run_prediction_analysis(
	snapshot: Snapshot,
	config: BacktestConfig,
	force: bool = False,
) -> dict[str, Any]:
	"""Run pending backtests and persist every derived result document."""
	_configure_logging()
	config = config.for_snapshot(snapshot)
	config.validate()
	logger.info(
		"[PREDICTION] analysis started pairs=%d windows=%d models=%d",
		len(config.currency_pairs), len(config.test_windows), len(config.model_names),
	)
	run_metadata = config.metadata()
	results_dir = config.results_dir

	stored_predictions = load_json(results_dir / PREDICTIONS_FILENAME)
	pending_tests = get_pending_tests(stored_predictions, config, force)
	logger.info("[PREDICTION] pending test groups=%d", len(pending_tests))

	new_predictions, errors = execute_backtests(snapshot, config, pending_tests)

	metadata = config.metadata()
	predictions = merge_predictions(stored_predictions, new_predictions, metadata)
	summaries = build_summaries(predictions, config, metadata)
	best_model = build_best_model(summaries, metadata)
	not_in_tests = build_not_in_tests(errors, metadata)

	write_json_atomic(results_dir / PREDICTIONS_FILENAME, predictions)
	write_json_atomic(results_dir / SUMMARY_FILENAME, summaries)
	write_json_atomic(results_dir / BEST_MODEL_FILENAME, best_model)
	write_json_atomic(results_dir / NOT_IN_TESTS_FILENAME, not_in_tests)
	report_path = write_report(summaries, best_model, results_dir / REPORT_FILENAME)

	successful_windows = sum(
		len(windows) for models in new_predictions.values() for windows in models.values()
	)
	logger.info(
		"[PREDICTION] analysis finished successful_windows=%d errors=%d report=%s",
		successful_windows, len(errors), report_path,
	)
	return {
		"metadata": run_metadata,
		"predictions": predictions,
		"summaries": summaries,
		"best_model": best_model,
		"not_in_tests": not_in_tests,
	}
