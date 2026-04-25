from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RoofAnalysisStatus(StrEnum):
    ANALYZED = "analyzed"
    SKIPPED = "skipped"


class RoofOutline(BaseModel):
    source: str
    model_id: str
    class_name: str = "Building"
    polygon_pixels: list[list[int]]
    area_pixels: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class RoofAnalysis(BaseModel):
    status: RoofAnalysisStatus
    roof_outlines: list[RoofOutline] = Field(default_factory=list)
    roof_planes: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
