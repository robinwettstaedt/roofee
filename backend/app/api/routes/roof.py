from fastapi import APIRouter, Depends

from app.models.roof import (
    RoofObstructionAnalysis,
    RoofObstructionRequest,
    RoofSelectionRequest,
    RoofSelectionResponse,
)
from app.services.house_data_service import HouseDataService, get_house_data_service
from app.services.roof.obstruction_service import (
    RoofObstructionService,
    get_roof_obstruction_service,
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
