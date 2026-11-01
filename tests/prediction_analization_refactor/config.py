"""Backtest configuration: pair mode, test windows, models, thresholds."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from szakdolgozat_backend.services.predictionServices import PREDICTORS

PACKAGE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = PACKAGE_DIR / "results"

MIN_REFERENCE_OBSERVATIONS = 5
MIN_HISTORY_OBSERVATIONS = 30


class CurrencyPairMode(StrEnum):
	SELECTED = "selected"
	ALL = "all"


@dataclass(frozen=True, slots=True)
class TestWindow:
	__test__ = False  # not a pytest test class

	id: str
	from_date: date
	to_date: date

	@classmethod
	def from_start(cls, window_id: str, from_date: date, horizon: int) -> TestWindow:
		return cls(window_id, from_date, from_date + timedelta(days=horizon - 1))

	def to_dict(self) -> dict[str, str]:
		return {
			"id": self.id,
			"from_date": self.from_date.isoformat(),
			"to_date": self.to_date.isoformat(),
		}


@dataclass(frozen=True, slots=True)
class BacktestConfig:
	currency_pairs: tuple[tuple[str, str], ...] = ()
	test_windows: tuple[TestWindow, ...] = ()
	pair_mode: CurrencyPairMode = CurrencyPairMode.SELECTED
	models: tuple[str, ...] | None = None
	horizon: int = 30
	results_dir: Path = RESULTS_DIR

	def __post_init__(self) -> None:
		# Accept plain strings ("all", "selected") as well.
		object.__setattr__(self, "pair_mode", CurrencyPairMode(self.pair_mode))

	@property
	def model_names(self) -> tuple[str, ...]:
		return self.models or tuple(PREDICTORS)

	def for_snapshot(self, snapshot: Any) -> BacktestConfig:
		"""Resolve ALL mode to every ordered pair of snapshot currencies."""
		if self.pair_mode is CurrencyPairMode.SELECTED:
			return replace(self, currency_pairs=tuple(self.currency_pairs))

		currencies = snapshot.DimCurrencies["CurrencyCode"].dropna().astype(str)
		codes = sorted({currency.upper() for currency in currencies})
		pairs = tuple((b, t) for b in codes for t in codes if b != t)
		return replace(self, currency_pairs=pairs)

	def validate(self) -> None:
		if self.horizon <= 0:
			raise ValueError("horizon must be greater than zero")
		unknown_models = set(self.model_names) - set(PREDICTORS)
		if unknown_models:
			raise ValueError(f"Unknown prediction models: {sorted(unknown_models)}")
		if self.pair_mode is CurrencyPairMode.SELECTED and not self.currency_pairs:
			raise ValueError(
				"currency_pairs must contain at least one pair in selected mode"
			)
		if any(base == target for base, target in self.currency_pairs):
			raise ValueError("currency pairs must contain two different currencies")

	def test_configuration(self) -> dict[str, Any]:
		return {
			"horizon": self.horizon,
			"minimum_reference_observations": MIN_REFERENCE_OBSERVATIONS,
			"minimum_history_observations": MIN_HISTORY_OBSERVATIONS,
			"required_test_windows": len(self.test_windows),
			"test_windows": [window.to_dict() for window in self.test_windows],
		}

	def metadata(self) -> dict[str, Any]:
		return {
			"generated_at": datetime.now().isoformat(timespec="seconds"),
			"test_configuration": self.test_configuration(),
			"models": list(self.model_names),
			"currency_pair_mode": self.pair_mode.value,
			"currency_pairs": [f"{b}/{t}" for b, t in self.currency_pairs],
		}


def _load_default_pairs() -> tuple[tuple[str, str], ...]:
	lines = (PACKAGE_DIR / "default_pairs.txt").read_text(encoding="utf-8").splitlines()
	return tuple(
		tuple(line.strip().split("/", 1))
		for line in lines
		if line.strip()
	)


DEFAULT_PAIR_MODE = CurrencyPairMode.SELECTED
DEFAULT_SELECTED_PAIRS = _load_default_pairs()
DEFAULT_WINDOWS = (
	TestWindow.from_start("2026-09", date(2026, 9, 1), 30),
	TestWindow.from_start("2026-03", date(2026, 3, 1), 30),
	TestWindow.from_start("2025-09", date(2025, 9, 1), 30),
)


def build_default_config(
	pair_mode: CurrencyPairMode | str = DEFAULT_PAIR_MODE,
	selected_pairs: tuple[tuple[str, str], ...] = DEFAULT_SELECTED_PAIRS,
) -> BacktestConfig:
	return BacktestConfig(
		pair_mode=pair_mode,
		currency_pairs=selected_pairs,
		test_windows=DEFAULT_WINDOWS,
	)
