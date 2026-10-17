from fastapi import FastAPI
from contextlib import asynccontextmanager

from szakdolgozat_backend.api.health import router as health_router
from szakdolgozat_backend.api.firstData import router as first_data_router
from szakdolgozat_backend.api.dataFrameTest import router as dataFrame_router
from szakdolgozat_backend.snapshots.loader import load_snapshot

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the initial snapshot
    snapshot = load_snapshot()
    app.state.snapshot = snapshot
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(health_router)
app.include_router(first_data_router)
app.include_router(dataFrame_router)