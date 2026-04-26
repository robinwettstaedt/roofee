import httpx
import pytest
from fastapi import HTTPException

from app.services import pvgis_service
from app.services.pvgis_service import PVGIS_MRCALC_URL, PvgisService, _pvgis_aspect_from_roof_azimuth


def monthly_rows() -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    for year, offset in [(2022, 0), (2023, 12)]:
        for month in range(1, 13):
            rows.append(
                {
                    "year": year,
                    "month": month,
                    "H(h)_m": month + offset,
                    "H(i_opt)_m": (month * 2) + offset,
                    "T2m": 10 + month + offset,
                }
            )
    return rows


def test_fetch_solar_weather_builds_expected_mrcalc_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"outputs": {"monthly": monthly_rows()}}

    def fake_get(url: str, params: dict[str, object], timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(pvgis_service.httpx, "get", fake_get)

    result = PvgisService().fetch_solar_weather(52.52, 13.405)

    assert captured["url"] == PVGIS_MRCALC_URL
    assert captured["params"] == {
        "lat": 52.52,
        "lon": 13.405,
        "horirrad": 1,
        "optrad": 1,
        "avtemp": 1,
        "outputformat": "json",
    }
    assert captured["timeout"] == 10.0
    assert result.provider == "pvgis"
    assert result.api_version == "5.3"


def test_parse_solar_weather_normalizes_monthly_data_and_computes_annual_values() -> None:
    result = PvgisService().parse_solar_weather(
        {"outputs": {"monthly": monthly_rows()}},
        latitude=52.52,
        longitude=13.405,
    )

    assert len(result.monthly) == 12
    assert result.monthly[0].month == 1
    assert result.monthly[0].horizontal_irradiation_kwh_per_m2 == 7.0
    assert result.monthly[0].optimal_irradiation_kwh_per_m2 == 8.0
    assert result.monthly[0].average_temperature_c == 17.0
    assert result.annual_horizontal_irradiation_kwh_per_m2 == 150.0
    assert result.annual_optimal_irradiation_kwh_per_m2 == 228.0
    assert result.average_temperature_c == 22.5
    assert result.source_url == PVGIS_MRCALC_URL
    assert result.request_params["outputformat"] == "json"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"outputs": {}},
        {"outputs": {"monthly": []}},
        {"outputs": {"monthly": [{"month": 1, "H(h)_m": 1, "H(i_opt)_m": 2, "T2m": 3}]}},
        {"outputs": {"monthly": [{"month": 13, "H(h)_m": 1, "H(i_opt)_m": 2, "T2m": 3}]}},
    ],
)
def test_parse_solar_weather_returns_502_for_malformed_data(payload: dict[str, object]) -> None:
    with pytest.raises(HTTPException) as exc:
        PvgisService().parse_solar_weather(payload, latitude=52.52, longitude=13.405)

    assert exc.value.status_code == 502
    assert exc.value.detail == "PVGIS returned malformed monthly data."


def test_fetch_solar_weather_returns_502_for_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, params: dict[str, object], timeout: float) -> None:
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(pvgis_service.httpx, "get", fake_get)

    with pytest.raises(HTTPException) as exc:
        PvgisService().fetch_solar_weather(52.52, 13.405)

    assert exc.value.status_code == 502
    assert exc.value.detail == "PVGIS request timed out."


def test_fetch_solar_weather_returns_502_for_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 503

        def raise_for_status(self) -> None:
            request = httpx.Request("GET", PVGIS_MRCALC_URL)
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("service unavailable", request=request, response=response)

    def fake_get(url: str, params: dict[str, object], timeout: float) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(pvgis_service.httpx, "get", fake_get)

    with pytest.raises(HTTPException) as exc:
        PvgisService().fetch_solar_weather(52.52, 13.405)

    assert exc.value.status_code == 502
    assert exc.value.detail == "PVGIS returned HTTP 503."


def test_parse_annual_pv_yield_per_kwp() -> None:
    yield_per_kwp = PvgisService().parse_annual_pv_yield_per_kwp(
        {"outputs": {"totals": {"fixed": {"E_y": 957.42}}}}
    )

    assert yield_per_kwp == 957.42


def test_pvgis_aspect_converts_roof_azimuth_to_south_zero_convention() -> None:
    assert _pvgis_aspect_from_roof_azimuth(180) == 0
    assert _pvgis_aspect_from_roof_azimuth(90) == -90
    assert _pvgis_aspect_from_roof_azimuth(270) == 90
    assert _pvgis_aspect_from_roof_azimuth(0) == -180
