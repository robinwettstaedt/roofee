import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.models.recommendation import ProposalRequest, ProposalResponse
from app.services.house_data_service import HouseDataService, get_house_data_service
from app.services.location.google_3d_tiles_service import Google3DTilesService, get_google_3d_tiles_service
from app.services.proposal_service import ProposalService, get_proposal_service

router = APIRouter()


@router.post("/proposal", response_model=ProposalResponse)
def create_proposal(
    request: str = Form(...),
    model_file: UploadFile | None = File(default=None),
    house_data_service: HouseDataService = Depends(get_house_data_service),
    tiles_service: Google3DTilesService = Depends(get_google_3d_tiles_service),
    proposal_service: ProposalService = Depends(get_proposal_service),
) -> ProposalResponse:
    try:
        parsed_request = ProposalRequest.model_validate_json(request)
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid proposal request JSON.") from exc

    return proposal_service.create_proposal(
        parsed_request,
        model_file=model_file,
        house_data_service=house_data_service,
        tiles_service=tiles_service,
    )
