"""Markdown report from SummaryTestsData and BestModelData.

The pipeline calls write_report() with the in-memory documents. The module
can also be run on its own to regenerate the report from existing JSON files:

	python -m tests.prediction_analization_refactor.report
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .config import RESULTS_DIR
from .storage import (
	BEST_MODEL_FILENAME,
	REPORT_FILENAME,
	SUMMARY_FILENAME,
	JsonDocumentError,
	load_json,
)

# (JSON key, label, unit, meaning)
SUMMARY_METRICS: tuple[tuple[str, str, str, str], ...] = (
	("mae", "MAE", "rate", "A napi abszolút hibák átlaga."),
	("median_absolute_error", "Median absolute error", "rate", "A napi abszolút hibák mediánja."),
	("mape", "MAPE", "percent", "Az abszolút százalékos hibák átlaga; a kisebb érték pontosabb modellt jelez."),
	("bias", "Bias", "rate", "Az előjeles hibák átlaga; pozitív érték túlbecslést, negatív érték alulbecslést jelez."),
	("median_bias", "Median bias", "rate", "Az előjeles hibák mediánja; az előrejelzések tipikus irányú eltérését mutatja."),
	("coverage", "Coverage", "percent", "A tényleges értékek százalékos aránya, amely a predikciós intervallumba esett."),
	("mean_range_absolute_error", "Mean range absolute error", "rate", "A predikciós intervallumon kívül eső értékek átlagos abszolút távolsága."),
	("median_range_absolute_error", "Median range absolute error", "rate", "A predikciós intervallumon kívül eső értékek abszolút távolságának mediánja."),
	("mean_interval_width", "Mean interval width", "rate", "A predikciós intervallum alsó és felső határa közötti átlagos szélesség."),
)


def _format_value(value: Any, unit: str) -> str:
	if value is None:
		return "—"
	if unit == "percent":
		return f"{float(value):.2f}%"
	return f"{float(value):.6f}"


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
	def line(cells: list[str]) -> str:
		return "| " + " | ".join(cells) + " |"

	escaped = ([cell.replace("|", "\\|").replace("\n", " ") for cell in row] for row in rows)
	return [line(headers), line(["---"] * len(headers)), *map(line, escaped)]


def _metadata_lines(metadata: dict[str, Any]) -> list[str]:
	configuration = metadata.get("test_configuration", {})
	models = ", ".join(f"`{model}`" for model in metadata.get("models", [])) or "—"
	rows = [
		[str(window.get(key, "—")) for key in ("id", "from_date", "to_date")]
		for window in configuration.get("test_windows", [])
	]
	return [
		"## Test configuration",
		"",
		f"- Generated at: `{metadata.get('generated_at', '—')}`",
		f"- Currency pair mode: `{metadata.get('currency_pair_mode', '—')}`",
		f"- Models: {models}",
		f"- Currency pairs: {len(metadata.get('currency_pairs', []))}",
		f"- Horizon: {configuration.get('horizon', '—')} days",
		f"- Minimum history observations: {configuration.get('minimum_history_observations', '—')}",
		f"- Minimum reference observations: {configuration.get('minimum_reference_observations', '—')}",
		"",
		"### Test windows",
		"",
		*(_table(["Window", "From", "To"], rows) if rows else ["No test windows recorded."]),
	]


def _metric_legend() -> list[str]:
	rows = [[label, meaning] for _, label, _, meaning in SUMMARY_METRICS]
	return ["## Metric legend", "", *_table(["Metric", "Meaning"], rows), ""]


def _best_model_lines(best_model: dict[str, Any]) -> list[str]:
	global_best = best_model.get("global_best_model")
	rows = [
		["1" if model == global_best else "", f"`{model}`", _format_value(mape, "percent")]
		for model, mape in sorted(
			best_model["global_model_average_mapes"].items(),
			key=lambda item: (float(item[1]), item[0]),
		)
	]
	pair_rows = []
	for pair, result in sorted(best_model["results"].items()):
		mapes = ", ".join(
			f"`{model}`: {_format_value(mape, 'percent')}"
			for model, mape in sorted(result.get("model_mapes", {}).items())
		) or "—"
		pair_rows.append([f"`{pair}`", f"`{result.get('best_model', '—')}`", mapes])
	return [
		"## Model comparison",
		"",
		f"**Global best model:** `{best_model.get('global_best_model', '—')}`",
		"",
		*_table(["Best", "Model", "Average MAPE"], rows),
		"",
		"### Best model by currency pair",
		"",
		*(
			_table(["Currency pair", "Best model", "Model MAPEs"], pair_rows)
			if pair_rows
			else ["No pair-level model results recorded."]
		),
	]


def _summary_lines(summary: dict[str, Any], best_model: dict[str, Any]) -> list[str]:
	summary_results = summary["results"]
	best_results = best_model["results"]
	headers = ["Model", "From", "To", "Observations"] + [label for _, label, _, _ in SUMMARY_METRICS]
	lines = ["## 90-day summary by currency pair", ""]

	for pair in sorted(set(summary_results) | set(best_results)):
		lines.extend([f"### `{pair}`", ""])
		pair_best = best_results.get(pair, {})
		pair_models = set(summary_results.get(pair, {})) | set(pair_best.get("model_mapes", {}))
		if not pair_models:
			lines.extend(["No summary results recorded.", ""])
			continue

		lines.extend([f"Best model: `{pair_best.get('best_model', '—')}`", ""])
		rows = []
		for model in sorted(pair_models):
			entry = summary_results.get(pair, {}).get(model, {}).get("90_days")
			if not isinstance(entry, dict):
				rows.append([f"`{model}`"] + ["—"] * (3 + len(SUMMARY_METRICS)))
				continue
			metrics = entry.get("summary_metrics", {})
			count = entry.get("observation_count")
			rows.append([
				f"`{model}`",
				str(entry.get("from_date", "—")),
				str(entry.get("to_date", "—")),
				"—" if count is None else str(count),
				*(_format_value(metrics.get(key), unit) for key, _, unit, _ in SUMMARY_METRICS),
			])
		lines.extend([*_table(headers, rows), ""])
	return lines


def build_markdown(summary: dict[str, Any], best_model: dict[str, Any]) -> str:
	lines = [
		"# Prediction analysis report",
		"",
		"This report is generated deterministically from `SummaryTestsData.json` and `BestModelData.json`.",
		"",
		*_metadata_lines(summary["metadata"]),
		"",
		*_metric_legend(),
		*_best_model_lines(best_model),
		"",
		*_summary_lines(summary, best_model),
	]
	return "\n".join(lines).rstrip() + "\n"


def write_report(summary: dict[str, Any], best_model: dict[str, Any], output_path: Path) -> Path:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	output_path.write_text(build_markdown(summary, best_model), encoding="utf-8", newline="\n")
	return output_path


def _validate_documents(summary: dict[str, Any], best_model: dict[str, Any]) -> None:
	"""Only needed for files read from disk; pipeline documents are always valid."""
	for key in ("metadata", "results"):
		if not isinstance(summary.get(key), dict):
			raise JsonDocumentError(f"{SUMMARY_FILENAME} must contain object {key}")
	missing = [
		key
		for key in ("metadata", "global_best_model", "global_model_average_mapes", "results")
		if key not in best_model
	]
	if missing:
		raise JsonDocumentError(f"{BEST_MODEL_FILENAME} is missing required keys: " + ", ".join(missing))
	for key in ("metadata", "global_model_average_mapes", "results"):
		if not isinstance(best_model[key], dict):
			raise JsonDocumentError(f"{BEST_MODEL_FILENAME} {key} must be an object")


def main() -> None:
	parser = argparse.ArgumentParser(description="Convert result JSON files to a Markdown report.")
	parser.add_argument("--summary", type=Path, default=RESULTS_DIR / SUMMARY_FILENAME)
	parser.add_argument("--best-model", type=Path, default=RESULTS_DIR / BEST_MODEL_FILENAME)
	parser.add_argument("--output", type=Path, default=RESULTS_DIR / REPORT_FILENAME)
	args = parser.parse_args()

	summary = load_json(args.summary, required=True)
	best_model = load_json(args.best_model, required=True)
	_validate_documents(summary, best_model)
	output_path = write_report(summary, best_model, args.output)
	print(f"Markdown report written to {output_path}")


if __name__ == "__main__":
	main()
