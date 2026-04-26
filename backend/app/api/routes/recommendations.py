from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.models.recommendation import RecommendationValidationResponse
from app.services.house_data_service import HouseDataService, get_house_data_service
from app.services.project_input_service import ProjectInputService, get_project_input_service
from app.services.pvgis_service import PvgisService, get_pvgis_service
from app.services.roof.roof_analysis_service import RoofAnalysisService, get_roof_analysis_service

router = APIRouter()


@router.post("/recommendations", response_model=RecommendationValidationResponse)
def create_recommendation(
    request: str = Form(...),
    model_file: UploadFile | None = File(default=None),
    project_input_service: ProjectInputService = Depends(get_project_input_service),
    pvgis_service: PvgisService = Depends(get_pvgis_service),
    house_data_service: HouseDataService = Depends(get_house_data_service),
    roof_analysis_service: RoofAnalysisService = Depends(get_roof_analysis_service),
) -> RecommendationValidationResponse:
    response = project_input_service.validate_recommendation_input(request, model_file)
    response.house_data = house_data_service.fetch_house_data(
        response.input.latitude,
        response.input.longitude,
    )
    response.solar_weather = pvgis_service.fetch_solar_weather(
        response.input.latitude,
        response.input.longitude,
    )
    response.roof_analysis = roof_analysis_service.analyze_house(response.house_data, house_data_service)
    asset_id = roof_analysis_service.asset_id_from_overhead_url(response.house_data.overhead_image_url)
    if asset_id is not None:
        input_payload = response.input.model_dump(mode="json")
        house_data_service.update_house_asset_metadata(
            asset_id,
            {
                "project_context": {
                    **input_payload,
                    "recommendation_goal": response.input.recommendation_goal.value,
                    "battery_preference": response.input.battery_preference.value,
                    "heat_pump_preference": response.input.heat_pump_preference.value,
                    "ev_charger_preference": response.input.ev_charger_preference.value,
                    "shading_level": response.input.shading_level.value,
                }
            },
        )
    return response
