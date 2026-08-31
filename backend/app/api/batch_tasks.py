from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.batch_task import BatchLoginCreate, BatchTaskRead
from app.services.batch_tasks import BatchTaskError, create_login_batch, get_batch, list_batches

router = APIRouter(prefix="/batch-tasks", tags=["batch-tasks"])


@router.post(
    "/login",
    response_model=BatchTaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_batch_login(
    payload: BatchLoginCreate,
    db: Session = Depends(get_db),
) -> BatchTaskRead:
    try:
        return BatchTaskRead.model_validate(create_login_batch(db, payload))
    except BatchTaskError as exc:
        message = str(exc)
        code = 404 if "不存在" in message and "任务" in message else 409 if "已经在登录任务" in message else 400
        raise HTTPException(status_code=code, detail=message) from exc


@router.get("", response_model=list[BatchTaskRead])
def list_batch_tasks(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[BatchTaskRead]:
    return [BatchTaskRead.model_validate(item) for item in list_batches(db, limit=limit)]


@router.get("/{batch_id}", response_model=BatchTaskRead)
def get_batch_task(batch_id: str, db: Session = Depends(get_db)) -> BatchTaskRead:
    try:
        return BatchTaskRead.model_validate(get_batch(db, batch_id))
    except BatchTaskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
