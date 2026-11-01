"""Shared result and error structures for prediction backtesting."""

from dataclasses import asdict, dataclass
from datetime import date
from statistics import mean, median
from typing import Any


@dataclass(slots=True)
class PredictionTestError:
	model_name: str | None
	base_currency: str
	target_currency: str
	reference_from_date: date
	reference_to_date: date
	status: str
	message: str

	def to_dict(self) -> dict[str, Any]:
		result = asdict(self)
		result["reference_from_date"] = self.reference_from_date.isoformat()
		result["reference_to_date"] = self.reference_to_date.isoformat()
		return result


@dataclass(slots=True)
class DailyPredictionTestResult:
	date: date
	base_currency: str
	target_currency: str
	model_name: str
	actual_rate: float
	predicted_rate: float
	lower_bound: float
	upper_bound: float
	error: float
	absolute_error: float
	percentage_error: float
	absolute_percentage_error: float
	in_range: bool
	range_error: float
	range_absolute_error: float
	range_percentage_error: float
	absolute_range_percentage_error: float
	interval_width: float

	@classmethod
	def from_values(
		cls,
		date: date,
		base_currency: str,
		target_currency: str,
		model_name: str,
		actual_rate: float,
		predicted_rate: float,
		lower_bound: float,
		upper_bound: float,
	) -> "DailyPredictionTestResult":
		if actual_rate == 0:
			raise ValueError("actual_rate must not be zero")
		if lower_bound > upper_bound:
			raise ValueError("lower_bound cannot be greater than upper_bound")

		error = predicted_rate - actual_rate
		percentage_error = error / actual_rate * 100

		if actual_rate < lower_bound:
			range_error = actual_rate - lower_bound
		elif actual_rate > upper_bound:
			range_error = actual_rate - upper_bound
		else:
			range_error = 0.0

		range_percentage_error = range_error / actual_rate * 100

		return cls(
			date=date,
			base_currency=base_currency,
			target_currency=target_currency,
			model_name=model_name,
			actual_rate=actual_rate,
			predicted_rate=predicted_rate,
			lower_bound=lower_bound,
			upper_bound=upper_bound,
			error=error,
			absolute_error=abs(error),
			percentage_error=percentage_error,
			absolute_percentage_error=abs(percentage_error),
			in_range=range_error == 0.0,
			range_error=range_error,
			range_absolute_error=abs(range_error),
			range_percentage_error=range_percentage_error,
			absolute_range_percentage_error=abs(range_percentage_error),
			interval_width=upper_bound - lower_bound,
		)

	def to_dict(self) -> dict[str, Any]:
		result = asdict(self)
		result["date"] = self.date.isoformat()
		return result


@dataclass(slots=True)
class PredictionSummaryResult:
	base_currency: str
	target_currency: str
	model_name: str
	from_date: date
	to_date: date
	mae: float
	median_absolute_error: float
	mape: float
	bias: float
	median_bias: float
	coverage: float
	mean_range_absolute_error: float | None
	median_range_absolute_error: float | None
	mean_interval_width: float

	@classmethod
	def from_daily_results(
		cls,
		daily_results: list[DailyPredictionTestResult],
	) -> "PredictionSummaryResult":
		if not daily_results:
			raise ValueError("daily_results must not be empty")

		pairs = {
			(result.base_currency, result.target_currency)
			for result in daily_results
		}
		models = {result.model_name for result in daily_results}

		if len(pairs) != 1:
			raise ValueError("daily_results must contain one currency pair")
		if len(models) != 1:
			raise ValueError("daily_results must contain one prediction model")

		pair = next(iter(pairs))
		range_errors = [
			result.range_absolute_error
			for result in daily_results
			if result.range_absolute_error > 0
		]

		return cls(
			base_currency=pair[0],
			target_currency=pair[1],
			model_name=next(iter(models)),
			from_date=min(result.date for result in daily_results),
			to_date=max(result.date for result in daily_results),
			mae=mean(result.absolute_error for result in daily_results),
			median_absolute_error=median(
				result.absolute_error for result in daily_results
			),
			mape=mean(
				result.absolute_percentage_error for result in daily_results
			),
			bias=mean(result.error for result in daily_results),
			median_bias=median(result.error for result in daily_results),
			coverage=mean(
				result.in_range for result in daily_results
			) * 100,
			mean_range_absolute_error=(
				mean(range_errors) if range_errors else None
			),
			median_range_absolute_error=(
				median(range_errors) if range_errors else None
			),
			mean_interval_width=mean(
				result.interval_width for result in daily_results
			),
		)

	def to_dict(self) -> dict[str, Any]:
		result = asdict(self)
		result["from_date"] = self.from_date.isoformat()
		result["to_date"] = self.to_date.isoformat()
		return result


@dataclass(slots=True)
class CurrencyPairPredictionSummary:
	base_currency: str
	target_currency: str
	best_model: str | None
	model_mapes: dict[str, float]

	@classmethod
	def from_summaries(
		cls,
		summaries: list[PredictionSummaryResult],
	) -> "CurrencyPairPredictionSummary":
		if not summaries:
			raise ValueError("summaries must not be empty")

		pairs = {
			(summary.base_currency, summary.target_currency)
			for summary in summaries
		}
		if len(pairs) != 1:
			raise ValueError("summaries must contain one currency pair")

		model_mapes = {
			summary.model_name: summary.mape
			for summary in summaries
		}
		best_model = min(model_mapes, key=model_mapes.get)
		base_currency, target_currency = next(iter(pairs))

		return cls(
			base_currency=base_currency,
			target_currency=target_currency,
			best_model=best_model,
			model_mapes=model_mapes,
		)

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)