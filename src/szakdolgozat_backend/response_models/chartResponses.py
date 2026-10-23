import pandas as pd
from pandas import DataFrame
from pydantic import BaseModel

def exchangeRateChartResponse(
    chartData: DataFrame | None,
    dim_dates: DataFrame,
) -> dict:
    chart_data = None
    if chartData is not None:
        dates = dim_dates[["DateID", "Date"]].copy()
        dates["Date"] = pd.to_datetime(dates["Date"], errors="coerce")
        chart_data = chartData.merge(
            dates,
            on="DateID",
            how="left",
            validate="many_to_one",
        )

    return {
        "lineChart_X": chart_data["Date"].dt.strftime("%Y-%m-%d").tolist() if chart_data is not None else [],
        "lineChart_Y": chart_data["Rate"].tolist() if chart_data is not None else [],
    }

def waterfallVarianceResponse(waterfall_variance: DataFrame | None) -> dict:
    return {
        "waterfallVarianceChart_X": waterfall_variance["Year_Month"].astype(str).tolist() if waterfall_variance is not None else [],
        "waterfallVarianceChart_Y": waterfall_variance["Variance"].tolist() if waterfall_variance is not None else [],
    }

class DailyHeatmapResponse(BaseModel):
    x_data: list[str]
    y_data: list[str]
    data: list[list[float | None]]