from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.models.recommendation import RecommendationValidationResponse
from app.services.project_input_service import ProjectInputService, get_project_input_service

router = APIRouter()


@router.post("/recommendations", response_model=RecommendationValidationResponse)
def create_recommendation(
    request: str = Form(...),
    model_file: UploadFile | None = File(default=None),
    project_input_service: ProjectInputService = Depends(get_project_input_service),
) -> RecommendationValidationResponse:
    return project_input_service.validate_recommendation_input(request, model_file)
