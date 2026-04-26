from pathlib import Path

from PIL import Image

from app.models.recommendation import (
    Google3DTilesData,
    HouseData,
    LatLng,
    ProposalRequest,
    SolarBuildingData,
    SolarWeatherMetadata,
)
from app.models.roof import (
    BoundingBoxPixels,
    OrthographicWorldBounds,
    RegistrationQualityMetrics,
    RoofAnalysis,
    RoofAnalysisStatus,
    RoofGeometryAnalysisRequest,
    RoofGeometryAnalysisResponse,
    RoofOutline,
    RoofRegistrationResponse,
    SelectedRoof,
    SimilarityTransform,
    TopDownRenderMetadata,
)
from app.services.project_input_service import ProjectInputService
from app.services.proposal_service import ProposalService


class FakeHouseDataService:
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path
        self.metadata_updates: list[tuple[str, dict[str, object]]] = []

    def fetch_house_data(self, latitude: float, longitude: float) -> HouseData:
        center = LatLng(latitude=latitude, longitude=longitude)
        return HouseData(
            status="fetched",
            provider="google",
            location=center,
            solar_building=SolarBuildingData(center=center, imagery_quality="HIGH"),
            overhead_image_url="/api/house-assets/test-asset/overhead.png",
            tiles_3d=Google3DTilesData(root_url="/api/google-3d-tiles/root.json", origin=center),
            warnings=[],
        )

    def overhead_image_path(self, asset_id: str) -> Path:
        assert asset_id == "test-asset"
        return self.image_path

    def update_house_asset_metadata(self, asset_id: str, values: dict[str, object]) -> None:
        self.metadata_updates.append((asset_id, values))


class FakePvgisService:
    def fetch_solar_weather(self, latitude: float, longitude: float) -> SolarWeatherMetadata:
        return SolarWeatherMetadata(
            provider="pvgis",
            api_version="5.3",
            latitude=latitude,
            longitude=longitude,
            source_url="https://example.test/pvgis",
            request_params={"lat": latitude, "lon": longitude},
            annual_horizontal_irradiation_kwh_per_m2=1200,
            annual_optimal_irradiation_kwh_per_m2=1400,
            average_temperature_c=11,
            monthly=[
                {
                    "month": month,
                    "horizontal_irradiation_kwh_per_m2": 100,
                    "optimal_irradiation_kwh_per_m2": 116,
                    "average_temperature_c": 11,
                }
                for month in range(1, 13)
            ],
        )


class FakeRoofAnalysisService:
    def analyze_house(self, house_data: HouseData, house_data_service: object) -> RoofAnalysis:
        return RoofAnalysis(
            status=RoofAnalysisStatus.ANALYZED,
            satellite_image_url=house_data.overhead_image_url,
            roof_outlines=[
                RoofOutline(
                    id="roof-001",
                    source="test",
                    model_id="test",
                    bounding_box_pixels=BoundingBoxPixels(x_min=0, y_min=0, x_max=20, y_max=20),
                    polygon_pixels=[[0, 0], [20, 0], [20, 20], [0, 20]],
                    area_pixels=400,
                    confidence=0.8,
                ),
                RoofOutline(
                    id="roof-002",
                    source="test",
                    model_id="test",
                    bounding_box_pixels=BoundingBoxPixels(x_min=35, y_min=35, x_max=65, y_max=65),
                    polygon_pixels=[[35, 35], [65, 35], [65, 65], [35, 65]],
                    area_pixels=900,
                    confidence=0.9,
                ),
            ],
        )

    def asset_id_from_overhead_url(self, url: str) -> str | None:
        return "test-asset" if url == "/api/house-assets/test-asset/overhead.png" else None


class FakeGeometryPipelineService:
    def __init__(self) -> None:
        self.requests: list[RoofGeometryAnalysisRequest] = []

    def analyze_geometry(
        self,
        request: RoofGeometryAnalysisRequest,
        *,
        house_data_service: object,
        tiles_service: object,
    ) -> RoofGeometryAnalysisResponse:
        self.requests.append(request)
        selected_roof = _selected_roof(request)
        metadata = TopDownRenderMetadata(
            render_width=100,
            render_height=100,
            orthographic_world_bounds=OrthographicWorldBounds(x_min=0, x_max=10, z_min=0, z_max=10),
        )
        return RoofGeometryAnalysisResponse(
            status="analyzed",
            selected_roof=selected_roof,
            registration=RoofRegistrationResponse(
                status="registered",
                selected_roof=selected_roof,
                transform=SimilarityTransform(
                    matrix=[[1, 0, 0], [0, 1, 0]],
                    scale=1,
                    rotation_degrees=0,
                    translation_pixels=[0, 0],
                    algorithm="orb",
                ),
                render_metadata=metadata,
                quality=RegistrationQualityMetrics(confidence=0.9),
            ),
            render_metadata=metadata,
        )


def test_proposal_flow_selects_clicked_house_roof_and_hides_2d_candidates(tmp_path: Path) -> None:
    image_path = tmp_path / "overhead.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    house_data_service = FakeHouseDataService(image_path)
    geometry_service = FakeGeometryPipelineService()
    service = ProposalService(
        project_input_service=ProjectInputService(),
        pvgis_service=FakePvgisService(),
        roof_analysis_service=FakeRoofAnalysisService(),
        geometry_pipeline_service=geometry_service,
    )

    response = service.create_proposal(
        ProposalRequest(
            project=_valid_project_payload(),
            picked_location=LatLng(latitude=52.5201, longitude=13.4051),
        ),
        house_data_service=house_data_service,
        tiles_service=object(),
    )

    assert response.status == "analyzed"
    assert response.recommendation.roof_analysis is None
    assert geometry_service.requests[0].selected_roof_outline_ids == ["roof-002"]
    assert response.roof_geometry.selected_roof.selected_roof_outline_ids == ["roof-002"]
    assert house_data_service.metadata_updates[0][0] == "test-asset"
    assert house_data_service.metadata_updates[0][1]["model_anchor"] == {
        "latitude": 52.5201,
        "longitude": 13.4051,
    }


def _valid_project_payload() -> dict[str, object]:
    return {
        "address": "Test Street 1, Berlin",
        "latitude": 52.52,
        "longitude": 13.405,
        "annual_electricity_demand_kwh": 4500,
        "electricity_price_per_kwh": 0.39,
        "num_inhabitants": 3,
        "house_size_sqm": 140,
        "heating_existing_type": "gas",
        "has_ev": False,
        "has_solar": False,
        "has_storage": False,
        "has_wallbox": False,
        "recommendation_goal": "balanced",
        "battery_preference": "consider",
        "heat_pump_preference": "consider",
        "ev_charger_preference": "consider",
    }


def _selected_roof(request: RoofGeometryAnalysisRequest) -> SelectedRoof:
    outline = RoofOutline(
        id=request.selected_roof_outline_ids[0],
        source="test",
        model_id="test-building-outline",
        bounding_box_pixels=BoundingBoxPixels(x_min=35, y_min=35, x_max=65, y_max=65),
        polygon_pixels=[[35, 35], [65, 35], [65, 65], [35, 65]],
        area_pixels=900,
        confidence=0.9,
    )
    return SelectedRoof(
        satellite_image_url=request.satellite_image_url,
        selected_roof_outline_ids=request.selected_roof_outline_ids,
        selected_roof_outlines=[outline],
        bounding_box_pixels=outline.bounding_box_pixels,
        area_pixels=outline.area_pixels,
    )
