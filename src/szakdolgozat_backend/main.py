from fastapi import FastAPI

from szakdolgozat_backend.api.health import router as health_router
from szakdolgozat_backend.api.firstData import router as first_data_router

app = FastAPI()
app.include_router(health_router)
app.include_router(first_data_router)
