import asyncio
from datetime import date
from fastapi.encoders import jsonable_encoder
from typing_extensions import Annotated
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from szakdolgozat_backend.response_models.chartResponses import DailyHeatmapResponse
from szakdolgozat_backend.response_models.correlationResponses import AnyalysisPeriod, CategoryCorrelationRow, CorrelationObservationRow, CorrelationResponse, ExchangeRateSeriesRow, LLMAnalysisResponse
from szakdolgozat_backend.response_models.mediaResponses import MediaAnalyticsResponse
from szakdolgozat_backend.response_models.predictionResponses import (
    PredictionHistoryPointResponse,
    PredictionPointResponse,
    PredictionResponse,
)
from szakdolgozat_backend.services.correlationServices import analyze_cached_correlation_with_llm, dateID_to_date, get_correlation_data, get_correlation_results, get_exchange_rate_series
from szakdolgozat_backend.services.predictionServices import (
    get_all_predictions_from_history,
    get_prediction_history,
)
from szakdolgozat_backend.services.ratesServices import SelectedRateChart, WaterfallVariance, LatestRate, PreviousRate, StartPeriodRate, DailyPercentChange, PeriodPercentChange 
from szakdolgozat_backend.services.mediaServices import NewsFilter, SelectedDateNews, build_media_dataset
from szakdolgozat_backend.response_models.fx_performance import create_fx_performance_response
from pydantic import StringConstraints

from time import perf_counter

logger = logging.getLogger(__name__)

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

@router.get("/pages/Prediction", response_model=PredictionResponse)
def get_prediction_data(
    request: Request, 
    BaseCurrency: str = Query(..., min_length=3, max_length=3), 
    TargetCurrency: str = Query(..., min_length=3, max_length=3), 
    StartDate:  date | None = None,
    ToDate: date | None = None
):
    snapshot = request.app.state.snapshot
    try:
        history = get_prediction_history(
            snapshot,
            BaseCurrency,
            TargetCurrency,
            StartDate,
            ToDate,
        )
        predictions = get_all_predictions_from_history(history)

        result = PredictionResponse(
            baseCurrency=BaseCurrency,
            targetCurrency=TargetCurrency,
            history=[
                PredictionHistoryPointResponse(
                    date=row["Date"].date()
                    if hasattr(row["Date"], "date")
                    else row["Date"],
                    rate=float(row["Rate"]),
                )
                for _, row in history.iterrows()
            ],
            predictions={
                model_name: [
                    PredictionPointResponse(
                        date=row["Date"].date()
                        if hasattr(row["Date"], "date")
                        else row["Date"],
                        predictedRate=float(row["PredictedRate"]),
                        lowerBound=float(row["LowerBound"]),
                        upperBound=float(row["UpperBound"]),
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


#TODO:
#   -DONE: Response model véglegesítése, a front end miatt
#   -DONE: Függvényeket írni amik visszadják a response modellhez szükséges adatokat.
#   -DONE: llm függvény befejezése
#   -DONE: lokálil ollama modell bekötése Containerbe
#   -Mi a helyzet a percentChange %-al az elemzésnél?
#   -LOCK miközben egy adott devizapáron elemzést csinálunk, ugyan arra a devizapárra ne lehessen újabb elemzést indítani, 
#       amíg az előző nem fejeződött be. Várakoztatja amíg az a számolás befejeződik és akkor már cache-ből adja vissza az eredményt.
@router.get("/pages/Correlation", response_model=CorrelationResponse)
async def get_correlation_page_data(
    request: Request, 
    BaseCurrency: str = Query(..., min_length=3, max_length=3), 
    TargetCurrency: str = Query(..., min_length=3, max_length=3)
):
    snapshot = request.app.state.snapshot
    BaseCurrency = BaseCurrency.upper()
    TargetCurrency = TargetCurrency.upper()
    cache_key = (BaseCurrency, TargetCurrency)
    correlation_lock = snapshot.CorrelationResponseLocks.setdefault(
        cache_key,
        asyncio.Lock(),
    )
    try:
        async with correlation_lock:
            if cache_key in snapshot.CorrelationResponseCache:
                return snapshot.CorrelationResponseCache[cache_key]

            exchange_rate_series_df = get_exchange_rate_series(snapshot, BaseCurrency, TargetCurrency)
            correlation_data_df = get_correlation_data(snapshot, BaseCurrency, TargetCurrency)
            if snapshot.FactNews.empty:
                data_start_date = None
                data_end_date = None
            else:
                data_start_date = dateID_to_date(
                    snapshot, snapshot.FactNews["DateID"].min()
                )
                data_end_date = dateID_to_date(
                    snapshot, snapshot.FactNews["DateID"].max()
                )

            correlation_results_df = get_correlation_results(snapshot, BaseCurrency, TargetCurrency, correlation_data_df=correlation_data_df)

            correlation_rows = correlation_results_df.rename(
                columns={"CategoryName": "category_name"}
            ).to_dict(orient="records")
            correlation_results = [
                CategoryCorrelationRow(**row) for row in correlation_rows
            ]

            paired_observations = []
            for observation_date, group in correlation_data_df.groupby("Date", sort=True):
                first_row = group.iloc[0]
                observation_date = (
                    observation_date.date()
                    if hasattr(observation_date, "date")
                    else date.fromisoformat(str(observation_date))
                )
                paired_observations.append(
                    CorrelationObservationRow(
                        date=observation_date,
                        exchange_rate=float(first_row["ExchangeRate"]),
                        daily_change_pct=float(first_row["PercentChange"]),
                        news_count={
                            row["CategoryName"]: int(row["CategoryCount"])
                            for _, row in group.iterrows()
                        },
                    )
                )

            exchange_rate_series = [
                ExchangeRateSeriesRow(
                    date=(
                        row["Date"].date()
                        if hasattr(row["Date"], "date")
                        else date.fromisoformat(str(row["Date"]))
                    ),
                    exchange_rate=float(row["ExchangeRate"]),
                )
                for _, row in exchange_rate_series_df.iterrows()
            ]

            result = CorrelationResponse(
                currency_pair=f"{BaseCurrency}/{TargetCurrency}",
                correlation_analysis="",
                analysis_period=AnyalysisPeriod(
                    start_date=data_start_date,
                    end_date=data_end_date,
                ),
                correlation_results=correlation_results,
                paired_observations=paired_observations,
                exchange_rate_series=exchange_rate_series,
            )

            snapshot.CorrelationResponseCache[cache_key] = result
            return result

    except Exception as e:
        logger.exception("Error occurred while fetching correlation data")
        raise HTTPException(
            status_code=500,
            detail=f"Error occurred while fetching correlation data: {type(e).__name__}: {e}"
        ) from e


@router.get("/pages/Correlation/LLM", response_model=LLMAnalysisResponse)
async def get_correlation_llm_analysis(
    request: Request,
    BaseCurrency: str = Query(..., min_length=3, max_length=3),
    TargetCurrency: str = Query(..., min_length=3, max_length=3),
):
    snapshot = request.app.state.snapshot
    BaseCurrency = BaseCurrency.upper()
    TargetCurrency = TargetCurrency.upper()
    cache_key = (BaseCurrency, TargetCurrency)
    correlation_lock = snapshot.CorrelationResponseLocks.setdefault(
        cache_key,
        asyncio.Lock(),
    )

    try:
        async with correlation_lock:
            cached_response = snapshot.CorrelationResponseCache.get(cache_key)
            if cached_response is None:
                raise HTTPException(
                    status_code=404,
                    detail="Correlation data has not been calculated for this currency pair.",
                )

            if cached_response.correlation_analysis:
                return LLMAnalysisResponse(analysis=cached_response.correlation_analysis)

            analysis = await analyze_cached_correlation_with_llm(cached_response)
            snapshot.CorrelationResponseCache[cache_key] = cached_response.model_copy(
                update={"correlation_analysis": analysis}
            )
            return LLMAnalysisResponse(analysis=analysis)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error occurred while generating correlation LLM analysis")
        raise HTTPException(
            status_code=500,
            detail=f"Error occurred while generating correlation LLM analysis: {type(e).__name__}: {e}"
        ) from e
