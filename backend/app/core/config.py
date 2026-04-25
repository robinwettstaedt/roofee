from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Roofee API"
    cors_origins: list[str] = ["http://localhost:3000"]
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    google_api_key: str | None = None
    google_maps_api_key: str | None = None
    google_geocoding_url: str = "https://maps.googleapis.com/maps/api/geocode/json"
    google_3d_tiles_root_url: str = "https://tile.googleapis.com/v1/3dtiles/root.json"
    google_3d_tiles_max_radius_m: float = 200.0
    google_3d_tiles_max_walk_depth: int = 32
    google_timeout_seconds: float = 10.0
    house_data_cache_dir: Path = Path(".roofee_cache/house_data")
    google_solar_radius_meters: float = 50.0
    google_solar_pixel_size_meters: float = 0.25
    rid_runtime_python: str = "python3.10"
    rid_runtime_timeout_seconds: float = 60.0
    roof_obstruction_crop_padding_pixels: int = 8
    roof_obstruction_min_confidence: float = 0.5
    roof_obstruction_min_area_pixels: float = 50.0

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_prefix="ROOFEE_")


settings = Settings()
