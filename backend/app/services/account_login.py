from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.auth import AccountAuthConfig, AccountLoginIdentity
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.credential_vault import (
    CredentialVaultError,
    account_secret_reference,
    credential_vault,
)
from app.services.ixbrowser import IXBrowserError
from app.services.login_engine import (
    LoginCapabilities,
    LoginResult,
    LoginState,
    LoginStateMachine,
    generate_totp,
)
from app.services.platforms.facebook_login import FacebookLoginAdapter, FacebookPageObservation
from app.services.profile_locks import ProfileBusyError, profile_locks


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccountLoginError(RuntimeError):
    pass


class AccountLoginUnsupported(AccountLoginError):
    pass


@dataclass
class AccountLoginExecution:
    account_id: int
    profile_id: int
    state: str
    status: str
    message: str
    source_step: str
    identity_id: str | None = None
    identity_confirmed: bool = False
    action_required: str | None = None
    browser_open: bool = False
    current_url: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def recover_account_login(db: Session, account_id: int) -> AccountLoginExecution:
    account = _require_account(db, account_id)
    if account.platform != "facebook":
        raise AccountLoginUnsupported("当前真实登录执行器先支持 Facebook，其他平台将在后续适配。")

    config = _get_or_create_auth_config(db, account.id)
    capabilities = LoginCapabilities(
        cookie_configured=config.cookie_configured,
        password_configured=config.password_configured,
        totp_configured=config.totp_configured,
        allow_cookie_restore=config.allow_cookie_restore,
        allow_password_login=config.allow_password_login,
        allow_totp=config.allow_totp,
    )
    machine = LoginStateMachine(capabilities)
    machine.start()

    owner_id = f"account-login:{account.id}:{uuid4().hex[:10]}"
    profile_id = account.ix_profile_id
    opened_here = False
    keep_open = False
    observation: FacebookPageObservation | None = None
    source_step = "existing_session"

    profile_locks.acquire(db, profile_id=profile_id, owner_id=owner_id, ttl_seconds=240)
    try:
        opened = browser_sessions.open(profile_id)
        opened_here = not bool(opened.get("already_open"))
        machine.profile_opened()
        driver = browser_sessions.get_driver(profile_id)
        adapter = FacebookLoginAdapter()

        observation = adapter.open_home(driver)
        state = machine.session_result(_state_result(observation))

        if state == LoginState.RESTORING_COOKIES:
            source_step = "cookie_restore"
            try:
                cookie_json = credential_vault.get_text(account_secret_reference(account.id, "cookies"))
                observation = adapter.restore_cookies(driver, cookie_json)
            except (CredentialVaultError, ValueError, RuntimeError) as exc:
                keep_open = True
                return _finish(
                    db,
                    account,
                    state=LoginState.NEEDS_REVIEW,
                    status="needs_review",
                    message=f"Cookie 恢复无法继续：{exc}",
                    source_step=source_step,
                    observation=observation,
                    action_required="检查登录设置",
                    browser_open=True,
                )
            state = machine.cookies_result(_state_result(observation))

        if state == LoginState.ENTERING_CREDENTIALS:
            source_step = "password"
            if not config.login_identifier:
                return _finish(
                    db,
                    account,
                    state=LoginState.NEEDS_REVIEW,
                    status="needs_review",
                    message="已配置密码恢复，但尚未填写登录账号。请先完善登录设置。",
                    source_step=source_step,
                    observation=observation,
                    action_required="检查登录设置",
                    browser_open=not opened_here,
                )
            try:
                password = credential_vault.get_text(account_secret_reference(account.id, "password"))
            except CredentialVaultError as exc:
                return _finish(
                    db,
                    account,
                    state=LoginState.NEEDS_REVIEW,
                    status="needs_review",
                    message=f"无法读取已保存密码：{exc}",
                    source_step=source_step,
                    observation=observation,
                    action_required="检查登录设置",
                    browser_open=not opened_here,
                )
            observation = adapter.submit_password(
                driver,
                login_identifier=config.login_identifier,
                password=password,
            )
            state = machine.credentials_result(observation.result or LoginResult.UNKNOWN)

        if state == LoginState.SUBMITTING_TOTP:
            source_step = "totp"
            try:
                secret = credential_vault.get_text(account_secret_reference(account.id, "totp"))
                code = generate_totp(secret)
            except (CredentialVaultError, ValueError) as exc:
                keep_open = True
                return _finish(
                    db,
                    account,
                    state=LoginState.NEEDS_REVIEW,
                    status="needs_review",
                    message=f"无法生成 TOTP 验证码：{exc}",
                    source_step=source_step,
                    observation=observation,
                    action_required="检查登录设置",
                    browser_open=True,
                )
            observation = adapter.submit_totp(driver, code)
            state = machine.totp_result(observation.result or LoginResult.UNKNOWN)

        if state == LoginState.VERIFYING_IDENTITY:
            source_step = source_step or "existing_session"
            identity_id = observation.identity_id if observation else None
            if not identity_id:
                identity_id = adapter.current_login_identity(driver)
            result = _verify_identity(db, account, machine, identity_id, observation, source_step)
            keep_open = result.action_required in {"确认当前身份", "人工检查身份"}
            if keep_open:
                result.browser_open = True
            return result

        if state == LoginState.WAITING_FOR_USER:
            keep_open = True
            status = "needs_2fa" if observation and observation.result in {LoginResult.TOTP_REQUIRED, LoginResult.OTHER_MFA_REQUIRED} else "needs_login"
            message = observation.reason if observation else "当前账号需要人工完成登录。"
            if status == "needs_login":
                message = "自动恢复方式已用完或未配置，已保留真实 iXBrowser 窗口供你手动登录。"
            return _finish(
                db,
                account,
                state=state,
                status=status,
                message=message,
                source_step=source_step,
                observation=observation,
                action_required="在浏览器中处理",
                browser_open=True,
            )

        if state == LoginState.CHECKPOINT:
            keep_open = True
            return _finish(
                db,
                account,
                state=state,
                status="checkpoint",
                message=observation.reason if observation else "Facebook 要求安全检查，已停止自动处理。",
                source_step=source_step,
                observation=observation,
                action_required="在浏览器中处理",
                browser_open=True,
            )

        if state == LoginState.FAILED:
            return _finish(
                db,
                account,
                state=state,
                status="failed",
                message=observation.reason if observation else "Facebook 登录失败。",
                source_step=source_step,
                observation=observation,
                action_required="更新登录设置",
                browser_open=not opened_here,
            )

        keep_open = True
        return _finish(
            db,
            account,
            state=LoginState.NEEDS_REVIEW,
            status="needs_review",
            message=observation.reason if observation else "无法确认 Facebook 登录结果，已停止自动处理。",
            source_step=source_step,
            observation=observation,
            action_required="人工检查",
            browser_open=True,
        )
    finally:
        try:
            profile_locks.release(db, profile_id, owner_id)
        except ProfileBusyError:
            pass
        if opened_here and not keep_open:
            try:
                browser_sessions.close(profile_id, force=True)
            except (IXBrowserError, BrowserSessionError):
                pass


def check_account_login(db: Session, account_id: int) -> AccountLoginExecution:
    account = _require_account(db, account_id)
    if account.platform != "facebook":
        raise AccountLoginUnsupported("当前登录检查先支持 Facebook。")

    owner_id = f"account-login-check:{account.id}:{uuid4().hex[:10]}"
    profile_id = account.ix_profile_id
    opened_here = False
    keep_open = False
    profile_locks.acquire(db, profile_id=profile_id, owner_id=owner_id, ttl_seconds=120)
    try:
        opened = browser_sessions.open(profile_id)
        opened_here = not bool(opened.get("already_open"))
        driver = browser_sessions.get_driver(profile_id)
        adapter = FacebookLoginAdapter()
        observation = adapter.open_home(driver)

        if observation.result == LoginResult.SUCCESS:
            machine = LoginStateMachine(LoginCapabilities())
            machine.start()
            machine.profile_opened()
            machine.session_result(LoginResult.SUCCESS)
            result = _verify_identity(
                db,
                account,
                machine,
                observation.identity_id,
                observation,
                "existing_session",
            )
            keep_open = result.action_required in {"确认当前身份", "人工检查身份"}
            if keep_open:
                result.browser_open = True
            return result

        if observation.result == LoginResult.CHECKPOINT:
            keep_open = True
            return _finish(db, account, state=LoginState.CHECKPOINT, status="checkpoint", message=observation.reason, source_step="existing_session", observation=observation, action_required="在浏览器中处理", browser_open=True)
        if observation.result in {LoginResult.TOTP_REQUIRED, LoginResult.OTHER_MFA_REQUIRED}:
            keep_open = True
            return _finish(db, account, state=LoginState.WAITING_FOR_USER, status="needs_2fa", message=observation.reason, source_step="existing_session", observation=observation, action_required="在浏览器中处理", browser_open=True)
        if observation.result == LoginResult.UNKNOWN and not observation.login_form_visible:
            keep_open = True
            return _finish(db, account, state=LoginState.NEEDS_REVIEW, status="needs_review", message=observation.reason, source_step="existing_session", observation=observation, action_required="人工检查", browser_open=True)

        return _finish(
            db,
            account,
            state=LoginState.WAITING_FOR_USER,
            status="needs_login",
            message="当前固定 iX 环境没有有效 Facebook 登录状态。",
            source_step="existing_session",
            observation=observation,
            action_required="恢复登录",
            browser_open=not opened_here,
        )
    finally:
        try:
            profile_locks.release(db, profile_id, owner_id)
        except ProfileBusyError:
            pass
        if opened_here and not keep_open:
            try:
                browser_sessions.close(profile_id, force=True)
            except (IXBrowserError, BrowserSessionError):
                pass


def confirm_account_login_identity(db: Session, account_id: int) -> AccountLoginExecution:
    account = _require_account(db, account_id)
    if account.platform != "facebook":
        raise AccountLoginUnsupported("当前身份确认先支持 Facebook。")

    owner_id = f"account-login-confirm:{account.id}:{uuid4().hex[:10]}"
    profile_id = account.ix_profile_id
    opened_here = False
    profile_locks.acquire(db, profile_id=profile_id, owner_id=owner_id, ttl_seconds=120)
    try:
        opened = browser_sessions.open(profile_id)
        opened_here = not bool(opened.get("already_open"))
        driver = browser_sessions.get_driver(profile_id)
        adapter = FacebookLoginAdapter()
        observation = adapter.open_home(driver)
        if observation.result != LoginResult.SUCCESS or not observation.identity_id:
            account.status = "needs_login"
            db.commit()
            return AccountLoginExecution(
                account_id=account.id,
                profile_id=profile_id,
                state=LoginState.WAITING_FOR_USER.value,
                status="needs_login",
                message="当前浏览器还没有可确认的 Facebook 登录身份，请先完成登录。",
                source_step="identity_confirmation",
                browser_open=not opened_here,
                current_url=observation.current_url,
                action_required="恢复登录",
            )

        binding = db.get(AccountLoginIdentity, account.id)
        now = utcnow()
        if binding is not None and binding.platform_identity_id != observation.identity_id:
            account.status = "needs_review"
            db.commit()
            return AccountLoginExecution(
                account_id=account.id,
                profile_id=profile_id,
                state=LoginState.NEEDS_REVIEW.value,
                status="needs_review",
                message="当前 Facebook 登录身份与已经确认的账号身份不一致，系统不会自动覆盖原绑定。",
                source_step="identity_confirmation",
                identity_id=observation.identity_id,
                identity_confirmed=False,
                action_required="人工检查身份",
                browser_open=True,
                current_url=observation.current_url,
            )

        if binding is None:
            binding = AccountLoginIdentity(
                account_id=account.id,
                platform_identity_id=observation.identity_id,
                confirmed_at=now,
                last_verified_at=now,
            )
            db.add(binding)
        else:
            binding.last_verified_at = now
        account.status = "logged_in"
        db.commit()
        return AccountLoginExecution(
            account_id=account.id,
            profile_id=profile_id,
            state=LoginState.SUCCESS.value,
            status="logged_in",
            message="当前 Facebook 登录身份已确认并绑定到该账号。",
            source_step="identity_confirmation",
            identity_id=observation.identity_id,
            identity_confirmed=True,
            browser_open=not opened_here,
            current_url=observation.current_url,
        )
    finally:
        try:
            profile_locks.release(db, profile_id, owner_id)
        except ProfileBusyError:
            pass
        if opened_here:
            try:
                browser_sessions.close(profile_id, force=True)
            except (IXBrowserError, BrowserSessionError):
                pass


def _verify_identity(
    db: Session,
    account: Account,
    machine: LoginStateMachine,
    identity_id: str | None,
    observation: FacebookPageObservation | None,
    source_step: str,
) -> AccountLoginExecution:
    if not identity_id:
        return _finish(
            db,
            account,
            state=LoginState.NEEDS_REVIEW,
            status="needs_review",
            message="Facebook 看起来已经登录，但无法读取登录账号身份 ID，已停止。",
            source_step=source_step,
            observation=observation,
            action_required="人工检查",
            browser_open=True,
        )

    binding = db.get(AccountLoginIdentity, account.id)
    if binding is None:
        account.status = "needs_review"
        db.commit()
        return AccountLoginExecution(
            account_id=account.id,
            profile_id=account.ix_profile_id,
            state=LoginState.NEEDS_REVIEW.value,
            status="needs_review",
            message="已检测到有效 Facebook 登录，但这是该账号第一次绑定身份。请确认 iXBrowser 中当前账号无误后再确认身份。",
            source_step=source_step,
            identity_id=identity_id,
            identity_confirmed=False,
            action_required="确认当前身份",
            browser_open=True,
            current_url=observation.current_url if observation else None,
        )

    matches = binding.platform_identity_id == identity_id
    machine.identity_verified(matches)
    if not matches:
        account.status = "needs_review"
        db.commit()
        return AccountLoginExecution(
            account_id=account.id,
            profile_id=account.ix_profile_id,
            state=LoginState.NEEDS_REVIEW.value,
            status="needs_review",
            message="当前 Facebook 登录身份与该账号已确认身份不一致，已停止后续操作。",
            source_step=source_step,
            identity_id=identity_id,
            identity_confirmed=False,
            action_required="人工检查身份",
            browser_open=True,
            current_url=observation.current_url if observation else None,
        )

    binding.last_verified_at = utcnow()
    account.status = "logged_in"
    db.commit()
    return AccountLoginExecution(
        account_id=account.id,
        profile_id=account.ix_profile_id,
        state=LoginState.SUCCESS.value,
        status="logged_in",
        message="Facebook 登录状态正常，身份验证通过。",
        source_step=source_step,
        identity_id=identity_id,
        identity_confirmed=True,
        current_url=observation.current_url if observation else None,
    )


def _finish(
    db: Session,
    account: Account,
    *,
    state: LoginState,
    status: str,
    message: str,
    source_step: str,
    observation: FacebookPageObservation | None,
    action_required: str | None,
    browser_open: bool,
) -> AccountLoginExecution:
    account.status = status
    db.commit()
    return AccountLoginExecution(
        account_id=account.id,
        profile_id=account.ix_profile_id,
        state=state.value,
        status=status,
        message=message,
        source_step=source_step,
        identity_id=observation.identity_id if observation else None,
        identity_confirmed=False,
        action_required=action_required,
        browser_open=browser_open,
        current_url=observation.current_url if observation else None,
    )


def _state_result(observation: FacebookPageObservation) -> LoginResult | None:
    if observation.result == LoginResult.SUCCESS:
        return LoginResult.SUCCESS
    if observation.result in {
        LoginResult.TOTP_REQUIRED,
        LoginResult.OTHER_MFA_REQUIRED,
        LoginResult.CHECKPOINT,
        LoginResult.INVALID_CREDENTIALS,
        LoginResult.UNKNOWN,
    }:
        return observation.result
    return None


def _get_or_create_auth_config(db: Session, account_id: int) -> AccountAuthConfig:
    config = db.get(AccountAuthConfig, account_id)
    if config is None:
        config = AccountAuthConfig(account_id=account_id)
        db.add(config)
        db.flush()
    return config


def _require_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise AccountLoginError("未找到该社交账号。")
    if not account.enabled:
        raise AccountLoginError("该社交账号已停用，不能执行登录任务。")
    return account
