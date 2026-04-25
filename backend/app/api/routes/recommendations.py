from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.models.recommendation import RecommendationValidationResponse
from app.services.project_input_service import ProjectInputService, get_project_input_service
from app.services.pvgis_service import PvgisService, get_pvgis_service

router = APIRouter()


@router.post("/recommendations", response_model=RecommendationValidationResponse)
def create_recommendation(
    request: str = Form(...),
    model_file: UploadFile | None = File(default=None),
    project_input_service: ProjectInputService = Depends(get_project_input_service),
    pvgis_service: PvgisService = Depends(get_pvgis_service),
) -> RecommendationValidationResponse:
    response = project_input_service.validate_recommendation_input(request, model_file)
    response.solar_weather = pvgis_service.fetch_solar_weather(
        response.input.latitude,
        response.input.longitude,
    )
    return response
