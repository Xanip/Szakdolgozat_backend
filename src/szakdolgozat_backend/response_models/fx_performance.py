from pandas import DataFrame
from szakdolgozat_backend.response_models.chartResponses import exchangeRateChartResponse, waterfallVarianceResponse

def create_fx_performance_response(
        dim_dates: DataFrame,
        
        #kpi kártyák adatai
        previousDayRate: float | None,
        changeSinceYesteray: float | None, 

        todaysRate: float | None, 

        firstRateInPeriod: float | None, 
        changeSinceTheStartOfPeriod: float | None, 

        #gráfok adatai
        exchangeRateData: DataFrame | None, 
        waterfall_variance: DataFrame | None
    ) -> dict:
    return {
        "todaysRate": todaysRate,
        "previousDayRate": previousDayRate,
        "firstRateInPeriod": firstRateInPeriod,

        "changeSinceYesteray": changeSinceYesteray,
        "changeSinceTheStartOfPeriod": changeSinceTheStartOfPeriod,

        "exchangeRateChart": exchangeRateChartResponse(exchangeRateData, dim_dates),
        "waterfallVarianceChart": waterfallVarianceResponse(waterfall_variance),
    }