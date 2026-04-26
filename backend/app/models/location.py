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


class GeocodingMetadata(BaseModel):
    source: Literal["request", "geocoded"]
    formatted_address: str | None = None
    place_id: str | None = None


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


class TileGlbRequest(BaseModel):
    """Body for POST /api/location/tile-glb.

    The frontend Photorealistic Tiles viewer captures the absolute tile content
    URL (without `key`/`session` query params — the SDK appends those at fetch
    time) and forwards it here so the backend can stream just that one tile.
    """

    model_config = ConfigDict(extra="forbid")

    tile_uri: str = Field(min_length=1)
    session: str | None = Field(default=None, min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class TileGlbMetadata(BaseModel):
    provider: str = "google_3d_tiles"
    tile_uri: str
    glb_size_bytes: int
    anchor_latitude: float | None = None
    anchor_longitude: float | None = None
