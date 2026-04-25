import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.models.roof import (
    RoofObstructionAnalysis,
    RoofObstructionRequest,
    RoofRegistrationRequest,
    RoofRegistrationResponse,
    RoofSelectionRequest,
    RoofSelectionResponse,
)
from app.services.house_data_service import HouseDataService, get_house_data_service
from app.services.roof.obstruction_service import (
    RoofObstructionService,
    get_roof_obstruction_service,
)
from app.services.roof.registration_service import (
    RoofRegistrationService,
    get_roof_registration_service,
)
from app.services.roof.roof_analysis_service import RoofAnalysisService, get_roof_analysis_service

router = APIRouter()


@router.post("/roof/selection", response_model=RoofSelectionResponse)
def select_roof(
    request: RoofSelectionRequest,
    house_data_service: HouseDataService = Depends(get_house_data_service),
    roof_analysis_service: RoofAnalysisService = Depends(get_roof_analysis_service),
) -> RoofSelectionResponse:
    return roof_analysis_service.select_roof(request, house_data_service)


@router.post("/roof/obstructions", response_model=RoofObstructionAnalysis)
def analyze_roof_obstructions(
    request: RoofObstructionRequest,
    house_data_service: HouseDataService = Depends(get_house_data_service),
    obstruction_service: RoofObstructionService = Depends(get_roof_obstruction_service),
) -> RoofObstructionAnalysis:
    return obstruction_service.analyze_obstructions(request, house_data_service)


@router.post("/roof/registration", response_model=RoofRegistrationResponse)
async def register_roof_to_top_down_render(
    request: str = Form(...),
    top_down_render: UploadFile = File(...),
    house_data_service: HouseDataService = Depends(get_house_data_service),
    registration_service: RoofRegistrationService = Depends(get_roof_registration_service),
) -> RoofRegistrationResponse:
    try:
        parsed_request = RoofRegistrationRequest.model_validate_json(request)
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid registration request JSON.") from exc

    if top_down_render.content_type not in {None, "image/png", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="top_down_render must be a PNG image.")

    return registration_service.register_roof(
        parsed_request,
        await top_down_render.read(),
        house_data_service,
    )
