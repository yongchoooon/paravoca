from __future__ import annotations

from fastapi import APIRouter

from app.api.responses import ok
from app.schemas.enrichment import DataSourceCapabilitiesResponse, KtoSourceCapability
from app.tools.kto_capabilities import list_kto_capabilities

router = APIRouter(prefix="/data/sources", tags=["data-sources"])


@router.get("/capabilities")
def get_data_source_capabilities() -> dict:
    sources = [
        KtoSourceCapability.model_validate(source)
        for source in list_kto_capabilities()
    ]
    response = DataSourceCapabilitiesResponse(
        sources=sources,
        enabled_count=sum(1 for source in sources if source.enabled),
        implemented_operation_count=sum(
            1
            for source in sources
            for operation in source.operations
            if operation.implemented
        ),
        workflow_operation_count=sum(
            1
            for source in sources
            for operation in source.operations
            if operation.workflow_enabled
        ),
    )
    return ok(response.model_dump(mode="json"), count=len(sources))
