from fastapi import APIRouter, Depends

from app.models.dataset import DatasetSummary
from app.services.data_service import DataService, get_data_service

router = APIRouter()


@router.get("/datasets", response_model=list[DatasetSummary])
def list_datasets(
    data_service: DataService = Depends(get_data_service),
) -> list[DatasetSummary]:
    return data_service.list_datasets()
