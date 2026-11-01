"""Metric calculation entry points for prediction backtesting."""

from datetime import date

from .models import (
	CurrencyPairPredictionSummary,
	DailyPredictionTestResult,
	PredictionSummaryResult,
)


def calculate_daily_result(
	date: date,
	base_currency: str,
	target_currency: str,
	model_name: str,
	actual_rate: float,
	predicted_rate: float,
	lower_bound: float,
	upper_bound: float,
) -> DailyPredictionTestResult:
	return DailyPredictionTestResult.from_values(
		date=date,
		base_currency=base_currency,
		target_currency=target_currency,
		model_name=model_name,
		actual_rate=actual_rate,
		predicted_rate=predicted_rate,
		lower_bound=lower_bound,
		upper_bound=upper_bound,
	)


def calculate_prediction_summary(
	daily_results: list[DailyPredictionTestResult],
) -> PredictionSummaryResult:
	return PredictionSummaryResult.from_daily_results(daily_results)


def calculate_currency_pair_summary(
	summaries: list[PredictionSummaryResult],
) -> CurrencyPairPredictionSummary:
	return CurrencyPairPredictionSummary.from_summaries(summaries)