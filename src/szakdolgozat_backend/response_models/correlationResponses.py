from datetime import date
from pydantic import BaseModel

class CategoryCorrelationRow(BaseModel):
    category_name: str
    pearson_r: float | None
    pearson_p_value: float | None
    pearson_adjusted_p_value: float | None
    spearman_r: float | None
    spearman_p_value: float | None
    spearman_adjusted_p_value: float | None
    sample_size: int

class CorrelationObservationRow(BaseModel):
    date: date
    exchange_rate: float
    daily_change_pct: float
    news_count: dict[str, int]  # Dictionary with category names as keys and counts (category/day) as values

class ExchangeRateSeriesRow(BaseModel):
    date: date
    exchange_rate: float

class AnyalysisPeriod(BaseModel):
    start_date: date | None
    end_date: date | None

class CorrelationResponseForLLM(BaseModel):
    currency_pair: str
    analysis_period: AnyalysisPeriod
    correlation_results: list[CategoryCorrelationRow]

class CorrelationResponse(BaseModel):
    currency_pair: str
    correlation_analysis: str
    analysis_period: AnyalysisPeriod
    correlation_results: list[CategoryCorrelationRow]
    paired_observations: list[CorrelationObservationRow]
    exchange_rate_series: list[ExchangeRateSeriesRow]

class LLMAnalysisResponse(BaseModel):
    analysis: str
