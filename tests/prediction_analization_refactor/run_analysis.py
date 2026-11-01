"""Command-line entry point, independent of the FastAPI app (main.py).

From the Szakdolgozat_backend folder, any of these work:

	python -m tests.prediction_analization_refactor
	python -m tests.prediction_analization_refactor.run_analysis --pair EUR/USD
	python tests/prediction_analization_refactor/run_analysis.py --mode all --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
	# Started as a plain script: make the package and the backend importable.
	_backend_root = Path(__file__).resolve().parents[2]
	for _path in (_backend_root / "src", _backend_root):
		if str(_path) not in sys.path:
			sys.path.insert(0, str(_path))
	__package__ = "tests.prediction_analization_refactor"

from szakdolgozat_backend.snapshots.loader import load_snapshot

from .config import (
	DEFAULT_PAIR_MODE,
	DEFAULT_SELECTED_PAIRS,
	CurrencyPairMode,
	build_default_config,
)
from .pipeline import run_prediction_analysis
from .storage import PREDICTIONS_FILENAME, SUMMARY_FILENAME


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
	config = build_default_config(
		CurrencyPairMode(args.mode),
		tuple(args.pair or DEFAULT_SELECTED_PAIRS),
	)

	snapshot = load_snapshot()
	state = run_prediction_analysis(snapshot, config, force=args.force)
	print(f"Prediction analysis completed in {config.pair_mode} mode.")
	print(f"Prediction JSON: {config.results_dir / PREDICTIONS_FILENAME}")
	print(f"Summary JSON: {config.results_dir / SUMMARY_FILENAME}")
	print(f"Processed pairs: {len(state['predictions']['metadata'].get('currency_pairs', []))}")


if __name__ == "__main__":
	main()
