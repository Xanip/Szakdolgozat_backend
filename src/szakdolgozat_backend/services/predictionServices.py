from datetime import date

import pandas as pd 
from szakdolgozat_backend.calculations.predictors.prophet import predict_with_prophet
from szakdolgozat_backend.services.ratesServices import SelectedRateChart
from szakdolgozat_backend.snapshots.store import Snapshot

#prediction model names like PROPHET, ARIMA, etc.
class PredictionModel:
    PROPHET = "PROPHET"
    #ARIMA = "ARIMA"

PREDICTORS = {
    PredictionModel.PROPHET: predict_with_prophet,
    # PredictionModel.ARIMA: predict_with_arima,
}

def get_prediction(
        snapshot: Snapshot, 
        predictionModel: str,
        BaseCurrency: str, 
        TargetCurrency: str, 
        FromDate: date | None = None, 
        ToDate: date | None = None
) -> pd.DataFrame:

    history = get_prediction_history(snapshot, BaseCurrency, TargetCurrency, FromDate, ToDate)
    
    model_name = predictionModel.upper()
    predictor = PREDICTORS.get(model_name)

    if predictor is None:
        raise ValueError(f"Invalid prediction model: {predictionModel}")

    if history.empty:
        return pd.DataFrame(
            columns=[
                "Date",
                "PredictedRate",
                "LowerBound",
                "UpperBound",
            ]
        )
    
    return  predictor(history)

def get_all_predictions(
    snapshot: Snapshot,
    BaseCurrency: str,
    TargetCurrency: str,
    FromDate: date | None = None,
    ToDate: date | None = None,
) -> dict[str, pd.DataFrame]:
    history = get_prediction_history(
        snapshot,
        BaseCurrency,
        TargetCurrency,
        FromDate,
        ToDate,
    )

    if history.empty:
        return {
            model_name: pd.DataFrame(
                columns=[
                    "Date",
                    "PredictedRate",
                    "LowerBound",
                    "UpperBound",
                ]
            )
            for model_name in PREDICTORS
        }

    return {
        model_name: predictor(history.copy())
        for model_name, predictor in PREDICTORS.items()
    }

def get_prediction_history(snapshot: Snapshot, BaseCurrency: str, TargetCurrency: str, FromDate: date | None = None, ToDate: date | None = None) -> pd.DataFrame:
    """
    Joins the dataframes for predictions historical data.

    Args:
        BaseCurrency (str): The base currency code.
        TargetCurrency (str): The target currency code.

    Returns:
        pd.DataFrame: The joined dataframe containing historical data.

    """
    filtered_df = SelectedRateChart(snapshot, BaseCurrency, TargetCurrency, FromDate, ToDate)
    if filtered_df.empty:
        return pd.DataFrame(
            columns=["Date", "Rate", "BaseCurrency", "TargetCurrency"]
        )
    
    dim_dates = snapshot.DimDates[["DateID", "Date"]].copy()
    dim_dates["Date"] = pd.to_datetime(dim_dates["Date"], errors="raise").dt.normalize()

    filtered_df = filtered_df.merge(dim_dates, on="DateID", validate="many_to_one", how="left")
    
    result = (
        filtered_df[
            ["Date", "Rate"]
        ]
        .sort_values("Date")
        .reset_index(drop=True)
    )
    result["BaseCurrency"] = BaseCurrency
    result["TargetCurrency"] = TargetCurrency
    return result[
        ["Date", "Rate", "BaseCurrency", "TargetCurrency"]
    ]
