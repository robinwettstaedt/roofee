from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.models.recommendation import RecommendationValidationResponse
from app.services.house_data_service import HouseDataService, get_house_data_service
from app.services.project_input_service import ProjectInputService, get_project_input_service
from app.services.pvgis_service import PvgisService, get_pvgis_service

router = APIRouter()


@router.post("/recommendations", response_model=RecommendationValidationResponse)
def create_recommendation(
    request: str = Form(...),
    model_file: UploadFile | None = File(default=None),
    project_input_service: ProjectInputService = Depends(get_project_input_service),
    pvgis_service: PvgisService = Depends(get_pvgis_service),
    house_data_service: HouseDataService = Depends(get_house_data_service),
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
    return response
