import logging
import time
from functools import lru_cache

import pandas as pd
from chronos import Chronos2Pipeline

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "Date",
    "PredictedRate",
    "LowerBound",
    "UpperBound",
]


@lru_cache(maxsize=1)
def _get_chronos_pipeline() -> Chronos2Pipeline:
    """
    Loads Chronos-2 once and reuses the pipeline.
    """
    logger.info("Loading Chronos-2 model...")

    pipeline = Chronos2Pipeline.from_pretrained(
        "amazon/chronos-2",
        device_map="cpu",
    )

    logger.info("Chronos-2 model loaded.")

    return pipeline


def predict_with_chronos(
    exchange_rates: pd.DataFrame,
    horizon: int = 30,
    validate_freshness: bool = True,
) -> pd.DataFrame:

    started_at = time.perf_counter()

    required_columns = {
        "Date",
        "Rate",
        "BaseCurrency",
        "TargetCurrency",
    }

    missing = required_columns - set(exchange_rates.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    if horizon <= 0:
        raise ValueError(
            "horizon must be greater than zero"
        )

    if exchange_rates.empty:
        logger.warning(
            "No historical exchange rates provided."
        )
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    # The function expects exactly one currency pair.
    pairs = exchange_rates[
        ["BaseCurrency", "TargetCurrency"]
    ].drop_duplicates()

    if len(pairs) != 1:
        raise ValueError(
            "predict_with_chronos expects exactly one currency pair."
        )

    base, target = pairs.iloc[0]

    # Prepare history.
    history = exchange_rates[
        ["Date", "Rate"]
    ].copy()

    history["Date"] = pd.to_datetime(
        history["Date"],
        errors="coerce",
    )

    history["Rate"] = pd.to_numeric(
        history["Rate"],
        errors="coerce",
    )

    history = (
        history.dropna(subset=["Date", "Rate"])
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )

    if len(history) < 30:
        raise ValueError(
            f"Insufficient observations for {base}/{target}: "
            f"{len(history)}; at least 30 are required."
        )

    today = pd.Timestamp.today().normalize()
    last_date = history["Date"].max().normalize()

    if validate_freshness and (today - last_date).days > 30:
        raise ValueError(
            f"Latest observation for {base}/{target} is stale: "
            f"{last_date.date()}."
        )

    logger.info(
        "Chronos started for %s/%s: %d observations, horizon=%d days",
        base,
        target,
        len(history),
        horizon,
    )

    # Generate the actual calendar dates for the forecast.
    future_dates = pd.date_range(
        start=last_date + pd.Timedelta(days=1),
        periods=horizon,
        freq="D",
    )

    # Chronos input requires regular timestamps.
    # Preserve the sequence of observed rates while assigning
    # consecutive daily timestamps.
    chronos_history = pd.DataFrame({
        "id": "exchange_rate",
        "timestamp": pd.date_range(
            end=last_date,
            periods=len(history),
            freq="D",
        ),
        "target": history["Rate"].to_numpy(),
    })

    pipeline = _get_chronos_pipeline()

    forecast = pipeline.predict_df(
        chronos_history,
        prediction_length=horizon,
        quantile_levels=[0.05, 0.5, 0.95],
        id_column="id",
        timestamp_column="timestamp",
        target="target",
        freq="D",
    )

    result = pd.DataFrame({
        "Date": future_dates,
        "PredictedRate": forecast["0.5"].to_numpy(),
        "LowerBound": forecast["0.05"].to_numpy(),
        "UpperBound": forecast["0.95"].to_numpy(),
    })

    logger.info(
        "Chronos finished for %s/%s: %d predictions in %.2f seconds",
        base,
        target,
        len(result),
        time.perf_counter() - started_at,
    )

    return result[OUTPUT_COLUMNS]