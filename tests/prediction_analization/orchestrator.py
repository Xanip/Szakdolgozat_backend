"""Coordinate the prediction backtesting workflow."""

from __future__ import annotations

import logging
from typing import Any

from szakdolgozat_backend.snapshots.store import Snapshot

from .configuration import BacktestConfig, CurrencyPairMode, TestWindow
from .converter import convert
from .execution import execute_backtests
from .state import (
	BacktestState,
	get_pending_tests,
	load_backtest_state,
	rebuild_summaries,
	save_backtest_state,
	update_backtest_results,
)

__all__ = [
	"BacktestConfig",
	"BacktestState",
	"CurrencyPairMode",
	"TestWindow",
	"run_prediction_analysis",
]

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
	"""Make analysis progress visible for both Uvicorn and CLI runs."""
	root_logger = logging.getLogger()
	if not root_logger.handlers:
		logging.basicConfig(
			level=logging.INFO,
			format="%(asctime)s %(levelname)s %(name)s: %(message)s",
		)

	logging.getLogger("tests.prediction_analization").setLevel(logging.INFO)


def run_prediction_analysis(
	snapshot: Snapshot,
	config: BacktestConfig,
	force: bool = False,
) -> dict[str, Any]:
	"""Run pending backtests and persist all derived result documents."""
	_configure_logging()
	config = config.for_snapshot(snapshot)
	config.validate()
	logger.info(
		"[PREDICTION] analysis started pairs=%d windows=%d models=%d",
		len(config.currency_pairs),
		len(config.test_windows),
		len(config.model_names),
	)

	# 1. Meglévő eredmények betöltése
	state = load_backtest_state(config)
	# 2. Hiányzó tesztek meghatározása
	pending_tests = get_pending_tests(state, config, force)
	logger.info(
		"[PREDICTION] pending test groups=%d",
		len(pending_tests),
	)
	# 3. Predikciók végrehajtása
	new_predictions, errors = execute_backtests(
		snapshot,
		config,
		pending_tests,
	)
	# 4. Eredmények összeállítása
	state = update_backtest_results(state, new_predictions, config)
	# 5. Összesítések újraszámítása
	state = rebuild_summaries(state, config)
	# 6. JSON-ok mentése
	save_backtest_state(state, config, errors)
	report_path = convert(
		config.results_dir / "SummaryTestsData.json",
		config.results_dir / "BestModelData.json",
		config.results_dir / "PredictionAnalysisReport.md",
	)
	successful_windows = sum(
		len(model_windows)
		for pair_models in new_predictions.values()
		for model_windows in pair_models.values()
	)
	logger.info(
		"[PREDICTION] analysis finished successful_windows=%d errors=%d report=%s",
		successful_windows,
		len(errors),
		report_path,
	)

	return state
