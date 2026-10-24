from datetime import date

import pandas as pd

from szakdolgozat_backend.snapshots.store import Snapshot


def SelectedDateNews(
    snapshot: Snapshot,
    FromDate: date,
    ToDate: date,
) -> pd.DataFrame:
    """
    Returns news articles between FromDate and ToDate.

    The returned DataFrame contains the original FactNews columns.
    """

    if FromDate > ToDate:
        raise ValueError("FromDate cannot be later than ToDate.")

    dates = snapshot.DimDates.copy()
    dates["Date"] = pd.to_datetime(
        dates["Date"],
        errors="coerce",
    ).dt.normalize()

    def resolve_date_id(date_value: date) -> object:
        if not isinstance(date_value, date):
            raise TypeError("Date values must be date instances.")

        parsed_date = pd.Timestamp(date_value).normalize()

        date_matches = dates.loc[
            dates["Date"].eq(parsed_date),
            "DateID",
        ].unique()

        if len(date_matches) != 1:
            raise ValueError(
                f"Unknown or ambiguous date: {date_value}"
            )

        return date_matches[0]

    from_date_id = resolve_date_id(FromDate)
    to_date_id = resolve_date_id(ToDate)

    fact_news = snapshot.FactNews

    mask = (
        fact_news["DateID"].ge(from_date_id)
        & fact_news["DateID"].le(to_date_id)
    )

    return (
        fact_news.loc[mask]
        .sort_values("DateID")
        .reset_index(drop=True)
    )


def resolve_source_id(
    snapshot: Snapshot,
    source_name: str,
) -> object:
    """Resolve a source name to exactly one SourceID."""

    sources = snapshot.DimSources

    matches = sources.loc[
        sources["SourceName"].eq(source_name),
        "SourceID",
    ].unique()

    if len(matches) != 1:
        raise ValueError(
            f"Unknown or ambiguous source: {source_name}"
        )

    return matches[0]


def resolve_category_id(
    snapshot: Snapshot,
    category_name: str,
) -> object:
    """Resolve a category name to exactly one CategoryID."""

    categories = snapshot.DimCategories

    matches = categories.loc[
        categories["CategoryName"].eq(category_name),
        "CategoryID",
    ].unique()

    if len(matches) != 1:
        raise ValueError(
            f"Unknown or ambiguous category: {category_name}"
        )

    return matches[0]


def NewsFilter(
    snapshot: Snapshot,
    mainData: pd.DataFrame,
    SourceFilter: str | None = None,
    CategoryFilter: str | None = None,
) -> pd.DataFrame:
    """
    Filter the date-selected news by at most one dimension.

    Returns the filtered news DataFrame.
    """

    if SourceFilter is not None and CategoryFilter is not None:
        raise ValueError(
            "SourceFilter and CategoryFilter cannot be used together."
        )

    if CategoryFilter is not None:
        category_id = resolve_category_id(
            snapshot,
            CategoryFilter,
        )

        return mainData.loc[
            mainData["CategoryID"].eq(category_id)
        ].reset_index(drop=True)

    if SourceFilter is not None:
        source_id = resolve_source_id(
            snapshot,
            SourceFilter,
        )

        return mainData.loc[
            mainData["SourceID"].eq(source_id)
        ].reset_index(drop=True)

    return mainData


def group_news_by_source(news: pd.DataFrame) -> pd.DataFrame:
    """Count news articles per source."""

    return (
        news.groupby("SourceID")
        .size()
        .reset_index(name="Count")
    )


def group_news_by_category(news: pd.DataFrame) -> pd.DataFrame:
    """Count news articles per category."""

    return (
        news.groupby("CategoryID")
        .size()
        .reset_index(name="Count")
    )

def enrich_news_with_dimensions(
    snapshot: Snapshot,
    news: pd.DataFrame,
) -> pd.DataFrame:
    """
    Adds Date, SourceName and CategoryName to FactNews records.
    """

    # Csak a szükséges DIM-oszlopokat használjuk.
    dates = snapshot.DimDates[["DateID", "Date"]].copy()
    sources = snapshot.DimSources[["SourceID", "SourceName"]].copy()
    categories = snapshot.DimCategories[
        ["CategoryID", "CategoryName"]
    ].copy()

    dates["Date"] = pd.to_datetime(
        dates["Date"],
        errors="coerce",
    ).dt.date

    result = news.merge(
        dates,
        on="DateID",
        how="left",
        validate="many_to_one",
    )

    result = result.merge(
        sources,
        on="SourceID",
        how="left",
        validate="many_to_one",
    )

    result = result.merge(
        categories,
        on="CategoryID",
        how="left",
        validate="many_to_one",
    )

    return result


def build_media_dataset(
    snapshot: Snapshot,
    news: pd.DataFrame,
) -> dict:
    """
    Builds the table and both chart aggregations.
    """

    enriched = enrich_news_with_dimensions(snapshot, news)

    # Táblázat
    table = (
        enriched[
            ["Date", "SourceName", "CategoryName", "Title", "Url"]
        ]
        .rename(columns={"Url": "URL"})
        .sort_values("Date")
        .reset_index(drop=True)
    )

    # Donut diagram: kategóriánkénti darabszám
    by_category = (
        enriched.groupby("CategoryID")
        .size()
        .rename("Count")
        .reset_index()
        .merge(
            snapshot.DimCategories[["CategoryID", "CategoryName"]],
            on="CategoryID",
            how="left",
            validate="many_to_one",
        )
        .rename(columns={"CategoryName": "Name"})
        [["Name", "Count"]]
        .sort_values("Count", ascending=False)
        .reset_index(drop=True)
    )

    # Fordított oszlopdiagram: forrásonkénti darabszám
    by_source = (
        enriched.groupby("SourceID")
        .size()
        .rename("Count")
        .reset_index()
        .merge(
            snapshot.DimSources[["SourceID", "SourceName"]],
            on="SourceID",
            how="left",
            validate="many_to_one",
        )
        .rename(columns={"SourceName": "Name"})
        [["Name", "Count"]]
        .sort_values("Count", ascending=False)
        .reset_index(drop=True)
    )

    # NaN / NaT értékek szabályos JSON-kompatibilis None értékké alakítása.
    table = table.astype(object).where(table.notna(), None)
    by_category = by_category.astype(object).where(
        by_category.notna(), None
    )
    by_source = by_source.astype(object).where(
        by_source.notna(), None
    )

    return {
        "table": table.to_dict(orient="records"),
        "by_category": by_category.to_dict(orient="records"),
        "by_source": by_source.to_dict(orient="records"),
    }
