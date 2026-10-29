import logging
import time

import pandas as pd
from prophet import Prophet

logger = logging.getLogger(__name__)


def predict_with_prophet(exchange_rates: pd.DataFrame, horizon: int = 30) -> pd.DataFrame:
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
        raise ValueError("horizon must be greater than zero")

    output_columns = [
        "Date",
        "PredictedRate",
        "LowerBound",
        "UpperBound"
    ]

    if exchange_rates.empty:
        logger.warning("No historical exchange rates provided.")
        return pd.DataFrame(columns=output_columns)

    # A függvény egyetlen devizapárt vár.
    pairs = exchange_rates[
        ["BaseCurrency", "TargetCurrency"]
    ].drop_duplicates()

    if len(pairs) != 1:
        raise ValueError(
            "predict_with_prophet expects exactly one currency pair."
        )

    base, target = pairs.iloc[0]

    history = exchange_rates[["Date", "Rate"]].rename(
        columns={"Date": "ds", "Rate": "y"}
    ).copy()

    history["ds"] = pd.to_datetime(history["ds"], errors="coerce")
    history["y"] = pd.to_numeric(history["y"], errors="coerce")

    history = (
        history.dropna(subset=["ds", "y"])
        .sort_values("ds")
        .drop_duplicates(subset=["ds"], keep="last")
    )

    if len(history) < 30:
        raise ValueError(
            f"Insufficient observations for {base}/{target}: "
            f"{len(history)}; at least 30 are required."
        )

    today = pd.Timestamp.today().normalize()
    last_date = history["ds"].max().normalize()

    if (today - last_date).days > 30:
        raise ValueError(
            f"Latest observation for {base}/{target} is stale: "
            f"{last_date.date()}."
        )

    logger.info("Prophet started for %s/%s: %d observations, horizon=%d days",base,target,len(history),horizon)

    model = Prophet()
    model.fit(history)

    future = model.make_future_dataframe(
        periods=horizon,
        freq="D",
        include_history=False,
    )

    forecast = model.predict(future)

    result = pd.DataFrame({
        "Date": forecast["ds"],
        "PredictedRate": forecast["yhat"],
        "LowerBound": forecast["yhat_lower"],
        "UpperBound": forecast["yhat_upper"]
    })

    logger.info(
        "Prophet finished for %s/%s: %d predictions in %.2f seconds",
        base,
        target,
        len(result),
        time.perf_counter() - started_at,
    )

    return result[output_columns]