"""connecting to the MSSQL database for read only data access"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, Engine
from sqlalchemy import create_engine

class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int = 1433
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"
    DB_ENCRYPT: str = "yes"
    DB_TRUST_SERVER_CERTIFICATE: str = "yes"
    SNAPSHOT_CHUNK_SIZE: int = 100_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()

engine = create_engine(
    URL.create(
       "mssql+pyodbc",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=settings.DB_NAME,
        query={
            "driver": settings.DB_DRIVER,
            "Encrypt": settings.DB_ENCRYPT,
            "TrustServerCertificate": settings.DB_TRUST_SERVER_CERTIFICATE,
        },
    )
)

def get_engine() -> Engine:
    """returns the engine for the database"""
    return engine

def get_connection():
    """returns a connection to the database"""
    return engine.connect()

def close_connection(conn):
    """closes the connection to the database"""
    conn.close()