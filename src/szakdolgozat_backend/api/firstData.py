from fastapi import APIRouter

from szakdolgozat_backend.database.queries import *

router = APIRouter()

@router.get("/data/dim/authors")
def read_first_data():
    data = get_dim_author()
    return {"author_data": data}

@router.get("/data/dim/categories")
def read_first_data():
    data = get_dim_category()
    return {"category_data": data}

@router.get("/data/dim/currencies")
def read_first_data():
    data = get_dim_currency()
    return {"currency_data": data}

@router.get("/data/dim/dates")
def read_first_data():
    data = get_dim_date()
    return {"date_data": data}

@router.get("/data/dim/sources")
def read_first_data():
    data = get_dim_source()
    return {"source_data": data}

@router.get("/data/fact/exchangerates")
def read_first_data():
    data = get_fact_exchange()
    return {"exchange_rate_data": data}

@router.get("/data/fact/news")
def read_first_data():
    data = get_fact_news()
    return {"news_data": data}