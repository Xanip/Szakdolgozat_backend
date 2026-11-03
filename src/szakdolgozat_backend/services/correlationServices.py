"""
Functions for transforming data into the forms SciPy expects for correlation calculations.
Functions that use SciPy to calculate correlation coefficients and p-values for the data.
Functions that call a local llm in the container to analyze the correlation results and provide a summary of the findings.

Tasks in other files:
- eldönteni mit is akarunk megjelníteni a FrontEnd-en, az alapján hozzuk létre a correlationResults DataFrame-t.
- snapshots/store: felvenni a correlationResults DataFrame-t a snapshotba, hogy az eredményeket el lehessen menteni késöbbi lekérdezésekhez.
- api/pagesData: enpoint megírása, először kiolvasni a correlationResults DataFrame-t a snapshotból, majd ha nincs benne az adott párra vonatkozó eredmény, akkor kiszámolni és elmenteni a snapshotba.
                    Fontos, hogy szinkron legyen, egyszerre csak egy kérés számoljon, a többiek várjanak, amíg az eredmény elkészül. 
                    A snapshotot lockolni kell, hogy ne legyen race condition.
"""

from datetime import date
import numpy as np
import pandas as pd
import scipy
from szakdolgozat_backend.response_models.correlationResponses import AnyalysisPeriod, CorrelationResponse, CorrelationResponseForLLM
from szakdolgozat_backend.services.llmServices import generate_llm_response
from szakdolgozat_backend.snapshots.store import Snapshot

def get_categories_number_distribution(snapshot: Snapshot) -> pd.DataFrame:
    """
    Returns a DataFrame with the dateID and the number of news articles per category for each date.
    DataFrame columns: DateID, CategoryName, Count | Count is 0 if there are no articles for that category on that date.
    """

    fact_news = snapshot.FactNews.copy()
    categories = snapshot.DimCategories.copy()
    if fact_news.empty:
        return pd.DataFrame(columns=["DateID", "CategoryName", "CategoryCount"])

    first_news_date = fact_news["DateID"].min()
    last_news_date = fact_news["DateID"].max()
    # Select DateID, CategoryID, Count(*) FROM FactNews GROUP BY DateID, CategoryID
    category_counts = (
        fact_news.groupby(["DateID", "CategoryID"])
        .size()
        .reset_index(name="CategoryCount")
    )

    # Each date has to have each category even if there are no articles for that category on that date. if there are no articles for that category on that date, the count should be 0.
    all_dates = snapshot.FactExchangeRates.loc[
        snapshot.FactExchangeRates["DateID"].between(
            first_news_date, last_news_date
        ),
        "DateID",
    ].unique()
    all_categories = categories["CategoryID"]
    all_combinations = pd.MultiIndex.from_product(
        [all_dates, all_categories], names=["DateID", "CategoryID"]
    )

    # Reindex the category_counts DataFrame with the all_combinations MultiIndex
    category_counts = category_counts.set_index(["DateID", "CategoryID"]).reindex(all_combinations).fillna(0).reset_index()

    # Merge with categories to get CategoryName
    result = category_counts.merge(categories, on="CategoryID", how="left").loc[:, ["DateID", "CategoryName", "CategoryCount"]]

    return result



def get_daily_percent_change_on_exchange_rate(snapshot: Snapshot, BaseCurrency: str, TargetCurrency: str) -> pd.DataFrame:
    """
    Returns a DataFrame with the dateID and the daily percent change of the exchange rate for each date.
    DataFrame columns: DateID, PercentChange | PercentChange is 0 if there is no previous rate to compare to, which is the case for the first date in the series.
    """

    fact_exchange = snapshot.FactExchangeRates.copy()
    currencies = snapshot.DimCurrencies.copy()
    # Filter the DataFrame for the specified BaseCurrencyID and CurrencyID
    def resolve_currency_id(currency: str) -> object:
        matches = currencies.loc[
            currencies["CurrencyCode"].eq(currency),
            "CurrencyID",
        ].unique()

        if len(matches) != 1:
            raise ValueError(f"Unknown or ambiguous currency: {currency}")

        return matches[0]

    base_currency_id = resolve_currency_id(BaseCurrency)
    target_currency_id = resolve_currency_id(TargetCurrency)
    fact_exchange = fact_exchange[
        (fact_exchange["BaseCurrencyID"] == base_currency_id) &
        (fact_exchange["CurrencyID"] == target_currency_id)
    ]

    # Sort by DateID to ensure correct calculation of percent change
    fact_exchange = fact_exchange.sort_values(by="DateID")

    # Calculate daily percent change
    fact_exchange["PercentChange"] = fact_exchange["Rate"].pct_change() * 100

    # Fill NaN values with 0 for the first entry of each group
    fact_exchange["PercentChange"] = fact_exchange["PercentChange"].fillna(0)

    result = fact_exchange.loc[:, ["DateID", "Rate", "PercentChange"]].rename(
        columns={"Rate": "ExchangeRate"}
    )
    
    return result

"""végcél: 
    -hírek kategóriáinak darabszáma per nap
    -árfolyam változás előző mért értékhez képest az egész árfolyamra vonatkozóan, rate helyett percentChange
    -PercentChange és kategóriaEloszlás: kategóriaEloszlásból törölni a napokat amikhez nincs percentChange, precentChange-ből törölni a napokat amikhez nincs kategóriaEloszlás
                                        Azaz egyezzenek a napok, hogy a két sorozat összehasonlítható legyen.

    -Ezeket lehet majd átadni a SciPy-nek: a percentChange sorozatot valamint a kategóriaEloszlás sorozatot, hogy kiszámolja a korrelációt és a p-value-t.
"""

def get_correlation_data(snapshot: Snapshot, BaseCurrency: str, TargetCurrency: str) -> pd.DataFrame:
    """
    Returns a DataFrame with the dateID, daily percent change of the exchange rate, and the number of news articles per category for each date.
    DataFrame columns: DateID, ExchangeRate, PercentChange, CategoryName, CategoryCount
        PercentChange is 0 if there is no previous rate to compare to, which is the case for the first date in the series. 
        CategoryCount is 0 if there are no articles for that category on that date.
    """

    # kategóriánként kapott korreláció vizsgálat
    # ha kategóriánként akarjuk mejd az adatokat látni akkor kategória szűrőket kell majd alkalmaznunk
    # kategóriánként, majd úgy végrehajtani a SciPy korreláció számítást.

    percent_change_df = get_daily_percent_change_on_exchange_rate(snapshot, BaseCurrency, TargetCurrency)
    category_distribution_df = get_categories_number_distribution(snapshot)

    if category_distribution_df.empty:
        return pd.DataFrame(
            columns=[
                "DateID",
                "ExchangeRate",
                "PercentChange",
                "CategoryName",
                "CategoryCount",
                "Date",
            ]
        )

    # first get the dates that are present in both DataFrames
    common_dates = set(percent_change_df["DateID"]).intersection(set(category_distribution_df["DateID"]))

    # filter both DataFrames to only include the common dates
    percent_change_df = percent_change_df[percent_change_df["DateID"].isin(common_dates)]
    category_distribution_df = category_distribution_df[category_distribution_df["DateID"].isin(common_dates)]

    # Merge the two DataFrames on DateID
    merged_df = pd.merge(percent_change_df, category_distribution_df, on="DateID", how="inner")

    # Add Date column by converting DateID to date using the snapshot's DimDates table
    dates_df = snapshot.DimDates.copy()
    merged_df = pd.merge(merged_df, dates_df[["DateID", "Date"]], on="DateID", how="left")

    return merged_df

def get_correlation_results(snapshot: Snapshot, BaseCurrency: str, TargetCurrency: str, correlation_data_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Returns a DataFrame with the correlation results for each category.
    DataFrame columns: CategoryName, pearson_r, pearson_p_value, spearman_r, spearman_p_value, sample_size
    """

    if correlation_data_df is None:
        correlation_data_df = get_correlation_data(snapshot, BaseCurrency, TargetCurrency)
    
    # Group by CategoryName and calculate correlation coefficient and p-value for each category
    correlation_results = []
    for category, group in correlation_data_df.groupby("CategoryName"):
        numeric_group = group[["PercentChange", "CategoryCount"]].apply(
            pd.to_numeric, errors="coerce"
        )
        finite_values = np.isfinite(numeric_group).all(axis=1)
        valid_group = numeric_group.loc[finite_values]
        sample_size = len(valid_group)

        result = {
            "CategoryName": category,
            "pearson_r": None,
            "pearson_p_value": None,
            "spearman_r": None,
            "spearman_p_value": None,
            "sample_size": sample_size,
        }

        if (
            sample_size >= 2
            and valid_group["PercentChange"].nunique() >= 2
            and valid_group["CategoryCount"].nunique() >= 2
        ):
            pearson_r, pearson_p_value = scipy.stats.pearsonr(
                valid_group["PercentChange"], valid_group["CategoryCount"]
            )
            spearman_r, spearman_p_value = scipy.stats.spearmanr(
                valid_group["PercentChange"], valid_group["CategoryCount"]
            )

            for name, value in (
                ("pearson_r", pearson_r),
                ("pearson_p_value", pearson_p_value),
                ("spearman_r", spearman_r),
                ("spearman_p_value", spearman_p_value),
            ):
                if np.isfinite(value):
                    result[name] = float(value)

        correlation_results.append(result)

    result_columns = [
        "CategoryName",
        "pearson_r",
        "pearson_p_value",
        "spearman_r",
        "spearman_p_value",
        "sample_size",
    ]
    results_df = pd.DataFrame(correlation_results, columns=result_columns)

    # mi történik itt ha a pearson_p_value vagy spearman_p_value NaN? 
    # BH correction for Pearson p-values
    pearson_p_values = pd.to_numeric(
        results_df["pearson_p_value"], errors="coerce"
    )
    valid_pearson = pearson_p_values.notna() & np.isfinite(pearson_p_values)

    results_df["pearson_adjusted_p_value"] = None

    if valid_pearson.any():
        results_df.loc[valid_pearson,"pearson_adjusted_p_value"] = scipy.stats.false_discovery_control(
            pearson_p_values.loc[valid_pearson].astype(float),
            method="bh"
        )
        
    # BH correction for Spearman p-values
    spearman_p_values = pd.to_numeric(
        results_df["spearman_p_value"], errors="coerce"
    )
    valid_spearman = spearman_p_values.notna() & np.isfinite(spearman_p_values)
    results_df["spearman_adjusted_p_value"] = None

    if valid_spearman.any():
        results_df.loc[valid_spearman,"spearman_adjusted_p_value"] = scipy.stats.false_discovery_control(
            spearman_p_values.loc[valid_spearman].astype(float),
            method="bh"
        )

    return results_df

async def analyze_correlation_results_with_llm(correlation_results_df: pd.DataFrame, BaseCurrency: str, TargetCurrency: str, start_date: date | None, end_date: date | None) -> str:
    """
    Analyzes the correlation results using a local LLM and returns a summary of the findings.
    """
    # Convert the DataFrame to a JSON representation for the LLM in the form of CorrelationResponse 
    # without the correlation_analysis yet.
    correlation_rows = correlation_results_df.rename(
        columns={"CategoryName": "category_name"}
    )
    correlation_json = CorrelationResponseForLLM(
        currency_pair=f"{BaseCurrency}/{TargetCurrency}",
        analysis_period=AnyalysisPeriod(
            start_date=start_date,
            end_date=end_date
        ),
        correlation_results=correlation_rows.to_dict(orient="records")
    )

    # Here you would call your local LLM with the correlation_results_str as input
    # For example:
    # llm_response = call_local_llm(correlation_results_str)
    # return llm_response
    correlation_json = correlation_json.model_dump_json(indent=4)
    CORRELATION_ANALYSIS_PROMPT = f"""
    You are a financial data analyst specializing in FX markets and statistical analysis.

    ## Objective
    Interpret the provided correlation results between daily exchange rate percentage changes and news article counts by category. Produce a concise, statistically accurate report.

    ## Input Fields
    The input JSON contains `currency_pair`, `analysis_period`, and `correlation_results`. Each result includes:

    - `category_name`: News category.
    - `pearson_r`: Pearson correlation coefficient (-1 to +1), measuring linear association.
    - `pearson_p_value`: Original, unadjusted Pearson p-value.
    - `pearson_adjusted_p_value`: Benjamini-Hochberg (BH) adjusted Pearson p-value.
    - `spearman_r`: Spearman correlation coefficient (-1 to +1), measuring monotonic association.
    - `spearman_p_value`: Original, unadjusted Spearman p-value.
    - `spearman_adjusted_p_value`: BH adjusted Spearman p-value.
    - `sample_size`: Number of paired observations.

    ## Interpretation Rules
    - Correlation coefficients range from -1 to +1. The sign indicates direction; absolute magnitude indicates strength. Values near 0 indicate weak or no association; values closer to +1 or -1 indicate stronger association. Describe strength cautiously.
    - P-values range from 0 to 1. Smaller values provide stronger evidence against the null hypothesis of no association. A p-value is NOT the probability that the relationship is true.
    - Determine statistical significance exclusively from the BH-adjusted p-values. A result is significant only if its adjusted p-value is strictly below 0.05. Values >= 0.05 are not significant, regardless of the original p-value or coefficient magnitude.
    - Interpret Pearson and Spearman independently. Report their significant findings and directions accurately.
    - Statistical significance does not imply strong, economically meaningful, or causal relationships.
    - Consider sample size, but do not claim statistical power is sufficient without supporting evidence.
    - Do not infer causation, market explanations, or events absent from the input.
    - Ignore null or unavailable values. Never infer missing results.

    ## Output
    Write in English, maximum 1000 characters including spaces. Use concise, professional report language. Focus on the most meaningful findings, highlighting significant categories and correlation directions. If none are significant, state so explicitly. Avoid listing every category. No headings, bullets, markdown, JSON, or methodology explanation. Return only the analytical summary.

    ## Correlation Results

    {correlation_json}
    """
    return await generate_llm_response(CORRELATION_ANALYSIS_PROMPT)


async def analyze_cached_correlation_with_llm(response: CorrelationResponse) -> str:
    """Analyze a previously cached correlation response without recalculating it."""
    BaseCurrency, TargetCurrency = response.currency_pair.split("/", maxsplit=1)
    correlation_results_df = pd.DataFrame(
        [row.model_dump() for row in response.correlation_results]
    ).rename(columns={"category_name": "CategoryName"})

    return await analyze_correlation_results_with_llm(
        correlation_results_df,
        BaseCurrency,
        TargetCurrency,
        start_date=response.analysis_period.start_date,
        end_date=response.analysis_period.end_date,
    )


def dateID_to_date(snapshot: Snapshot, dateID: int) -> date:
    """
    Converts a dateID to a date object.
    Assumes dateID is in the format YYYYMMDD.
    """
    dates = snapshot.DimDates
    date_row = dates[dates["DateID"] == dateID]
    if date_row.empty:
        raise ValueError(f"dateID {dateID} not found in DimDates.")
    value = date_row.iloc[0]["Date"]
    return value.date() if hasattr(value, "date") else date.fromisoformat(str(value))

def get_exchange_rate_series(snapshot: Snapshot, BaseCurrency: str, TargetCurrency: str) -> pd.DataFrame:
    """
    Returns a DataFrame with the date and the exchange rate for each date.
    DataFrame columns: Date, ExchangeRate
    """
    fact_exchange = snapshot.FactExchangeRates.copy()
    if snapshot.FactNews.empty:
        return pd.DataFrame(columns=["Date", "ExchangeRate"])

    first_news_date = snapshot.FactNews["DateID"].min()
    last_news_date = snapshot.FactNews["DateID"].max()
    currencies = snapshot.DimCurrencies.copy()

    def resolve_currency_id(currency: str) -> object:
        matches = currencies.loc[
            currencies["CurrencyCode"].eq(currency),
            "CurrencyID",
        ].unique()

        if len(matches) != 1:
            raise ValueError(f"Unknown or ambiguous currency: {currency}")

        return matches[0]

    fact_exchange = fact_exchange[
        (fact_exchange["BaseCurrencyID"] == resolve_currency_id(BaseCurrency))
        & (fact_exchange["CurrencyID"] == resolve_currency_id(TargetCurrency))
        & fact_exchange["DateID"].between(first_news_date, last_news_date)
    ].sort_values("DateID")

    #change dateID to date
    fact_exchange["Date"] = fact_exchange["DateID"].apply(lambda x: dateID_to_date(snapshot, x))

    exchange_rate_series = fact_exchange.loc[:, ["Date", "Rate"]].rename(
        columns={"Rate": "ExchangeRate"}
    )
    return exchange_rate_series