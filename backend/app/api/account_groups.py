from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account, AccountGroup
from app.schemas.account import AccountGroupCreate, AccountGroupRead, AccountGroupUpdate

router = APIRouter(prefix="/groups", tags=["account-groups"])


def _to_read(group: AccountGroup, member_count: int = 0) -> AccountGroupRead:
    return AccountGroupRead(
        id=group.id,
        name=group.name,
        description=group.description,
        sort_order=group.sort_order,
        enabled=group.enabled,
        member_count=member_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.get("", response_model=list[AccountGroupRead])
def list_account_groups(db: Session = Depends(get_db)) -> list[AccountGroupRead]:
    counts = dict(
        db.execute(
            select(Account.group_id, func.count(Account.id))
            .where(Account.group_id.is_not(None))
            .group_by(Account.group_id)
        ).all()
    )
    groups = list(
        db.scalars(
            select(AccountGroup).order_by(
                AccountGroup.sort_order,
                AccountGroup.name,
                AccountGroup.id,
            )
        ).all()
    )
    return [_to_read(group, int(counts.get(group.id, 0))) for group in groups]


@router.post("", response_model=AccountGroupRead, status_code=status.HTTP_201_CREATED)
def create_account_group(
    payload: AccountGroupCreate,
    db: Session = Depends(get_db),
) -> AccountGroupRead:
    group = AccountGroup(**payload.model_dump())
    db.add(group)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account group name already exists.") from exc
    db.refresh(group)
    return _to_read(group)


@router.patch("/{group_id}", response_model=AccountGroupRead)
def update_account_group(
    group_id: int,
    payload: AccountGroupUpdate,
    db: Session = Depends(get_db),
) -> AccountGroupRead:
    group = db.get(AccountGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Account group not found.")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, key, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account group name already exists.") from exc
    db.refresh(group)
    member_count = db.scalar(select(func.count(Account.id)).where(Account.group_id == group.id)) or 0
    return _to_read(group, int(member_count))


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account_group(group_id: int, db: Session = Depends(get_db)) -> Response:
    group = db.get(AccountGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Account group not found.")

    member_count = db.scalar(select(func.count(Account.id)).where(Account.group_id == group.id)) or 0
    if member_count:
        raise HTTPException(
            status_code=409,
            detail="Move accounts out of this group before deleting it.",
        )

    db.delete(group)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
