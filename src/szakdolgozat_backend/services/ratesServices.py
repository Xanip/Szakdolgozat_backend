from datetime import date
from szakdolgozat_backend.snapshots.store import Snapshot
from szakdolgozat_backend.calculations.ratesCalculations import ExchangePercentChange, WaterfallVarianceMonth

import pandas as pd

def SelectedRateChart(
    snapshot: Snapshot,
    BaseCurrency: str,
    TargetCurrency: str,
    FromDate: date | None = None,
    ToDate: date | None = None,
) -> pd.DataFrame:
    currencies = snapshot.DimCurrencies

    def resolve_currency_id(currency: str) -> object:
        matches = currencies.loc[
            currencies["CurrencyCode"].eq(currency),
            "CurrencyID",
        ].unique()

        if len(matches) != 1:
            raise ValueError(f"Unknown or ambiguous currency: {currency}")

        return matches[0]

    base_currency_id = resolve_currency_id(BaseCurrency)
    target_currency_id = resolve_currency_id(TargetCurrency)

    dates = snapshot.DimDates.copy()
    dates["Date"] = pd.to_datetime(dates["Date"], errors="coerce").dt.normalize()

    def resolve_date_id(date_value: date) -> object:
        if not isinstance(date_value, date):
            raise TypeError("FromDate and ToDate must be date values")

        parsed_date = pd.Timestamp(date_value).normalize()

        date_matches = dates.loc[
            dates["Date"].eq(parsed_date),
            "DateID",
        ].unique()
        if len(date_matches) != 1:
            raise ValueError(f"Unknown or ambiguous date: {date_value}")

        return date_matches[0]

    from_date_id = resolve_date_id(FromDate) if FromDate else None
    to_date_id = resolve_date_id(ToDate) if ToDate else None

    fact_rates = snapshot.FactExchangeRates
    mask = fact_rates["BaseCurrencyID"].eq(base_currency_id)
    mask &= fact_rates["CurrencyID"].eq(target_currency_id)

    if from_date_id is not None:
        mask &= fact_rates["DateID"].ge(from_date_id)
    if to_date_id is not None:
        mask &= fact_rates["DateID"].le(to_date_id)

    return fact_rates.loc[mask].sort_values("DateID").reset_index(drop=True)

def RateAtDate(
    snapshot: Snapshot,
    BaseCurrency: str,
    TargetCurrency: str,
    Date: date | None = None,
) -> float | None:

    """Return the exchange rate for the given base and target currencies at a specific date."""
    if Date is None:
        raise ValueError("Date must be provided")

    rates_df = SelectedRateChart(snapshot, BaseCurrency, TargetCurrency, Date, Date)

    if rates_df.empty:
        return None

    return float(rates_df.iloc[0]["Rate"])

def LatestRate(
    snapshot: Snapshot,
    BaseCurrency: str | None = None,
    TargetCurrency: str | None = None,
    ToDate: date | None = None,
    rates_df: pd.DataFrame | None = None,
) -> float | None:
    """Return the latest exchange rate for the given base and target currencies, optionally filtered by a specific date."""
    if rates_df is not None:
        return None if rates_df.empty else float(rates_df.iloc[-1]["Rate"])

    if ToDate:
        return RateAtDate(snapshot, BaseCurrency, TargetCurrency, ToDate)

    # If no ToDate is provided, return the latest available rate
    rates_df = SelectedRateChart(snapshot, BaseCurrency, TargetCurrency, None, None)
    return None if rates_df.empty else float(rates_df.iloc[-1]["Rate"])

def PreviousRate(
    snapshot: Snapshot,
    BaseCurrency: str | None = None,
    TargetCurrency: str | None = None,
    ToDate: date | None = None,
    rates_df: pd.DataFrame | None = None,
) -> float | None:
    """Return the previous exchange rate for the given base and target currencies, optionally filtered by a specific date."""
    if rates_df is None:
        rates_df = SelectedRateChart(
            snapshot,
            BaseCurrency,
            TargetCurrency,
            None,
            ToDate,
        )

    if len(rates_df) < 2:
        return None

    return float(rates_df.iloc[-2]["Rate"])

def StartPeriodRate(
    snapshot: Snapshot,
    BaseCurrency: str | None = None,
    TargetCurrency: str | None = None,
    FromDate: date | None = None,
    rates_df: pd.DataFrame | None = None,
) -> float | None:
    """Return the exchange rate for the given base and target currencies at the start of a specified period."""
    if rates_df is not None:
        return None if rates_df.empty else float(rates_df.iloc[0]["Rate"])
    
    if FromDate is None:
        raise ValueError("FromDate must be provided")

    rates_df = SelectedRateChart(snapshot, BaseCurrency, TargetCurrency, FromDate, None)

    if rates_df.empty:
        return None

    return float(rates_df.iloc[0]["Rate"])

def DailyPercentChange(
    snapshot: Snapshot,
    BaseCurrency: str,
    TargetCurrency: str,
    ToDate: date | None = None,
    latest_rate: float | None = None,
    previous_rate: float | None = None,
) ->  float | None:
    """Calculate the daily percentage change in exchange rate for the given base and target currencies."""

    if latest_rate is None:
        latest_rate = LatestRate(snapshot, BaseCurrency, TargetCurrency, ToDate)
    if previous_rate is None:
        previous_rate = PreviousRate(snapshot, BaseCurrency, TargetCurrency, ToDate)

    if latest_rate is None or previous_rate is None:
        return None

    if previous_rate == 0:
        return None

    return ExchangePercentChange(latest_rate, previous_rate)

def PeriodPercentChange(
    snapshot: Snapshot,
    BaseCurrency: str,
    TargetCurrency: str,
    FromDate: date | None = None,
    ToDate: date | None = None,
    start_period_rate: float | None = None,
    latest_rate: float | None = None,
) -> float | None:
    """Calculate the percentage change in exchange rate over a specified period for the given base and target currencies."""

    if start_period_rate is None:
        start_period_rate = StartPeriodRate(
            snapshot,
            BaseCurrency,
            TargetCurrency,
            FromDate,
        )
    if latest_rate is None:
        latest_rate = LatestRate(snapshot, BaseCurrency, TargetCurrency, ToDate)

    if start_period_rate is None or latest_rate is None:
        return None

    if start_period_rate == 0:
        return None

    return ExchangePercentChange(latest_rate, start_period_rate)

#ha a rates_df már van akkor a base s target is lehet üres
def WaterfallVariance(
    snapshot: Snapshot,
    BaseCurrency: str | None = None,
    TargetCurrency: str | None = None,
    FromDate: date | None = None,
    ToDate: date | None = None,
    rates_df: pd.DataFrame | None = None,
) -> pd.DataFrame | None:
    """Return monthly average-rate variances for the supplied interval."""
    if rates_df is None:
        rates_df = SelectedRateChart(
            snapshot,
            BaseCurrency,
            TargetCurrency,
            FromDate,
            ToDate,
        )

    if rates_df.empty:
        return None

    dates_df = snapshot.DimDates.copy()
    dates_df["Date"] = pd.to_datetime(dates_df["Date"], errors="coerce").dt.normalize()
    merged_df = rates_df.merge(
        dates_df[["DateID", "Date"]],
        on="DateID",
        how="left",
        validate="many_to_one",
    )
    merged_df = merged_df.dropna(subset=["Date", "Rate"])

    if merged_df.empty:
        return None

    monthly_groups = (
        merged_df.assign(Year_Month=merged_df["Date"].dt.to_period("M"))
        .groupby("Year_Month")["Rate"]
        .agg(list)
        .sort_index()
        .reset_index(name="Rates")
    )

    monthly_groups["Variance"] = [
        None,
        *[
            WaterfallVarianceMonth(
                current_rates,
                previous_rates,
            )
            for previous_rates, current_rates in zip(
                monthly_groups["Rates"].iloc[:-1],
                monthly_groups["Rates"].iloc[1:],
            )
        ],
    ]

    result = monthly_groups.iloc[1:][["Year_Month", "Variance"]].copy()
    result["Year_Month"] = result["Year_Month"].astype(str)
    return result.reset_index(drop=True)