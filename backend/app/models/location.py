from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_HOUSE_MODEL_RADIUS_M = 200.0


class _AnchorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str | None = Field(default=None, min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def validate_anchor(self) -> "_AnchorRequest":
        has_latitude = self.latitude is not None
        has_longitude = self.longitude is not None
        if has_latitude != has_longitude:
            raise ValueError("latitude and longitude must be provided together.")
        return self


class HouseModelRequest(_AnchorRequest):
    radius_m: float = Field(default=50.0, gt=0, le=MAX_HOUSE_MODEL_RADIUS_M)


class GeocodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=1)


class GeocodingMetadata(BaseModel):
    source: Literal["request", "geocoded"]
    formatted_address: str | None = None
    place_id: str | None = None


class GeocodeResponse(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    geocoding: GeocodingMetadata


class TileSelection(BaseModel):
    uri: str
    geometric_error: float
    bounding_sphere_radius_m: float
    center_distance_m: float
    transform: list[float] = Field(default_factory=list)


class HouseModelMetadata(BaseModel):
    provider: str = "google_3d_tiles"
    anchor_latitude: float
    anchor_longitude: float
    radius_m: float
    geocoding: GeocodingMetadata
    tile: TileSelection
    candidate_tile_count: int
    copyright: str | None = None
    glb_size_bytes: int
