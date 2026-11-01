"""Command-line entry point for prediction backtesting."""

from __future__ import annotations

import argparse

from szakdolgozat_backend.snapshots.loader import load_snapshot

from .configuration import (
	DEFAULT_PAIR_MODE,
	DEFAULT_SELECTED_PAIRS,
	CurrencyPairMode,
	build_default_config,
)
from .orchestrator import run_prediction_analysis


def _parse_pair(value: str) -> tuple[str, str]:
	parts = value.upper().split("/", maxsplit=1)
	if len(parts) != 2 or not all(parts):
		raise argparse.ArgumentTypeError(
			f"Invalid currency pair '{value}'. Expected BASE/TARGET."
		)
	return parts[0], parts[1]


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="Run prediction backtesting and export JSON results."
	)
	parser.add_argument(
		"--mode",
		choices=[mode.value for mode in CurrencyPairMode],
		default=DEFAULT_PAIR_MODE.value,
		help="Run selected pairs or every currency pair in the snapshot.",
	)
	parser.add_argument(
		"--pair",
		type=_parse_pair,
		action="append",
		help="Selected pair in BASE/TARGET format; can be repeated.",
	)
	parser.add_argument(
		"--force",
		action="store_true",
		help="Recalculate existing prediction windows.",
	)
	return parser


def main() -> None:
	args = build_parser().parse_args()
	pair_mode = CurrencyPairMode(args.mode)
	selected_pairs = tuple(args.pair or DEFAULT_SELECTED_PAIRS)
	config = build_default_config(pair_mode, selected_pairs)

	snapshot = load_snapshot()
	state = run_prediction_analysis(snapshot, config, force=args.force)
	print(f"Prediction analysis completed in {config.pair_mode} mode.")
	print(f"Prediction JSON: {config.results_dir / 'AllPredictionTestsData.json'}")
	print(f"Summary JSON: {config.results_dir / 'SummaryTestsData.json'}")
	print(f"Processed pairs: {len(state['predictions']['metadata'].get('currency_pairs', []))}")


if __name__ == "__main__":
	main()
