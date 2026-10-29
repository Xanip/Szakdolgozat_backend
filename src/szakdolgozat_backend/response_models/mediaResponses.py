from datetime import date
from pydantic import BaseModel

class MediaTableRow(BaseModel):
    Date: date
    SourceName: str
    CategoryName: str
    Title: str
    URL: str


class MediaDataset(BaseModel):
    table: list[MediaTableRow]


class MediaAnalyticsResponse(BaseModel):
    main: MediaDataset