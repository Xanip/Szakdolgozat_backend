from szakdolgozat_backend.database.queries import get_dataFrames
from szakdolgozat_backend.snapshots.store import Snapshot

def load_snapshot() -> Snapshot:
    """loads all tables and constructs a snapshot from queries"""
    dataFrames = get_dataFrames()
    snapshot = Snapshot(
        DimAuthors=dataFrames["DimAuthor"],
        DimCategories=dataFrames["DimCategory"],
        DimCurrencies=dataFrames["DimCurrency"],
        DimDates=dataFrames["DimDate"],
        DimSources=dataFrames["DimSource"],
        FactNews=dataFrames["FactNews"],
        FactExchangeRates=dataFrames["FactExchange"],
    )

    _calculate_daily_rate_percent_change(snapshot)
    return snapshot

def _calculate_daily_rate_percent_change(snapshot: Snapshot) -> None:
    """Előre kiszámítja a legfrissebb két elérhető nap valutapárjainak változását."""

    fact = snapshot.FactExchangeRates

    available_dates = (
        fact["DateID"]
        .dropna()
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    if len(available_dates) < 2:
        return

    previous_date_id = available_dates[-2]
    latest_date_id = available_dates[-1]

    current = fact.loc[
        fact["DateID"].eq(latest_date_id),
        ["BaseCurrencyID", "CurrencyID", "Rate"],
    ].rename(columns={"Rate": "CurrentRate"})

    previous = fact.loc[
        fact["DateID"].eq(previous_date_id),
        ["BaseCurrencyID", "CurrencyID", "Rate"],
    ].rename(columns={"Rate": "PreviousRate"})

    changes = current.merge(
        previous,
        on=["BaseCurrencyID", "CurrencyID"],
        how="left",
        validate="one_to_one",
    )

    valid_previous = changes["PreviousRate"].notna() & changes["PreviousRate"].ne(0)

    changes["DailyPercentChange"] = (
        (changes["CurrentRate"] - changes["PreviousRate"])
        / changes["PreviousRate"]
    ).where(valid_previous)

    currencies = snapshot.DimCurrencies[["CurrencyID", "CurrencyCode"]]

    changes = changes.merge(
        currencies.rename(
            columns={
                "CurrencyID": "BaseCurrencyID",
                "CurrencyCode": "BaseCurrency",
            }
        ),
        on="BaseCurrencyID",
        how="left",
        validate="many_to_one",
    )

    changes = changes.merge(
        currencies.rename(
            columns={
                "CurrencyID": "CurrencyID",
                "CurrencyCode": "TargetCurrency",
            }
        ),
        on="CurrencyID",
        how="left",
        validate="many_to_one",
    )

    snapshot.DailyRatePercentChange = changes[
        ["BaseCurrency", "TargetCurrency", "DailyPercentChange"]
    ]