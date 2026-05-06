from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.responses import ok
from app.db import models
from app.db.session import get_db
from app.schemas.workflow import WorkflowTemplateRead

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("")
def list_workflows(db: Session = Depends(get_db)) -> dict:
    templates = (
        db.query(models.WorkflowTemplate)
        .order_by(models.WorkflowTemplate.is_default.desc(), models.WorkflowTemplate.name)
        .all()
    )
    data = [WorkflowTemplateRead.model_validate(template).model_dump(mode="json") for template in templates]
    return ok(data, count=len(data))

