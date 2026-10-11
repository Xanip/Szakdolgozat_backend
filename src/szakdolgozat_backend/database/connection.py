"""connecting to the MSSQL database for read only data access"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, Engine
from sqlalchemy import create_engine

class Settings(BaseSettings):
    CONNECTION_STRING: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

settings = Settings()

engine = create_engine(
    URL.create(
        "mssql+pyodbc",
        query={"odbc_connect": settings.CONNECTION_STRING}
    )
)

def get_connection():
    """returns a connection to the database"""
    return engine.connect()

def close_connection(conn):
    """closes the connection to the database"""
    conn.close()