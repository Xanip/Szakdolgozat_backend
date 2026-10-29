from datetime import date
from fastapi.encoders import jsonable_encoder
from typing_extensions import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from szakdolgozat_backend.response_models.chartResponses import DailyHeatmapResponse
from szakdolgozat_backend.response_models.mediaResponses import MediaAnalyticsResponse
from szakdolgozat_backend.response_models.predictionResponses import PredictionPointResponse, PredictionResponse
from szakdolgozat_backend.services.predictionServices import PredictionModel, get_all_predictions, get_prediction
from szakdolgozat_backend.services.ratesServices import SelectedRateChart, WaterfallVariance, LatestRate, PreviousRate, StartPeriodRate, DailyPercentChange, PeriodPercentChange 
from szakdolgozat_backend.services.mediaServices import NewsFilter, SelectedDateNews, build_media_dataset
from szakdolgozat_backend.response_models.fx_performance import create_fx_performance_response
from pydantic import StringConstraints

from time import perf_counter

CurrencyCode = Annotated[
    str,
    StringConstraints(min_length=3, max_length=3),
]

router = APIRouter(prefix="/exchange-rates", tags=["Exchange Rates"])

@router.get("/pages")
def get_filter_data(request: Request):
    """Return DimTables for filtering in the front-end."""
    snapshot = request.app.state.snapshot

    return jsonable_encoder({
        "DimAuthors": snapshot.DimAuthors.to_dict(orient="records"),
        "DimCategories": snapshot.DimCategories.to_dict(orient="records"),
        "DimCurrencies": (snapshot.DimCurrencies.astype(object).where(snapshot.DimCurrencies.notna(), None).to_dict(orient="records")),
        "DimSources": snapshot.DimSources.to_dict(orient="records"),
    })

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
    Currencies: Annotated[list[CurrencyCode] | None, Query()] = None,
):
    # legnagyobb DateID a FactExchange táblában lesz a date amit használunk. 
    # Oszlopok a Currencies listában a valuták. Sorok az összes elérhető valuta.
    # Oszlopok a TargetCurrencies, sorok a BaseCurrencies.
    # A megadott valutákra kiszámoljuk a DailyPercentChange-t az összes létező valutával, és azokat visszaadjuk egy dictionary-ben, ahol a kulcs a pár, az érték pedig a napi változás százalékban.
    # ahol nem lesz érték az null lesz.


    # Y_data = az összes valuta (sorok)
    # X_data = a Currencies listában megadott valuták (oszlopok)
    # data = X_data * Y_data mátrix, ahol a cellákban a napi változás százalékban van, vagy null ha nincs érték.
    start = perf_counter()

    snapshot = request.app.state.snapshot
    matrix = snapshot.DailyRatePercentChangeMatrix

    print(f"Snapshot access: {perf_counter() - start:.4f} s")

    start = perf_counter()

    if Currencies:
        selected = [currency.upper() for currency in Currencies]

        unknown = set(selected) - set(matrix.columns)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown currencies: {sorted(unknown)}",
            )

        filtered = matrix.loc[:, selected]
    else:
        filtered = matrix

    print(f"Matrix selection: {perf_counter() - start:.4f} s")

    start = perf_counter()

    response = DailyHeatmapResponse(
        calculation_date=snapshot.DailyRatePercentChangeDate,
        x_data=filtered.columns.tolist(),
        y_data=filtered.index.tolist(),
        data=(
            filtered.astype(object)
            .where(filtered.notna(), None)
            .values.tolist()
        ),
    )
    print(f"Response preparation: {perf_counter() - start:.4f} s")

    return response


@router.get("/pages/Media_analytics")
def get_media_analytics_data(
    request: Request,
    StartDate:  date,
    ToDate: date
):
    # return értékek 
    # mainData = táblázat: Date, SourceName, CategoryName, Title, URL
    # ez a mainData, a Chart-okhoz szükséges adatokat a Front-End számolja ebből.
    # Ez a kereszt szűrők egyszerűsítésére szolgál és hogy csökkentsük a hálózati forgalmat.

    if StartDate > ToDate:
        raise HTTPException(
            status_code=422,
            detail="StartDate cannot be later than ToDate.",
        )
    
    snapshot = request.app.state.snapshot
    try:
        t0 = perf_counter()
        mainData = SelectedDateNews(snapshot, StartDate, ToDate)
        print(
            f"[MEDIA] SelectedDateNews: "
            f"{perf_counter() - t0:.3f}s | rows={len(mainData)}",
            flush=True,
        )

        # Csak akkor kell alapadatokat visszaküldeni,
        # ha IncludeMain=True.
        t0 = perf_counter()
        main_response = (
            build_media_dataset(snapshot, mainData)
        )
        print(
            f"[MEDIA] Build main: {perf_counter() - t0:.3f}s",
            flush=True,
        )

        #JSON visszaküldése
        return MediaAnalyticsResponse(
            main=main_response,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

@router.get("/pages/Prediction")
def get_prediction_data(
    request: Request, 
    BaseCurrency: str = Query(..., min_length=3, max_length=3), 
    TargetCurrency: str = Query(..., min_length=3, max_length=3), 
    StartDate:  date | None = None,
    ToDate: date | None = None
):
    snapshot = request.app.state.snapshot
    try:
        predictions = get_all_predictions(
            snapshot,
            BaseCurrency,
            TargetCurrency,
            StartDate,
            ToDate,
        )

        result = PredictionResponse(
            baseCurrency=BaseCurrency,
            targetCurrency=TargetCurrency,
            predictions={
                model_name: [
                    PredictionPointResponse(
                        date=row["Date"],
                        predictedRate=row["PredictedRate"],
                        lowerBound=row["LowerBound"],
                        upperBound=row["UpperBound"],
                    )
                    for _, row in df.iterrows()
                ]
                for model_name, df in predictions.items()
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error occurred while fetching prediction data: {str(e)}",
        )

    return result