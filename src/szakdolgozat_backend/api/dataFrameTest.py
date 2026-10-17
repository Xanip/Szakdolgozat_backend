from fastapi import APIRouter, Request, Query

router = APIRouter()

@router.get("/dataframe/dim/authors")
def read_authors_dataFrame(request: Request):
    snapshot = request.app.state.snapshot
    data = snapshot.DimAuthors
    return {
        "row_count": len(data),
        "author_data": data.to_dict(orient="records")
    }

@router.get("/dataframe/dim/test")
def read_dimensions_dataFrame(request: Request):
    snapshot = request.app.state.snapshot

    final_data = []
    for table_name in ["DimAuthors", "DimCategories", "DimCurrencies", "DimDates", "DimSources"]:
        data = getattr(snapshot, table_name)
        final_data.append({
            "table_name": table_name,
            "row_count": len(data),
            "data": data.head(10).to_dict(orient="records")
        })
    return {
        "data": final_data
    }

@router.get("/dataframe/fact/test")
def read_dimensions_dataFrame(request: Request):
    snapshot = request.app.state.snapshot

    final_data = []
    for table_name in ["FactExchangeRates", "FactNews"]:
        data = getattr(snapshot, table_name)
        final_data.append({
            "table_name": table_name,
            "row_count": len(data),
            "data": data.head(10).to_dict(orient="records")
        })
    return {
        "data": final_data
    }

@router.get("/dataframe/memory_usage")
def read_dataFrame_memory_usage(request: Request):
    snapshot = request.app.state.snapshot
    return snapshot.get_snapshot_memory()