"""Configuration types for prediction backtesting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from szakdolgozat_backend.services.predictionServices import PREDICTORS


class CurrencyPairMode(StrEnum):
	SELECTED = "selected"
	ALL = "all"


@dataclass(frozen=True, slots=True)
class TestWindow:
	id: str
	from_date: date
	to_date: date

	@classmethod
	def from_start(cls, window_id: str, from_date: date, horizon: int) -> "TestWindow":
		return cls(window_id, from_date, from_date + timedelta(days=horizon - 1))


@dataclass(frozen=True, slots=True)
class BacktestConfig:
	currency_pairs: tuple[tuple[str, str], ...] = ()
	test_windows: tuple[TestWindow, ...] = ()
	pair_mode: CurrencyPairMode | str = CurrencyPairMode.SELECTED
	models: tuple[str, ...] | None = None
	horizon: int = 30
	results_dir: Path = Path("tests/prediction_analization/results")

	@property
	def model_names(self) -> tuple[str, ...]:
		return self.models or tuple(PREDICTORS)

	@property
	def normalized_pair_mode(self) -> CurrencyPairMode:
		return CurrencyPairMode(self.pair_mode)

	def for_snapshot(self, snapshot: Any) -> "BacktestConfig":
		"""Resolve the configured pair mode before the workflow starts."""
		from dataclasses import replace

		return replace(self, currency_pairs=self.resolve_currency_pairs(snapshot))

	def resolve_currency_pairs(self, snapshot: Any) -> tuple[tuple[str, str], ...]:
		if self.normalized_pair_mode is CurrencyPairMode.SELECTED:
			return tuple(self.currency_pairs)

		currencies = snapshot.DimCurrencies["CurrencyCode"].dropna().astype(str)
		codes = tuple(sorted({currency.upper() for currency in currencies}))
		return tuple(
			(base_currency, target_currency)
			for base_currency in codes
			for target_currency in codes
			if base_currency != target_currency
		)

	def validate(self) -> None:
		if self.horizon <= 0:
			raise ValueError("horizon must be greater than zero")
		unknown_models = set(self.model_names) - set(PREDICTORS)
		if unknown_models:
			raise ValueError(f"Unknown prediction models: {sorted(unknown_models)}")
		if (
			self.normalized_pair_mode is CurrencyPairMode.SELECTED
			and not self.currency_pairs
		):
			raise ValueError(
				"currency_pairs must contain at least one pair in selected mode"
			)
		if any(base == target for base, target in self.currency_pairs):
			raise ValueError("currency pairs must contain two different currencies")

	def metadata(self) -> dict[str, Any]:
		return {
			"generated_at": datetime.now().isoformat(timespec="seconds"),
			"test_configuration": {
				"horizon": self.horizon,
				"minimum_reference_observations": 5,
				"minimum_history_observations": 30,
				"required_test_windows": len(self.test_windows),
				"test_windows": [
					{
						"id": window.id,
						"from_date": window.from_date.isoformat(),
						"to_date": window.to_date.isoformat(),
					}
					for window in self.test_windows
				],
			},
			"models": list(self.model_names),
			"currency_pair_mode": self.normalized_pair_mode.value,
			"currency_pairs": [
				f"{base}/{target}" for base, target in self.currency_pairs
			],
		}


PendingTest = tuple[str, str, TestWindow, tuple[str, ...]]

DEFAULT_PAIR_MODE = CurrencyPairMode.SELECTED
DEFAULT_SELECTED_PAIR_CODES = (
	"INR/KGS", "LRD/QAR", "DJF/ERN", "KWD/SLE", "AZN/IRR",
	"BIF/MGA", "GEL/USD", "AED/ZMW", "BAM/MUR", "RSD/RUB",
	"AFN/CUP", "NGN/SYP", "BWP/IDR", "MDL/SHP", "CDF/GHS",
	"COP/VND", "PKR/TND", "KES/MKD", "CZK/DZD", "BDT/VES",
	"BBD/UGX", "ILS/THB", "BOB/TRY", "NZD/RWF", "GBP/GTQ",
	"LYD/MNT", "JOD/LKR", "BYN/LAK", "CRC/DKK", "NIO/TWD",
	"AUD/STN", "CNY/WST", "PEN/SAR", "GYD/MMK", "AWG/VUV",
	"MVR/SZL", "MRU/MWK", "GIP/UYU", "JPY/TTD", "BND/TMT",
	"PAB/YER", "ANG/HUF", "BTN/KYD", "ALL/XPF", "ISK/LSL",
	"BRL/RON", "AOA/XAF", "CVE/UZS", "LBP/MYR", "FKP/SBD",
	"DOP/ZWG", "CAD/FJD", "BSD/SGD", "NAD/SDG", "SRD/UAH",
	"MAD/TZS", "BMD/KHR", "CHF/GMD", "EUR/KRW", "PLN/SVC",
	"GNF/XCD", "IQD/NPR", "EGP/SSP", "ARS/ETB", "BHD/OMR",
	"HNL/JMD", "PHP/TJS", "HKD/SOS", "PYG/SCR", "CLP/KZT",
	"NOK/SEK", "MXN/XOF", "AMD/BZD", "TOP/ZAR", "HTG/PGK",
	"MOP/MZN", "KGS/QAR", "ERN/INR", "LRD/SLE", "AZN/DJF",
	"BIF/KWD", "IRR/USD", "AED/MGA", "BAM/GEL", "RUB/ZMW",
	"AFN/MUR", "RSD/SYP", "BWP/CUP", "MDL/NGN", "GHS/IDR",
	"COP/SHP", "CDF/PKR", "MKD/VND", "CZK/TND", "KES/VES",
	"DZD/UGX", "BDT/THB", "BBD/TRY", "ILS/RWF", "BOB/GTQ",
	"MNT/NZD", "GBP/JOD", "BYN/LYD", "CRC/LKR", "LAK/TWD",
	"DKK/STN", "CNY/NIO", "AUD/SAR", "MMK/WST", "PEN/VUV",
	"GYD/SZL", "AWG/MRU", "MVR/UYU", "MWK/TTD", "GIP/TMT",
	"JPY/PAB", "BND/HUF", "KYD/YER", "ANG/XPF", "BTN/LSL",
	"ALL/RON", "AOA/ISK", "BRL/CVE", "LBP/XAF", "SBD/UZS",
	"MYR/ZWG", "FJD/FKP", "BSD/DOP", "CAD/NAD", "SGD/UAH",
	"SDG/TZS", "BMD/SRD", "GMD/MAD", "EUR/KHR", "CHF/SVC",
	"KRW/XCD", "NPR/PLN", "EGP/GNF", "ETB/IQD", "OMR/SSP",
	"ARS/HNL", "BHD/PHP", "HKD/JMD", "SCR/TJS", "KZT/SOS",
	"NOK/PYG", "CLP/XOF", "AMD/SEK", "MXN/ZAR", "BZD/PGK",
	"MOP/TOP", "HTG/MZN", "ERN/KGS", "QAR/SLE", "AZN/INR",
	"BIF/LRD", "DJF/USD", "AED/KWD", "BAM/IRR", "MGA/RUB",
	"AFN/GEL", "SYP/ZMW", "BWP/MUR", "MDL/RSD", "CUP/GHS",
	"COP/NGN", "IDR/PKR", "MKD/SHP", "CDF/CZK", "VES/VND",
	"TND/UGX", "KES/THB", "DZD/TRY", "BDT/RWF", "BBD/GTQ",
	"ILS/MNT", "BOB/JOD", "BYN/NZD", "CRC/GBP", "LYD/TWD",
	"LKR/STN", "CNY/LAK", "DKK/SAR", "MMK/NIO", "AUD/VUV",
	"SZL/WST", "MRU/PEN", "GYD/UYU", "AWG/TTD", "MVR/TMT",
	"MWK/PAB", "GIP/HUF", "JPY/KYD", "BND/XPF", "LSL/YER",
	"ANG/RON", "AOA/BTN", "ALL/CVE", "ISK/LBP", "BRL/SBD",
	"XAF/ZWG", "FJD/UZS", "BSD/MYR", "FKP/NAD", "DOP/UAH",
	"CAD/TZS", "BMD/SGD", "GMD/SDG", "EUR/SRD", "MAD/SVC",
	"KHR/XCD", "CHF/NPR", "EGP/KRW", "ETB/PLN", "GNF/OMR",
	"HNL/IQD", "PHP/SSP", "ARS/HKD", "BHD/SCR", "JMD/KZT",
	"NOK/TJS", "SOS/XOF", "AMD/PYG", "CLP/ZAR", "PGK/SEK",
	"MOP/MXN", "BZD/MZN", "HTG/TOP", "KGS/SLE", "AZN/ERN",
	"BIF/QAR", "INR/USD", "AED/LRD", "BAM/DJF", "KWD/RUB",
	"AFN/IRR", "MGA/SYP", "BWP/GEL", "MDL/ZMW", "GHS/MUR",
	"COP/RSD", "CUP/PKR", "MKD/NGN", "CZK/IDR", "SHP/VES",
	"CDF/UGX", "THB/VND", "TND/TRY", "KES/RWF", "DZD/GTQ",
	"BDT/MNT", "BBD/JOD", "BYN/ILS", "BOB/CRC", "NZD/TWD",
	"GBP/STN", "CNY/LYD", "LKR/SAR", "LAK/MMK", "DKK/VUV",
	"NIO/SZL", "AUD/MRU", "UYU/WST", "PEN/TTD", "GYD/TMT",
	"AWG/PAB", "HUF/MVR", "KYD/MWK", "GIP/XPF", "JPY/LSL",
	"BND/RON", "AOA/YER", "ANG/CVE", "BTN/LBP", "ALL/SBD",
	"ISK/ZWG", "BRL/FJD", "BSD/XAF", "NAD/UZS", "MYR/UAH",
	"FKP/TZS", "BMD/DOP", "CAD/GMD", "EUR/SGD", "SDG/SVC",
	"SRD/XCD", "MAD/NPR", "EGP/KHR", "CHF/ETB", "KRW/OMR",
	"HNL/PLN", "GNF/PHP", "HKD/IQD", "SCR/SSP", "ARS/KZT",
	"BHD/NOK", "JMD/XOF", "AMD/TJS", "SOS/ZAR", "PGK/PYG",
	"CLP/MOP", "MZN/SEK", "HTG/MXN", "BZD/TOP", "AZN/KGS",
	"BIF/SLE", "ERN/USD", "AED/QAR", "BAM/INR", "QAR/RUB",
	"AFN/DJF", "KWD/SYP", "BWP/IRR", "MDL/MGA", "GEL/GHS",
	"COP/ZMW", "MUR/PKR", "MKD/RSD", "CUP/CZK", "NGN/VES",
	"IDR/UGX", "SHP/THB", "CDF/TRY", "RWF/VND", "GTQ/TND",
	"KES/MNT", "DZD/JOD", "BDT/BYN", "BBD/CRC", "CNY/ILS",
	"BOB/SAR", "MMK/NZD", "GBP/VUV", "LYD/SZL", "LKR/MRU",
	"LAK/UYU", "DKK/TTD", "NIO/TMT", "AUD/PAB", "HUF/WST",
	"KYD/PEN", "GYD/XPF", "AWG/LSL", "MVR/RON", "AOA/MWK",
	"CVE/GIP", "JPY/LBP", "BND/SBD", "YER/ZWG", "ANG/FJD",
	"BSD/BTN", "ALL/NAD", "ISK/UAH", "BRL/TZS", "BMD/XAF",
	"GMD/UZS", "EUR/MYR", "FKP/SVC", "DOP/XCD", "CAD/NPR",
	"EGP/SGD", "ETB/SDG", "OMR/SRD", "HNL/MAD", "KHR/PHP",
	"CHF/HKD", "KRW/SCR", "KZT/PLN", "GNF/NOK", "IQD/XOF",
	"AMD/SSP", "ARS/ZAR", "BHD/PGK", "JMD/MOP", "MZN/TJS",
	"HTG/SOS", "PYG/TOP", "BZD/CLP", "MXN/SEK", "KGS/USD",
	"AED/BIF", "AZN/BAM", "RUB/SLE", "AFN/ERN", "QAR/SYP",
	"BWP/INR", "LRD/MDL", "DJF/GHS", "COP/KWD", "IRR/PKR",
	"MGA/MKD", "CZK/GEL", "VES/ZMW", "MUR/UGX", "RSD/THB",
	"CUP/TRY", "NGN/RWF", "GTQ/IDR", "MNT/SHP", "CDF/JOD",
	"BYN/VND", "CRC/TND", "KES/TWD", "DZD/STN", "BDT/CNY",
	"BBD/SAR", "ILS/MMK", "BOB/VUV", "NZD/SZL", "GBP/MRU",
	"LYD/UYU", "LKR/TTD", "LAK/TMT", "DKK/PAB", "HUF/NIO",
	"AUD/KYD", "WST/XPF", "LSL/PEN", "GYD/RON", "AOA/AWG",
	"CVE/MVR", "LBP/MWK", "GIP/SBD",
	"EUR/USD", "USD/EUR", "EUR/GBP", "GBP/USD", "USD/JPY",
	"EUR/JPY", "USD/CHF", "EUR/CHF", "USD/CAD", "AUD/USD",
	"NZD/USD", "USD/SEK", "USD/NOK", "USD/DKK", "USD/PLN",
	"USD/CZK", "USD/HUF", "USD/TRY", "EUR/TRY", "EUR/PLN",
	"EUR/CZK", "EUR/HUF", "EUR/RON", "EUR/SEK", "EUR/NOK",
	"EUR/DKK", "GBP/JPY", "GBP/CHF", "GBP/CAD", "GBP/AUD",
	"JPY/CHF", "JPY/AUD", "CHF/JPY", "CAD/JPY", "AUD/JPY",
	"NZD/JPY", "CAD/CHF", "AUD/CHF", "NZD/CHF", "SEK/NOK",
	"NOK/DKK", "PLN/HUF", "CZK/HUF", "RON/HUF", "TRY/RUB",
	"EUR/RUB", "USD/RUB", "EUR/CNY", "USD/CNY", "CNY/JPY",
	"HKD/CNY", "SGD/JPY", "SGD/HKD", "INR/JPY", "INR/AED",
	"INR/GBP", "ZAR/JPY", "ZAR/GBP", "BRL/USD", "MXN/USD",
	"ARS/USD", "CLP/USD", "COP/USD", "PEN/USD", "THB/USD",
	"IDR/USD", "MYR/USD", "PHP/USD", "VND/USD", "EGP/USD",
	"NGN/USD", "KES/USD", "GHS/USD", "MAD/USD", "TZS/USD",
	"UGX/USD", "XOF/USD",
)
DEFAULT_SELECTED_PAIRS = tuple(
	tuple(pair_code.split("/", 1))
	for pair_code in DEFAULT_SELECTED_PAIR_CODES
)
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
