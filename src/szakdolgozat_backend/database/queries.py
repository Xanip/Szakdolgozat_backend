from .connection import get_connection, close_connection
from sqlalchemy import text

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
