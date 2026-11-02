import logging
import time

import pandas as pd
from pmdarima import auto_arima

logger = logging.getLogger(__name__)


def predict_with_auto_arima(exchange_rates: pd.DataFrame,horizon: int = 30,validate_freshness: bool = True,) -> pd.DataFrame:

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
        "UpperBound",
    ]

    if exchange_rates.empty:
        logger.warning("No historical exchange rates provided.")
        return pd.DataFrame(columns=output_columns)

    pairs = exchange_rates[
        ["BaseCurrency", "TargetCurrency"]
    ].drop_duplicates()

    if len(pairs) != 1:
        raise ValueError(
            "predict_with_auto_arima expects exactly one currency pair."
        )

    base, target = pairs.iloc[0]

    history = exchange_rates[["Date", "Rate"]].copy()

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
        "AutoARIMA started for %s/%s: %d observations, horizon=%d days",
        base,
        target,
        len(history),
        horizon,
    )

    model = auto_arima(
        history["Rate"].to_numpy(),
        seasonal=False,
        stepwise=True,
        suppress_warnings=True,
        error_action="ignore",
    )

    predictions, confidence_intervals = model.predict(
        n_periods=horizon,
        return_conf_int=True,
        alpha=0.05,
    )

    future_dates = pd.date_range(
        start=history["Date"].max() + pd.Timedelta(days=1),
        periods=horizon,
        freq="D",
    )

    result = pd.DataFrame({
        "Date": future_dates,
        "PredictedRate": predictions,
        "LowerBound": confidence_intervals[:, 0],
        "UpperBound": confidence_intervals[:, 1],
    })

    logger.info(
        "AutoARIMA finished for %s/%s: %d predictions in %.2f seconds",
        base,
        target,
        len(result),
        time.perf_counter() - started_at,
    )

    return result[output_columns]