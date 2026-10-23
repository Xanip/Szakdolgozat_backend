from datetime import date
from typing_extensions import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
import pandas as pd
from szakdolgozat_backend.response_models.chartResponses import DailyHeatmapResponse
from szakdolgozat_backend.services.ratesServices import SelectedRateChart, WaterfallVariance, LatestRate, PreviousRate, StartPeriodRate, DailyPercentChange, PeriodPercentChange 
from szakdolgozat_backend.response_models.fx_performance import create_fx_performance_response

router = APIRouter(prefix="/exchange-rates", tags=["Exchange Rates"])

@router.get("/pages/FX_performance")
def get_fx_performance_data(
    request: Request, 
    BaseCurrency: str = Query(..., min_length=3, max_length=3), 
    TargetCurrency: str = Query(..., min_length=3, max_length=3), 
    StartDate:  date | None = None,
    ToDate: date | None = None
    ):

    snapshot = request.app.state.snapshot

    try:
        exchangeRateData = SelectedRateChart(
            snapshot, 
            BaseCurrency, 
            TargetCurrency, 
            StartDate,
            ToDate,
        )
        previousDayRate = PreviousRate(
            snapshot,
            BaseCurrency,
            TargetCurrency,
            ToDate,
        )
        
        todaysRate = LatestRate(snapshot, rates_df=exchangeRateData)
        firstRateInPeriod = StartPeriodRate(snapshot, rates_df=exchangeRateData)
        changeSinceYesteray = DailyPercentChange(snapshot, BaseCurrency, TargetCurrency, latest_rate=todaysRate, previous_rate=previousDayRate)
        changeSinceTheStartOfPeriod = PeriodPercentChange(snapshot, BaseCurrency, TargetCurrency, latest_rate=todaysRate, start_period_rate=firstRateInPeriod)

        waterfall_variance = WaterfallVariance(
            snapshot,
            rates_df=exchangeRateData,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error occurred while fetching exchange rate data: {str(e)}",
        )

    return create_fx_performance_response(
            previousDayRate=previousDayRate,
            changeSinceYesteray=changeSinceYesteray,
            todaysRate=todaysRate,
            firstRateInPeriod=firstRateInPeriod,
            changeSinceTheStartOfPeriod=changeSinceTheStartOfPeriod,
            exchangeRateData=exchangeRateData,
            dim_dates=snapshot.DimDates,
            waterfall_variance=waterfall_variance,
        )

@router.get("/pages/Daily_heatmap")
def get_daily_heatmap_data(
    request: Request,
    Currencies: Annotated[
        list[Annotated[str, Query(min_length=3, max_length=3)]],
        Query(),
    ]
):
    # legnagyobb DateID a FactExchange táblában lesz a date amit használunk. 
    # Oszlopok a Currencies listában a valuták. Sorok az összes elérhető valuta.
    # Oszlopok a TargetCurrencies, sorok a BaseCurrencies.
    # A megadott valutákra kiszámoljuk a DailyPercentChange-t az összes létező valutával, és azokat visszaadjuk egy dictionary-ben, ahol a kulcs a pár, az érték pedig a napi változás százalékban.
    # ahol nem lesz érték az null lesz.


    # Y_data = az összes valuta (sorok)
    # X_data = a Currencies listában megadott valuták (oszlopok)
    # data = X_data * Y_data mátrix, ahol a cellákban a napi változás százalékban van, vagy null ha nincs érték.
    snapshot = request.app.state.snapshot

    X_data = [currency.upper() for currency in Currencies]
    Y_data = snapshot.DimCurrencies["CurrencyCode"].tolist()

    # Pénznempár -> előre kiszámított változás
    changes = snapshot.DailyRatePercentChange

    lookup = {
        (row.BaseCurrency, row.TargetCurrency): row.DailyPercentChange
        for row in changes.itertuples(index=False)
    }

    data = []

    for base_currency in Y_data:
        row_data = []

        for target_currency in X_data:
            if base_currency == target_currency:
                value = 0.0
            else:
                value = lookup.get((base_currency, target_currency))

                if pd.isna(value):
                    value = None

            row_data.append(value)

        data.append(row_data)

    return DailyHeatmapResponse(
        x_data=X_data,
        y_data=Y_data,
        data=data,
    )