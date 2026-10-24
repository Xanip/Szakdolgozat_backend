from datetime import date
from pydantic import BaseModel

class MediaTableRow(BaseModel):
    Date: date
    SourceName: str
    CategoryName: str
    Title: str
    URL: str


class MediaGroupCount(BaseModel):
    Name: str
    Count: int


class MediaDataset(BaseModel):
    table: list[MediaTableRow]
    by_category: list[MediaGroupCount]
    by_source: list[MediaGroupCount]


class MediaAnalyticsResponse(BaseModel):
    main: MediaDataset | None
    filtered: MediaDataset | None
