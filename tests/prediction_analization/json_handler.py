

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import DailyPredictionTestResult, PredictionSummaryResult

ALL_PREDICTIONS_FILENAME = "AllPredictionTestsData.json"
SUMMARY_FILENAME = "SummaryTestsData.json"
BEST_MODEL_FILENAME = "BestModelData.json"
NOT_IN_TESTS_FILENAME = "NotInTests.json"


class JsonHandlerError(ValueError):
	"""Base error for invalid prediction-analysis documents."""


def _empty_document(metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
	return {"metadata": dict(metadata or {}), "results": {}}


def _require_document(document: Any, document_name: str) -> dict[str, Any]:
	if not isinstance(document, dict):
		raise JsonHandlerError(f"{document_name} must contain a JSON object")
	if not isinstance(document.get("metadata", {}), dict):
		raise JsonHandlerError(f"{document_name}.metadata must be an object")
	if not isinstance(document.get("results", {}), dict):
		raise JsonHandlerError(f"{document_name}.results must be an object")
	return document


def load_json(path: str | Path, document_name: str = "JSON document") -> dict[str, Any]:
	"""Load a document, returning an empty document when the file is absent."""
	file_path = Path(path)
	if not file_path.exists():
		return _empty_document()
	try:
		with file_path.open("r", encoding="utf-8") as file:
			document = json.load(file)
	except json.JSONDecodeError as exc:
		raise JsonHandlerError(f"Invalid JSON in {file_path}: {exc}") from exc
	return _require_document(document, document_name)


def write_json_atomic(
	path: str | Path,
	document: Mapping[str, Any],
) -> None:
	"""Write valid JSON beside the target and replace the target atomically."""
	file_path = Path(path)
	file_path.parent.mkdir(parents=True, exist_ok=True)
	validated = _require_document(dict(document), file_path.name)
	serialized = json.dumps(
		validated,
		ensure_ascii=False,
		indent=2,
		sort_keys=False,
		allow_nan=False,
	)
	temporary_path: str | None = None
	try:
		with tempfile.NamedTemporaryFile(
			mode="w",
			encoding="utf-8",
			dir=file_path.parent,
			prefix=f".{file_path.name}.",
			suffix=".tmp",
			delete=False,
		) as temporary_file:
			temporary_path = temporary_file.name
			temporary_file.write(serialized)
			temporary_file.flush()
			os.fsync(temporary_file.fileno())
		os.replace(temporary_path, file_path)
	finally:
		if temporary_path is not None and os.path.exists(temporary_path):
			os.unlink(temporary_path)


def _pair_key(base_currency: str, target_currency: str) -> str:
	return f"{base_currency}/{target_currency}"


def _copy_result_tree(document: Mapping[str, Any]) -> dict[str, Any]:
	return {
		"metadata": dict(document.get("metadata", {})),
		"results": {
			str(pair): {
				str(model): {
					str(window): dict(days)
					for window, days in windows.items()
				}
				for model, windows in models.items()
			}
			for pair, models in document.get("results", {}).items()
		},
	}


def merge_prediction_results(
	existing: Mapping[str, Any],
	new_results: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Any]]]],
	metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
	"""Merge daily results by pair, model, and window.

	A supplied window replaces the complete old window, preventing stale daily
	rows when actual observations changed.
	"""
	document = _copy_result_tree(_require_document(existing, "prediction document"))
	if metadata is not None:
		document["metadata"] = dict(metadata)
	for pair, models in new_results.items():
		for model, windows in models.items():
			for window_id, daily_results in windows.items():
				window = document["results"].setdefault(pair, {}).setdefault(model, {})
				if not isinstance(daily_results, Mapping):
					raise JsonHandlerError("daily result window must be an object")
				window[str(window_id)] = dict(daily_results)
	return document


def daily_results_to_tree(
	results: Iterable[DailyPredictionTestResult],
	window_id_by_result: Mapping[tuple[str, str, str], str],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
	"""Convert daily dataclasses into the nested JSON result tree."""
	tree: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
	for result in results:
		pair = _pair_key(result.base_currency, result.target_currency)
		lookup_key = (pair, result.model_name, result.date.isoformat())
		window_id = window_id_by_result.get(lookup_key)
		if window_id is None:
			raise JsonHandlerError(f"No test window found for {lookup_key}")
		window = tree.setdefault(pair, {}).setdefault(result.model_name, {}).setdefault(
			window_id, {}
		)
		date_key = result.date.isoformat()
		if date_key in window:
			raise JsonHandlerError(f"Duplicate daily result: {pair}/{result.model_name}/{window_id}/{date_key}")
		window[date_key] = result.to_dict()
	return tree


def load_daily_results(
	document: Mapping[str, Any],
) -> list[DailyPredictionTestResult]:
	"""Convert all daily prediction entries in a document to dataclasses."""
	validated = _require_document(document, "prediction document")
	results: list[DailyPredictionTestResult] = []
	for models in validated["results"].values():
		for windows in models.values():
			for days in windows.values():
				for value in days.values():
					if not isinstance(value, dict):
						raise JsonHandlerError("daily prediction result must be an object")
					try:
						results.append(
							DailyPredictionTestResult(
								date=datetime.fromisoformat(value["date"]).date(),
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
						)
					except (KeyError, TypeError, ValueError) as exc:
						raise JsonHandlerError("Invalid daily prediction result") from exc
	return results


def load_summary_results(
	document: Mapping[str, Any],
) -> list[PredictionSummaryResult]:
	"""Convert all non-derived summary entries to summary dataclasses."""
	validated = _require_document(document, "summary document")
	results: list[PredictionSummaryResult] = []
	for pair, models in validated["results"].items():
		try:
			base_currency, target_currency = pair.split("/", maxsplit=1)
		except ValueError as exc:
			raise JsonHandlerError(f"Invalid currency pair: {pair}") from exc
		for model_name, windows in models.items():
			for window_id, value in windows.items():
				if window_id == "90_days":
					continue
				if not isinstance(value, dict) or not isinstance(
					value.get("summary_metrics"), dict
				):
					raise JsonHandlerError("Invalid summary result")
				metrics = value["summary_metrics"]
				results.append(
					PredictionSummaryResult(
							base_currency=base_currency,
							target_currency=target_currency,
							model_name=model_name,
							from_date=date.fromisoformat(value["from_date"]),
							to_date=date.fromisoformat(value["to_date"]),
							mae=float(metrics["mae"]),
							median_absolute_error=float(metrics["median_absolute_error"]),
							mape=float(metrics["mape"]),
							bias=float(metrics["bias"]),
							median_bias=float(metrics["median_bias"]),
							coverage=float(metrics["coverage"]),
							mean_range_absolute_error=(
								float(metrics["mean_range_absolute_error"])
								if metrics["mean_range_absolute_error"] is not None
								else None
							),
							median_range_absolute_error=(
								float(metrics["median_range_absolute_error"])
								if metrics["median_range_absolute_error"] is not None
								else None
							),
							mean_interval_width=float(metrics["mean_interval_width"]),
						)
				)
	return results


def summary_results_to_tree(
	results: Iterable[PredictionSummaryResult],
	window_ids: Mapping[tuple[str, str, str, str], str],
	observation_counts: Mapping[tuple[str, str, str], int] | None = None,
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
	"""Convert summary dataclasses into the summary JSON result tree."""
	tree: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
	for result in results:
		pair = _pair_key(result.base_currency, result.target_currency)
		lookup_key = (
			pair,
			result.model_name,
			result.from_date.isoformat(),
			result.to_date.isoformat(),
		)
		window_id = window_ids.get(lookup_key)
		if window_id is None:
			raise JsonHandlerError(f"No summary window found for {lookup_key}")
		model_windows = tree.setdefault(pair, {}).setdefault(result.model_name, {})
		if window_id in model_windows:
			raise JsonHandlerError(f"Duplicate summary result: {pair}/{result.model_name}/{window_id}")
		result_data = result.to_dict()
		metrics = {
			key: value
			for key, value in result_data.items()
			if key not in {"base_currency", "target_currency", "model_name", "from_date", "to_date"}
		}
		model_windows[window_id] = {
			"from_date": result.from_date.isoformat(),
			"to_date": result.to_date.isoformat(),
			"observation_count": (observation_counts or {}).get(
				(pair, result.model_name, window_id),
				0,
			),
			"summary_metrics": metrics,
		}
	return tree


def rebuild_best_model_document(
	summary_document: Mapping[str, Any],
	metadata: Mapping[str, Any] | None = None,
	) -> dict[str, Any]:
	"""Build BestModelData from the available 90-day summary MAPE values."""
	validated = _require_document(summary_document, "summary document")
	by_pair: dict[str, dict[str, float]] = {}
	for pair, models in validated["results"].items():
		for model, windows in models.items():
			result = windows.get("90_days")
			mape = result.get("summary_metrics", {}).get("mape") if isinstance(result, dict) else None
			if isinstance(mape, (int, float)):
				by_pair.setdefault(pair, {})[model] = float(mape)

	global_mapes: dict[str, list[float]] = {}
	results: dict[str, Any] = {}
	for pair, model_mapes in by_pair.items():
		if not model_mapes:
			continue
		for model, mape in model_mapes.items():
			global_mapes.setdefault(model, []).append(mape)
		results[pair] = {
			"best_model": min(sorted(model_mapes), key=model_mapes.get),
			"model_mapes": dict(sorted(model_mapes.items())),
		}
	averages = {
		model: sum(mapes) / len(mapes)
		for model, mapes in sorted(global_mapes.items())
	}
	return {
		"metadata": dict(metadata or validated.get("metadata", {})),
		"global_best_model": min(sorted(averages), key=averages.get) if averages else None,
		"global_model_average_mapes": averages,
		"results": results,
	}


def has_complete_prediction_window(
	document: Mapping[str, Any],
	pair: str,
	model: str,
	window_id: str,
	expected_dates: Iterable[str] | None = None,
) -> bool:
	"""Return whether a stored window has all expected daily result keys."""
	try:
		days = document["results"][pair][model][window_id]
	except (KeyError, TypeError):
		return False
	if not isinstance(days, dict) or not days:
		return False
	return expected_dates is None or set(expected_dates).issubset(days)


def default_result_paths(results_dir: str | Path) -> dict[str, Path]:
	root = Path(results_dir)
	return {
		"predictions": root / ALL_PREDICTIONS_FILENAME,
		"summary": root / SUMMARY_FILENAME,
		"best_model": root / BEST_MODEL_FILENAME,
		"not_in_tests": root / NOT_IN_TESTS_FILENAME,
	}