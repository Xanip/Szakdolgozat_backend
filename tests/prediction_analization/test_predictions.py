"""Compatibility exports for prediction backtesting.

The implementation is split by responsibility:
- models: shared result and error structures
- calculations: metric calculation entry points
- helpers: history preparation, validation, and eligibility checks
- orchestrator: reserved for the future full workflow
"""

from .calculations import (
    calculate_currency_pair_summary,
    calculate_daily_result,
    calculate_prediction_summary,
)
from .helpers import (
    is_currency_pair_eligible_for_analysis,
    is_model_eligible_for_90_day_summary,
    prepare_prediction_test_data,
)
from .models import (
    CurrencyPairPredictionSummary,
    DailyPredictionTestResult,
    PredictionSummaryResult,
    PredictionTestError,
)

__all__ = [
    "CurrencyPairPredictionSummary",
    "DailyPredictionTestResult",
    "PredictionSummaryResult",
    "PredictionTestError",
    "calculate_currency_pair_summary",
    "calculate_daily_result",
    "calculate_prediction_summary",
    "is_currency_pair_eligible_for_analysis",
    "is_model_eligible_for_90_day_summary",
    "prepare_prediction_test_data",
]
