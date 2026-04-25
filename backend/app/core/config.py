from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Roofee API"
    cors_origins: list[str] = ["http://localhost:3000"]
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ROOFEE_")


settings = Settings()
