from fastapi import APIRouter, Depends

from app.models.roof import RoofSelectionRequest, RoofSelectionResponse
from app.services.house_data_service import HouseDataService, get_house_data_service
from app.services.roof.roof_analysis_service import RoofAnalysisService, get_roof_analysis_service

router = APIRouter()


@router.post("/roof/selection", response_model=RoofSelectionResponse)
def select_roof(
    request: RoofSelectionRequest,
    house_data_service: HouseDataService = Depends(get_house_data_service),
    roof_analysis_service: RoofAnalysisService = Depends(get_roof_analysis_service),
) -> RoofSelectionResponse:
    return roof_analysis_service.select_roof(request, house_data_service)
