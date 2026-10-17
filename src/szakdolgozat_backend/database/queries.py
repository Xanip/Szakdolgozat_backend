import logging
import time

import pandas

from .connection import get_connection, close_connection, settings
from sqlalchemy import text
from pandas import read_sql

logger = logging.getLogger(__name__)

def get_dim_author():
    conn = get_connection()
    
    query = text("SELECT * FROM [DimAuthor]")
    
    result = conn.execute(query)
    data = result.fetchall()
    close_connection(conn)
    return [dict(row._mapping) for row in data] if data else []

def get_dim_category():
    conn = get_connection()
    
    query = text("SELECT * FROM [DimCategory]")
    
    result = conn.execute(query)
    data = result.fetchall()
    close_connection(conn)
    return [dict(row._mapping) for row in data] if data else []

def get_dim_currency():
    conn = get_connection()
    
    query = text("SELECT * FROM [DimCurrency]")
    
    result = conn.execute(query)
    data = result.fetchall()
    close_connection(conn)
    return [dict(row._mapping) for row in data] if data else []

def get_dim_date():
    conn = get_connection()
    
    query = text("SELECT * FROM [DimDate]")
    
    result = conn.execute(query)
    data = result.fetchall()
    close_connection(conn)
    return [dict(row._mapping) for row in data] if data else []

def get_dim_source():
    conn = get_connection()
    
    query = text("SELECT * FROM [DimSource]")
    
    result = conn.execute(query)
    data = result.fetchall()
    close_connection(conn)
    return [dict(row._mapping) for row in data] if data else []

def get_fact_news():
    conn = get_connection()
    
    query = text("SELECT * FROM [FactNews]")
    
    result = conn.execute(query)
    data = result.fetchall()
    close_connection(conn)
    return [dict(row._mapping) for row in data] if data else []

def get_fact_exchange():
    conn = get_connection()
    
    query = text("SELECT * FROM [FactExchange]")
    
    result = conn.execute(query)
    data = result.fetchall()
    close_connection(conn)
    return [dict(row._mapping) for row in data] if data else []


def _read_table_in_chunks(
    table: str,
    conn,
    chunk_size: int,
) -> pandas.DataFrame:
    """Read a table in bounded batches and combine the batches afterwards."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    query = text(f"SELECT * FROM [{table}]")
    chunks = []
    rows_read = 0

    for chunk_number, chunk in enumerate(
        read_sql(query, conn, chunksize=chunk_size),
        start=1,
    ):
        chunks.append(chunk)
        rows_read += len(chunk)
        logger.info(
            "Snapshot: read chunk table=%s chunk=%s rows=%s total_rows=%s",
            table,
            chunk_number,
            len(chunk),
            rows_read,
        )

    if not chunks:
        return pandas.DataFrame()

    if len(chunks) == 1:
        return chunks[0]

    return pandas.concat(chunks, ignore_index=True, copy=False)


def get_dataFrames() -> dict[str, pandas.DataFrame]:
    tables = [
        "DimAuthor",
        "DimCategory",
        "DimCurrency",
        "DimDate",
        "DimSource",
        "FactNews",
        "FactExchange",
    ]

    dataFrames = {}
    conn = get_connection()

    try:
        for table in tables:
            start = time.perf_counter()
            logger.info("Snapshot: starting table %s", table)

            df = _read_table_in_chunks(
                table,
                conn,
                settings.SNAPSHOT_CHUNK_SIZE,
            )

            elapsed = time.perf_counter() - start
            memory_bytes = int(
                df.memory_usage(index=True, deep=True).sum()
            )

            dataFrames[table] = df

            logger.info(
                "Snapshot: loaded %s | rows=%s | memory=%.2f MiB | time=%.2f s",
                table,
                len(df),
                memory_bytes / (1024 ** 2),
                elapsed,
            )

        return dataFrames
    finally:
        close_connection(conn)