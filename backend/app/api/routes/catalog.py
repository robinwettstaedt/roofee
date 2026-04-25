from collections.abc import Iterable

from fastapi import APIRouter, Depends

from app.models.catalog import ComponentCatalog, CatalogSummary, ComponentKind
from app.services.catalog_service import CatalogService, get_catalog_service

router = APIRouter()


@router.get("/components", response_model=ComponentCatalog)
def list_components(
    kind: ComponentKind | None = None,
    catalog_service: CatalogService = Depends(get_catalog_service),
) -> ComponentCatalog:
    catalog = catalog_service.build_catalog()
    if kind is None:
        return catalog

    components = [component for component in catalog.components if component.kind == kind]
    return ComponentCatalog(
        summary=CatalogSummary(
            component_count=len(components),
            source_datasets=catalog.summary.source_datasets,
            counts_by_category=_counts(component.category.value for component in components),
            counts_by_kind=_counts(component.kind.value for component in components),
            warning_count=sum(1 for component in components if component.warnings),
        ),
        components=components,
    )


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
