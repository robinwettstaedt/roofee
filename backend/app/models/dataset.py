from pydantic import BaseModel


class DatasetSummary(BaseModel):
    name: str
    file_count: int
    files: list[str]
