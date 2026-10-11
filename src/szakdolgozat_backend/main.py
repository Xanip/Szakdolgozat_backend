from fastapi import FastAPI

from szakdolgozat_backend.api.health import router as health_router

app = FastAPI()
app.include_router(health_router)
