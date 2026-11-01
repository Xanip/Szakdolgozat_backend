"""Result and error structures, plus the daily and summary metric formulas."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
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


_TEXT_FIELDS = {"base_currency", "target_currency", "model_name"}


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
	) -> DailyPredictionTestResult:
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

	@classmethod
	def from_dict(cls, value: dict[str, Any]) -> DailyPredictionTestResult:
		"""Inverse of to_dict(); extra keys are ignored."""
		kwargs: dict[str, Any] = {}
		for field in fields(cls):
			raw = value[field.name]
			if field.name == "date":
				kwargs["date"] = date.fromisoformat(raw)
			elif field.name == "in_range":
				kwargs["in_range"] = bool(raw)
			elif field.name in _TEXT_FIELDS:
				kwargs[field.name] = raw
			else:
				kwargs[field.name] = float(raw)
		return cls(**kwargs)

	def to_dict(self) -> dict[str, Any]:
		result = asdict(self)
		result["date"] = self.date.isoformat()
		return result


_SUMMARY_IDENTITY_FIELDS = {
	"base_currency", "target_currency", "model_name", "from_date", "to_date",
}


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
	) -> PredictionSummaryResult:
		if not daily_results:
			raise ValueError("daily_results must not be empty")

		pairs = {(r.base_currency, r.target_currency) for r in daily_results}
		models = {r.model_name for r in daily_results}
		if len(pairs) != 1:
			raise ValueError("daily_results must contain one currency pair")
		if len(models) != 1:
			raise ValueError("daily_results must contain one prediction model")

		base_currency, target_currency = next(iter(pairs))
		absolute_errors = [r.absolute_error for r in daily_results]
		errors = [r.error for r in daily_results]
		range_errors = [
			r.range_absolute_error for r in daily_results if r.range_absolute_error > 0
		]

		return cls(
			base_currency=base_currency,
			target_currency=target_currency,
			model_name=next(iter(models)),
			from_date=min(r.date for r in daily_results),
			to_date=max(r.date for r in daily_results),
			mae=mean(absolute_errors),
			median_absolute_error=median(absolute_errors),
			mape=mean(r.absolute_percentage_error for r in daily_results),
			bias=mean(errors),
			median_bias=median(errors),
			coverage=mean(r.in_range for r in daily_results) * 100,
			mean_range_absolute_error=mean(range_errors) if range_errors else None,
			median_range_absolute_error=median(range_errors) if range_errors else None,
			mean_interval_width=mean(r.interval_width for r in daily_results),
		)

	def to_entry(self, observation_count: int) -> dict[str, Any]:
		"""Shape used in SummaryTestsData.json for one window."""
		values = asdict(self)
		return {
			"from_date": self.from_date.isoformat(),
			"to_date": self.to_date.isoformat(),
			"observation_count": observation_count,
			"summary_metrics": {
				key: value
				for key, value in values.items()
				if key not in _SUMMARY_IDENTITY_FIELDS
			},
		}
