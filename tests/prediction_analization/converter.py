"""Convert prediction summary JSON documents to a readable Markdown report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).with_name("results")
DEFAULT_SUMMARY_PATH = RESULTS_DIR / "SummaryTestsData.json"
DEFAULT_BEST_MODEL_PATH = RESULTS_DIR / "BestModelData.json"
DEFAULT_OUTPUT_PATH = RESULTS_DIR / "PredictionAnalysisReport.md"

SUMMARY_METRICS: tuple[tuple[str, str, str], ...] = (
    ("mae", "MAE", "rate"),
    ("median_absolute_error", "Median absolute error", "rate"),
    ("mape", "MAPE", "percent"),
    ("bias", "Bias", "rate"),
    ("median_bias", "Median bias", "rate"),
    ("coverage", "Coverage", "percent"),
    ("mean_range_absolute_error", "Mean range absolute error", "rate"),
    ("median_range_absolute_error", "Median range absolute error", "rate"),
    ("mean_interval_width", "Mean interval width", "rate"),
)

METRIC_MEANINGS = {
    "mae": "A napi abszolút hibák átlaga.",
    "median_absolute_error": "A napi abszolút hibák mediánja.",
    "mape": "Az abszolút százalékos hibák átlaga; a kisebb érték pontosabb modellt jelez.",
    "bias": "Az előjeles hibák átlaga; pozitív érték túlbecslést, negatív érték alulbecslést jelez.",
    "median_bias": "Az előjeles hibák mediánja; az előrejelzések tipikus irányú eltérését mutatja.",
    "coverage": "A tényleges értékek százalékos aránya, amely a predikciós intervallumba esett.",
    "mean_range_absolute_error": "A predikciós intervallumon kívül eső értékek átlagos abszolút távolsága.",
    "median_range_absolute_error": "A predikciós intervallumon kívül eső értékek abszolút távolságának mediánja.",
    "mean_interval_width": "A predikciós intervallum alsó és felső határa közötti átlagos szélesség.",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except FileNotFoundError as exc:
        raise ValueError(f"Input file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _validate_documents(
    summary: dict[str, Any],
    best_model: dict[str, Any],
) -> None:
    if not isinstance(summary.get("metadata"), dict):
        raise ValueError("SummaryTestsData.json must contain object metadata")
    if not isinstance(summary.get("results"), dict):
        raise ValueError("SummaryTestsData.json must contain object results")

    required_best_keys = ("metadata", "global_best_model", "global_model_average_mapes", "results")
    missing = [key for key in required_best_keys if key not in best_model]
    if missing:
        raise ValueError(
            "BestModelData.json is missing required keys: " + ", ".join(missing)
        )
    if not isinstance(best_model["metadata"], dict):
        raise ValueError("BestModelData.json must contain object metadata")
    if not isinstance(best_model["global_model_average_mapes"], dict):
        raise ValueError("BestModelData.json global_model_average_mapes must be an object")
    if not isinstance(best_model["results"], dict):
        raise ValueError("BestModelData.json results must be an object")


def _format_value(value: Any, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "percent":
        return f"{float(value):.2f}%"
    if unit == "rate":
        return f"{float(value):.6f}"
    return str(value)


def _format_count(value: Any) -> str:
    return "—" if value is None else str(value)


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_escape_cell(cell) for cell in row) + " |"
        for row in rows
    )
    return lines


def _metadata_lines(metadata: dict[str, Any]) -> list[str]:
    configuration = metadata.get("test_configuration", {})
    lines = [
        "## Test configuration",
        "",
        f"- Generated at: `{metadata.get('generated_at', '—')}`",
        f"- Currency pair mode: `{metadata.get('currency_pair_mode', '—')}`",
        f"- Models: {', '.join(f'`{model}`' for model in metadata.get('models', [])) or '—'}",
        f"- Currency pairs: {len(metadata.get('currency_pairs', []))}",
        f"- Horizon: {configuration.get('horizon', '—')} days",
        f"- Minimum history observations: {configuration.get('minimum_history_observations', '—')}",
        f"- Minimum reference observations: {configuration.get('minimum_reference_observations', '—')}",
        "",
        "### Test windows",
        "",
    ]

    windows = configuration.get("test_windows", [])
    rows = [
        [str(window.get("id", "—")), str(window.get("from_date", "—")), str(window.get("to_date", "—"))]
        for window in windows
    ]
    lines.extend(_table(["Window", "From", "To"], rows) if rows else ["No test windows recorded."])
    return lines


def _metric_legend() -> list[str]:
    rows = [
        [label, METRIC_MEANINGS[key]]
        for key, label, _ in SUMMARY_METRICS
    ]
    return ["## Metric legend", "", *_table(["Metric", "Meaning"], rows), ""]


def _best_model_lines(best_model: dict[str, Any]) -> list[str]:
    global_mapes = best_model["global_model_average_mapes"]
    rows = [
        ["1" if model == best_model.get("global_best_model") else "", f"`{model}`", _format_value(mape, "percent")]
        for model, mape in sorted(global_mapes.items(), key=lambda item: (float(item[1]), item[0]))
    ]
    lines = [
        "## Model comparison",
        "",
        f"**Global best model:** `{best_model.get('global_best_model', '—')}`",
        "",
        *_table(["Best", "Model", "Average MAPE"], rows),
        "",
        "### Best model by currency pair",
        "",
    ]
    pair_rows = []
    for pair, result in sorted(best_model["results"].items()):
        model_mapes = result.get("model_mapes", {})
        mapes = ", ".join(
            f"`{model}`: {_format_value(mape, 'percent')}"
            for model, mape in sorted(model_mapes.items())
        ) or "—"
        pair_rows.append([f"`{pair}`", f"`{result.get('best_model', '—')}`", mapes])
    lines.extend(_table(["Currency pair", "Best model", "Model MAPEs"], pair_rows) if pair_rows else ["No pair-level model results recorded."])
    return lines


def _summary_lines(summary: dict[str, Any], best_model: dict[str, Any]) -> list[str]:
    summary_results = summary["results"]
    best_results = best_model["results"]
    pairs = sorted(set(summary_results) | set(best_results))
    lines = ["## 90-day summary by currency pair", ""]

    for pair in pairs:
        lines.extend([f"### `{pair}`", ""])
        pair_models = set(summary_results.get(pair, {})) | set(best_results.get(pair, {}).get("model_mapes", {}))
        if not pair_models:
            lines.append("No summary results recorded.")
            lines.append("")
            continue

        lines.append(
            f"Best model: `{best_results.get(pair, {}).get('best_model', '—')}`"
        )
        lines.append("")
        rows = []
        for model in sorted(pair_models):
            entry = summary_results.get(pair, {}).get(model, {}).get("90_days")
            if not isinstance(entry, dict):
                rows.append(
                    [f"`{model}`", "—", "—", "—"]
                    + ["—"] * len(SUMMARY_METRICS)
                )
                continue
            metrics = entry.get("summary_metrics", {})
            row = [f"`{model}`", str(entry.get("from_date", "—")), str(entry.get("to_date", "—")), _format_count(entry.get("observation_count"))]
            row.extend(_format_value(metrics.get(key), unit) for key, _, unit in SUMMARY_METRICS)
            rows.append(row)

        headers = ["Model", "From", "To", "Observations"] + [label for _, label, _ in SUMMARY_METRICS]
        lines.extend(_table(headers, rows))
        lines.append("")

    return lines


def build_markdown(summary: dict[str, Any], best_model: dict[str, Any]) -> str:
    _validate_documents(summary, best_model)
    metadata = summary["metadata"]
    lines = [
        "# Prediction analysis report",
        "",
        "This report is generated deterministically from `SummaryTestsData.json` and `BestModelData.json`.",
        "",
        *_metadata_lines(metadata),
        "",
        *_metric_legend(),
        *_best_model_lines(best_model),
        "",
        *_summary_lines(summary, best_model),
    ]
    return "\n".join(lines).rstrip() + "\n"


def convert(
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    best_model_path: Path = DEFAULT_BEST_MODEL_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    summary = _load_json(summary_path)
    best_model = _load_json(best_model_path)
    markdown = build_markdown(summary, best_model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8", newline="\n")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--best-model", type=Path, default=DEFAULT_BEST_MODEL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    output_path = convert(args.summary, args.best_model, args.output)
    print(f"Markdown report written to {output_path}")


if __name__ == "__main__":
    main()
