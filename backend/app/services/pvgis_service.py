from collections import defaultdict
from statistics import mean
from typing import Any

import httpx
from fastapi import HTTPException

from app.models.recommendation import MonthlySolarWeather, SolarWeatherMetadata


PVGIS_API_VERSION = "5.3"
PVGIS_MRCALC_URL = f"https://re.jrc.ec.europa.eu/api/v{PVGIS_API_VERSION.replace('.', '_')}/MRcalc"
PVGIS_TIMEOUT_SECONDS = 10.0


class PvgisService:
    def fetch_solar_weather(self, latitude: float, longitude: float) -> SolarWeatherMetadata:
        params: dict[str, str | float | int] = self._request_params(latitude, longitude)

        try:
            response = httpx.get(PVGIS_MRCALC_URL, params=params, timeout=PVGIS_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=502, detail="PVGIS request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise HTTPException(status_code=502, detail=f"PVGIS returned HTTP {status_code}.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="PVGIS request failed.") from exc

        return self.parse_solar_weather(payload, latitude, longitude, params)

    def parse_solar_weather(
        self,
        payload: dict[str, Any],
        latitude: float,
        longitude: float,
        request_params: dict[str, str | float | int] | None = None,
    ) -> SolarWeatherMetadata:
        try:
            rows = payload["outputs"]["monthly"]
            if not isinstance(rows, list) or not rows:
                raise ValueError
            monthly = self._normalize_monthly_rows(rows)
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            raise HTTPException(status_code=502, detail="PVGIS returned malformed monthly data.") from exc

        return SolarWeatherMetadata(
            provider="pvgis",
            api_version=PVGIS_API_VERSION,
            latitude=latitude,
            longitude=longitude,
            source_url=PVGIS_MRCALC_URL,
            request_params=request_params or self._request_params(latitude, longitude),
            annual_horizontal_irradiation_kwh_per_m2=round(
                sum(item.horizontal_irradiation_kwh_per_m2 for item in monthly),
                2,
            ),
            annual_optimal_irradiation_kwh_per_m2=round(
                sum(item.optimal_irradiation_kwh_per_m2 for item in monthly),
                2,
            ),
            average_temperature_c=round(mean(item.average_temperature_c for item in monthly), 2),
            monthly=monthly,
        )

    def _request_params(self, latitude: float, longitude: float) -> dict[str, str | float | int]:
        return {
            "lat": latitude,
            "lon": longitude,
            "horirrad": 1,
            "optrad": 1,
            "avtemp": 1,
            "outputformat": "json",
        }

    def _normalize_monthly_rows(self, rows: list[Any]) -> list[MonthlySolarWeather]:
        by_month: dict[int, dict[str, list[float]]] = defaultdict(
            lambda: {"horizontal": [], "optimal": [], "temperature": []}
        )

        for row in rows:
            if not isinstance(row, dict):
                raise ValueError
            month = int(row["month"])
            if month < 1 or month > 12:
                raise ValueError
            by_month[month]["horizontal"].append(float(row["H(h)_m"]))
            by_month[month]["optimal"].append(float(row["H(i_opt)_m"]))
            by_month[month]["temperature"].append(float(row["T2m"]))

        if set(by_month) != set(range(1, 13)):
            raise ValueError

        return [
            MonthlySolarWeather(
                month=month,
                horizontal_irradiation_kwh_per_m2=round(mean(values["horizontal"]), 2),
                optimal_irradiation_kwh_per_m2=round(mean(values["optimal"]), 2),
                average_temperature_c=round(mean(values["temperature"]), 2),
            )
            for month, values in sorted(by_month.items())
        ]


def get_pvgis_service() -> PvgisService:
    return PvgisService()
