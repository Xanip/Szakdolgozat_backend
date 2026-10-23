from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request
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