from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.account_groups import router as account_groups_router
from app.database import get_db
from app.models.account import Account, AccountGroup, BrowserProfile
from app.schemas.account import AccountBatchMove, AccountCreate, AccountRead, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])
router.include_router(account_groups_router)


@router.get("", response_model=list[AccountRead])
def list_accounts(
    platform: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    group_id: int | None = Query(default=None),
    ungrouped: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[Account]:
    statement = (
        select(Account)
        .options(
            selectinload(Account.browser_profile),
            selectinload(Account.group),
        )
        .order_by(Account.created_at.desc())
    )
    if platform:
        statement = statement.where(Account.platform == platform.strip().lower())
    if enabled is not None:
        statement = statement.where(Account.enabled == enabled)
    if group_id is not None:
        statement = statement.where(Account.group_id == group_id)
    elif ungrouped:
        statement = statement.where(Account.group_id.is_(None))
    return list(db.scalars(statement).all())


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> Account:
    _require_profile(db, payload.ix_profile_id)
    _require_group(db, payload.group_id)

    account = Account(**payload.model_dump())
    db.add(account)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This iX profile is already linked to an account for that platform.",
        ) from exc

    return _get_account_or_404(db, account.id)


@router.post("/batch/group")
def move_accounts_to_group(
    payload: AccountBatchMove,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_group(db, payload.group_id)

    requested_ids = list(dict.fromkeys(payload.account_ids))
    accounts = list(db.scalars(select(Account).where(Account.id.in_(requested_ids))).all())
    found_ids = {account.id for account in accounts}
    missing = [account_id for account_id in requested_ids if account_id not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Account not found: {', '.join(str(item) for item in missing[:10])}",
        )

    for account in accounts:
        account.group_id = payload.group_id
    db.commit()
    return {
        "status": "ok",
        "moved": len(accounts),
        "group_id": payload.group_id,
    }


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")

    changes = payload.model_dump(exclude_unset=True)
    if "ix_profile_id" in changes:
        _require_profile(db, changes["ix_profile_id"])
    if "group_id" in changes:
        _require_group(db, changes["group_id"])

    for key, value in changes.items():
        setattr(account, key, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This iX profile is already linked to an account for that platform.",
        ) from exc

    return _get_account_or_404(db, account_id)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, db: Session = Depends(get_db)) -> Response:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    db.delete(account)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _require_profile(db: Session, profile_id: int) -> BrowserProfile:
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=400,
            detail="iX profile is not synced yet. Sync iXBrowser profiles first.",
        )
    return profile


def _require_group(db: Session, group_id: int | None) -> AccountGroup | None:
    if group_id is None:
        return None
    group = db.get(AccountGroup, group_id)
    if group is None:
        raise HTTPException(status_code=400, detail="Account group does not exist.")
    return group


def _get_account_or_404(db: Session, account_id: int) -> Account:
    statement = (
        select(Account)
        .options(
            selectinload(Account.browser_profile),
            selectinload(Account.group),
        )
        .where(Account.id == account_id)
    )
    account = db.scalar(statement)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return account
