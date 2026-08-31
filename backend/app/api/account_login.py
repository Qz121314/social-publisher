from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.account_login import (
    AccountLoginError,
    AccountLoginUnsupported,
    check_account_login,
    confirm_account_login_identity,
    recover_account_login,
)
from app.services.browser_sessions import BrowserSessionError
from app.services.ixbrowser import IXBrowserError
from app.services.profile_locks import ProfileBusyError

router = APIRouter(tags=["account-login"])


@router.post("/{account_id}/login/recover")
def recover_login(account_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Recover one account in its fixed real iXBrowser Profile."""
    return _run(lambda: recover_account_login(db, account_id).to_dict())


@router.post("/{account_id}/login/check")
def check_login(account_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Inspect the current session without injecting credentials or Cookies."""
    return _run(lambda: check_account_login(db, account_id).to_dict())


@router.post("/{account_id}/login/confirm-identity")
def confirm_login_identity(account_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """First-time explicit confirmation of the observed Facebook login identity."""
    return _run(lambda: confirm_account_login_identity(db, account_id).to_dict())


def _run(action):
    try:
        return action()
    except ProfileBusyError as exc:
        raise HTTPException(status_code=409, detail="该浏览器环境正在执行其他任务，请稍后再试。") from exc
    except AccountLoginUnsupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AccountLoginError as exc:
        status_code = 404 if "未找到" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except (IXBrowserError, BrowserSessionError) as exc:
        raise HTTPException(status_code=503, detail=f"无法连接该 iXBrowser 环境：{exc}") from exc
