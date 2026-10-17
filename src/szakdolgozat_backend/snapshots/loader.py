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
        FactExchangeRates=dataFrames["FactExchange"]
    )
    return snapshot