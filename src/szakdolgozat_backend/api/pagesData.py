from datetime import date
from fastapi.encoders import jsonable_encoder
from typing_extensions import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from szakdolgozat_backend.response_models.chartResponses import DailyHeatmapResponse
from szakdolgozat_backend.response_models.mediaResponses import MediaAnalyticsResponse
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
    ToDate: date,
    SourceFilter: str | None = None,
    CategoryFilter: str | None = None,
    IncludeMain: bool = True,
):
    # return értékek 
    # táblázat: Date, SourceName, CategoryName, Title, URL
    # Döntött oszlop diagramm: Y=SourceName, X=Count
    # Donut diagramm: jelmagyarázat=CategoryName, érték=Count

    # két féle adat megadása:
    # main: Category és Source szűrők nélkül
    # szűrt: Category és Source szűrőkkel
    if StartDate > ToDate:
        raise HTTPException(
            status_code=422,
            detail="StartDate cannot be later than ToDate.",
        )

    if SourceFilter is not None and CategoryFilter is not None:
        raise HTTPException(
            status_code=422,
            detail="SourceFilter and CategoryFilter cannot be used together.",
        )
    
    snapshot = request.app.state.snapshot
    try:
        mainData = SelectedDateNews(snapshot, StartDate, ToDate)
        #ha van szűrő akkor elvégezzük a szűrést, ha nincs akkor a mainData-t használjuk a további feldolgozáshoz
        has_filter = (SourceFilter is not None or CategoryFilter is not None)

        # Csak akkor kell alapadatokat visszaküldeni,
        # ha IncludeMain=True.
        main_response = (
            build_media_dataset(snapshot, mainData)
            if IncludeMain
            else None
        )
        
        # Szűrt adatok csak aktív szűrő esetén.
        if has_filter:
            filteredNews = NewsFilter(
                snapshot=snapshot,
                mainData=mainData,
                SourceFilter=SourceFilter,
                CategoryFilter=CategoryFilter,
            )

            filtered_response = build_media_dataset(
                snapshot,
                filteredNews,
            )
        else:
            filtered_response = None

        #JSON visszaküldése
        return MediaAnalyticsResponse(
            main=main_response,
            filtered=filtered_response,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc