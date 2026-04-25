from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.models.location import GeocodingMetadata

DEFAULT_USER_AGENT = "roofee/0.1"


class GeocodingService:
    def __init__(self, api_key: str | None, geocoding_url: str, timeout_seconds: float) -> None:
        self._api_key = api_key
        self._geocoding_url = geocoding_url
        self._timeout_seconds = timeout_seconds

    def geocode(self, address: str) -> tuple[GeocodingMetadata, float, float]:
        if not self._api_key:
            raise HTTPException(status_code=503, detail="Google API key is not configured.")

        try:
            response = httpx.get(
                self._geocoding_url,
                params={"address": address, "key": self._api_key},
                timeout=self._timeout_seconds,
                headers={"User-Agent": DEFAULT_USER_AGENT},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=502, detail="Google Geocoding request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Geocoding returned HTTP {exc.response.status_code}.",
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="Google Geocoding request failed.") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="Google Geocoding returned malformed data.")

        status = payload.get("status")
        if status == "ZERO_RESULTS":
            raise HTTPException(status_code=404, detail="Address could not be geocoded.")
        if status != "OK":
            raise HTTPException(status_code=502, detail="Google Geocoding did not return an OK status.")

        result = _first_result(payload)
        location = result.get("geometry", {}).get("location")
        if not isinstance(location, dict) or location.get("lat") is None or location.get("lng") is None:
            raise HTTPException(status_code=502, detail="Google Geocoding returned malformed data.")

        return (
            GeocodingMetadata(
                source="geocoded",
                formatted_address=_optional_str(result.get("formatted_address")),
                place_id=_optional_str(result.get("place_id")),
            ),
            float(location["lat"]),
            float(location["lng"]),
        )


def get_geocoding_service() -> GeocodingService:
    return GeocodingService(
        api_key=settings.google_api_key or settings.google_maps_api_key,
        geocoding_url=settings.google_geocoding_url,
        timeout_seconds=settings.google_timeout_seconds,
    )


def _first_result(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise HTTPException(status_code=404, detail="Address could not be geocoded.")
    return results[0]


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
