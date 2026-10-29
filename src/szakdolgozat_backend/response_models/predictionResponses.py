from datetime import date
from pydantic import BaseModel, ConfigDict


class PredictionPointResponse(BaseModel):
    date: date
    predictedRate: float
    lowerBound: float
    upperBound: float


class PredictionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    baseCurrency: str
    targetCurrency: str
    predictions: dict[str, list[PredictionPointResponse]]