"""Prediction backtesting (refactored version of tests/prediction_analization).

Entry point without the FastAPI app:
	python -m tests.prediction_analization_refactor [--mode all] [--pair EUR/USD] [--force]

Modules:
	config            - BacktestConfig, test windows, default pairs, thresholds
	models            - daily / summary result dataclasses and metric formulas
	prediction_runner - history truncation, validation, predictor execution
	pipeline          - pending tests, merge, summaries, best model, saving
	storage           - JSON loading and atomic writing
	report            - Markdown report
	run_analysis      - command-line interface
"""
