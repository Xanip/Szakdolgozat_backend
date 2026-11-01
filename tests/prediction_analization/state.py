"""Load, update, aggregate, and persist prediction-analysis state."""

from __future__ import annotations

from datetime import date
from typing import Any

from .calculations import calculate_prediction_summary
from .configuration import BacktestConfig, PendingTest
from .json_handler import (
	default_result_paths,
	has_complete_prediction_window,
	load_json,
	merge_prediction_results,
	rebuild_best_model_document,
	write_json_atomic,
)
from .models import DailyPredictionTestResult, PredictionSummaryResult

BacktestState = dict[str, Any]
PredictionTree = dict[str, dict[str, dict[str, dict[str, Any]]]]
ErrorRecord = tuple[str, str, dict[str, Any]]


def load_backtest_state(config: BacktestConfig) -> BacktestState:
	paths = default_result_paths(config.results_dir)
	return {
		"metadata": config.metadata(),
		"predictions": load_json(paths["predictions"], "prediction document"),
		"summaries": load_json(paths["summary"], "summary document"),
	}


def _stored_configuration_matches(
	state: BacktestState,
	config: BacktestConfig,
) -> bool:
	stored = state["predictions"].get("metadata", {})
	stored_configuration = stored.get("test_configuration", {})
	current_configuration = config.metadata()["test_configuration"]
	return (
		stored_configuration.get("horizon") == current_configuration["horizon"]
		and stored_configuration.get("test_windows")
		== current_configuration["test_windows"]
	)


def get_pending_tests(
	state: BacktestState,
	config: BacktestConfig,
	force: bool = False,
) -> list[PendingTest]:
	"""Return only pair/window/model combinations needing prediction work."""
	refresh_configuration = force or not _stored_configuration_matches(state, config)
	predictions = state["predictions"]
	pending: list[PendingTest] = []
	for base_currency, target_currency in config.currency_pairs:
		pair = f"{base_currency}/{target_currency}"
		for window in config.test_windows:
			models = tuple(
				model
				for model in config.model_names
				if refresh_configuration
				or not has_complete_prediction_window(
					predictions, pair, model, window.id
				)
			)
			if models:
				pending.append((base_currency, target_currency, window, models))
	return pending


def update_backtest_results(
	state: BacktestState,
	new_predictions: PredictionTree,
	config: BacktestConfig,
) -> BacktestState:
	state["predictions"] = merge_prediction_results(
		state["predictions"], new_predictions, config.metadata()
	)
	return state


def _daily_result_from_dict(value: dict[str, Any]) -> DailyPredictionTestResult:
	return DailyPredictionTestResult(
		date=date.fromisoformat(value["date"]),
		base_currency=value["base_currency"],
		target_currency=value["target_currency"],
		model_name=value["model_name"],
		actual_rate=float(value["actual_rate"]),
		predicted_rate=float(value["predicted_rate"]),
		lower_bound=float(value["lower_bound"]),
		upper_bound=float(value["upper_bound"]),
		error=float(value["error"]),
		absolute_error=float(value["absolute_error"]),
		percentage_error=float(value["percentage_error"]),
		absolute_percentage_error=float(value["absolute_percentage_error"]),
		in_range=bool(value["in_range"]),
		range_error=float(value["range_error"]),
		range_absolute_error=float(value["range_absolute_error"]),
		range_percentage_error=float(value["range_percentage_error"]),
		absolute_range_percentage_error=float(value["absolute_range_percentage_error"]),
		interval_width=float(value["interval_width"]),
	)


def _summary_entry(
	summary: PredictionSummaryResult,
	observation_count: int,
) -> dict[str, Any]:
	values = summary.to_dict()
	return {
		"from_date": values["from_date"],
		"to_date": values["to_date"],
		"observation_count": observation_count,
		"summary_metrics": {
			key: value
			for key, value in values.items()
			if key not in {"base_currency", "target_currency", "model_name", "from_date", "to_date"}
		},
	}


def rebuild_summaries(
	state: BacktestState,
	config: BacktestConfig,
) -> BacktestState:
	"""Rebuild all window and 90-day summaries from prediction results."""
	summary_results: dict[str, dict[str, dict[str, Any]]] = {}
	configured_window_ids = {window.id for window in config.test_windows}
	for pair, models in state["predictions"]["results"].items():
		for model_name, windows in models.items():
			model_summaries = summary_results.setdefault(pair, {}).setdefault(
				model_name, {}
			)
			all_daily_results: list[DailyPredictionTestResult] = []
			for window_id, days in windows.items():
				if window_id not in configured_window_ids:
					continue
				daily_results = [
					_daily_result_from_dict(value) for value in days.values()
				]
				if not daily_results:
					continue
				summary = calculate_prediction_summary(daily_results)
				model_summaries[window_id] = _summary_entry(
					summary, len(daily_results)
				)
				all_daily_results.extend(daily_results)

			complete_windows = all(
				has_complete_prediction_window(
					state["predictions"], pair, model_name, window.id
				)
				for window in config.test_windows
			)
			if complete_windows and all_daily_results:
				summary = calculate_prediction_summary(all_daily_results)
				model_summaries["90_days"] = _summary_entry(
					summary, len(all_daily_results)
				)

	state["summaries"] = {
		"metadata": config.metadata(),
		"results": summary_results,
	}
	return state


def _errors_document(
	errors: list[ErrorRecord],
	metadata: dict[str, Any],
) -> dict[str, Any]:
	currency_pairs: dict[str, Any] = {}
	model_failures: dict[str, dict[str, list[dict[str, Any]]]] = {}
	for pair, model_name, error in errors:
		if model_name:
			model_failures.setdefault(pair, {}).setdefault(model_name, []).append(error)
		else:
			currency_pairs.setdefault(
				pair,
				{"status": "SKIPPED", "failed_test_windows": []},
			)["failed_test_windows"].append(error)
	return {
		"metadata": metadata,
		"currency_pairs": currency_pairs,
		"model_failures": model_failures,
	}


def save_backtest_state(
	state: BacktestState,
	config: BacktestConfig,
	errors: list[ErrorRecord],
) -> None:
	paths = default_result_paths(config.results_dir)
	write_json_atomic(paths["predictions"], state["predictions"])
	write_json_atomic(paths["summary"], state["summaries"])
	state["best_model"] = rebuild_best_model_document(
		state["summaries"], config.metadata()
	)
	state["not_in_tests"] = _errors_document(errors, config.metadata())
	write_json_atomic(paths["best_model"], state["best_model"])
	write_json_atomic(paths["not_in_tests"], state["not_in_tests"])
