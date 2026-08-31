from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from dataclasses import dataclass
from enum import StrEnum


class LoginState(StrEnum):
    IDLE = "idle"
    OPENING_PROFILE = "opening_profile"
    CHECKING_SESSION = "checking_session"
    RESTORING_COOKIES = "restoring_cookies"
    ENTERING_CREDENTIALS = "entering_credentials"
    SUBMITTING_TOTP = "submitting_totp"
    VERIFYING_IDENTITY = "verifying_identity"
    WAITING_FOR_USER = "waiting_for_user"
    CHECKPOINT = "checkpoint"
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class LoginResult(StrEnum):
    SUCCESS = "success"
    TOTP_REQUIRED = "totp_required"
    OTHER_MFA_REQUIRED = "other_mfa_required"
    CHECKPOINT = "checkpoint"
    INVALID_CREDENTIALS = "invalid_credentials"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LoginCapabilities:
    cookie_configured: bool = False
    password_configured: bool = False
    totp_configured: bool = False
    allow_cookie_restore: bool = True
    allow_password_login: bool = True
    allow_totp: bool = True


@dataclass(frozen=True)
class LoginPlan:
    steps: tuple[str, ...]


class LoginStateMachine:
    """Pure decision engine for account login/recovery.

    Browser/Selenium code reports observable outcomes into this machine. The
    machine never retries checkpoints or unknown security states automatically.
    Only an explicit ``None`` observation means "confirmed logged out" and may
    advance to the next configured recovery strategy.
    """

    def __init__(self, capabilities: LoginCapabilities) -> None:
        self.capabilities = capabilities
        self.state = LoginState.IDLE

    def start(self) -> LoginState:
        self.state = LoginState.OPENING_PROFILE
        return self.state

    def profile_opened(self) -> LoginState:
        self._require(LoginState.OPENING_PROFILE)
        self.state = LoginState.CHECKING_SESSION
        return self.state

    def session_result(self, result: LoginResult | None) -> LoginState:
        self._require(LoginState.CHECKING_SESSION)
        if result == LoginResult.SUCCESS:
            self.state = LoginState.VERIFYING_IDENTITY
        elif result == LoginResult.TOTP_REQUIRED:
            self.state = self._totp_or_manual()
        elif result == LoginResult.OTHER_MFA_REQUIRED:
            self.state = LoginState.WAITING_FOR_USER
        elif result == LoginResult.CHECKPOINT:
            self.state = LoginState.CHECKPOINT
        elif result is not None:
            self.state = LoginState.NEEDS_REVIEW
        elif self.capabilities.allow_cookie_restore and self.capabilities.cookie_configured:
            self.state = LoginState.RESTORING_COOKIES
        elif self.capabilities.allow_password_login and self.capabilities.password_configured:
            self.state = LoginState.ENTERING_CREDENTIALS
        else:
            self.state = LoginState.WAITING_FOR_USER
        return self.state

    def session_checked(self, valid: bool) -> LoginState:
        return self.session_result(LoginResult.SUCCESS if valid else None)

    def cookies_result(self, result: LoginResult | None) -> LoginState:
        self._require(LoginState.RESTORING_COOKIES)
        if result == LoginResult.SUCCESS:
            self.state = LoginState.VERIFYING_IDENTITY
        elif result == LoginResult.TOTP_REQUIRED:
            self.state = self._totp_or_manual()
        elif result == LoginResult.OTHER_MFA_REQUIRED:
            self.state = LoginState.WAITING_FOR_USER
        elif result == LoginResult.CHECKPOINT:
            self.state = LoginState.CHECKPOINT
        elif result is not None:
            self.state = LoginState.NEEDS_REVIEW
        elif self.capabilities.allow_password_login and self.capabilities.password_configured:
            self.state = LoginState.ENTERING_CREDENTIALS
        else:
            self.state = LoginState.WAITING_FOR_USER
        return self.state

    def cookies_restored(self, valid: bool) -> LoginState:
        return self.cookies_result(LoginResult.SUCCESS if valid else None)

    def credentials_result(self, result: LoginResult) -> LoginState:
        self._require(LoginState.ENTERING_CREDENTIALS)
        if result == LoginResult.SUCCESS:
            self.state = LoginState.VERIFYING_IDENTITY
        elif result == LoginResult.TOTP_REQUIRED:
            self.state = self._totp_or_manual()
        elif result == LoginResult.OTHER_MFA_REQUIRED:
            self.state = LoginState.WAITING_FOR_USER
        elif result == LoginResult.CHECKPOINT:
            self.state = LoginState.CHECKPOINT
        elif result == LoginResult.INVALID_CREDENTIALS:
            self.state = LoginState.FAILED
        else:
            self.state = LoginState.NEEDS_REVIEW
        return self.state

    def totp_result(self, result: LoginResult) -> LoginState:
        self._require(LoginState.SUBMITTING_TOTP)
        if result == LoginResult.SUCCESS:
            self.state = LoginState.VERIFYING_IDENTITY
        elif result == LoginResult.OTHER_MFA_REQUIRED:
            self.state = LoginState.WAITING_FOR_USER
        elif result == LoginResult.CHECKPOINT:
            self.state = LoginState.CHECKPOINT
        elif result == LoginResult.INVALID_CREDENTIALS:
            self.state = LoginState.FAILED
        else:
            self.state = LoginState.NEEDS_REVIEW
        return self.state

    def identity_verified(self, matches: bool) -> LoginState:
        self._require(LoginState.VERIFYING_IDENTITY)
        self.state = LoginState.SUCCESS if matches else LoginState.NEEDS_REVIEW
        return self.state

    def _totp_or_manual(self) -> LoginState:
        if self.capabilities.allow_totp and self.capabilities.totp_configured:
            return LoginState.SUBMITTING_TOTP
        return LoginState.WAITING_FOR_USER

    def _require(self, expected: LoginState) -> None:
        if self.state != expected:
            raise RuntimeError(f"invalid login transition: {self.state} -> expected {expected}")


def build_login_plan(capabilities: LoginCapabilities) -> LoginPlan:
    steps = ["existing_session"]
    if capabilities.allow_cookie_restore and capabilities.cookie_configured:
        steps.append("cookie_restore")
    if capabilities.allow_password_login and capabilities.password_configured:
        steps.append("password")
        if capabilities.allow_totp and capabilities.totp_configured:
            steps.append("totp")
    steps.append("manual_takeover")
    return LoginPlan(tuple(steps))


def normalize_totp_secret(secret: str) -> str:
    normalized = "".join(ch for ch in secret.upper() if ch not in {" ", "-"})
    if not normalized:
        raise ValueError("TOTP 密钥不能为空。")
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    try:
        decoded = base64.b32decode(normalized + padding, casefold=True)
    except Exception as exc:
        raise ValueError("TOTP 密钥不是有效的 Base32 格式。") from exc
    if len(decoded) < 10:
        raise ValueError("TOTP 密钥长度过短。")
    return normalized


def generate_totp(
    secret: str,
    *,
    at: float | None = None,
    digits: int = 6,
    period: int = 30,
) -> str:
    normalized = normalize_totp_secret(secret)
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(normalized + padding, casefold=True)
    timestamp = time.time() if at is None else at
    counter = int(timestamp // period)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10**digits)).zfill(digits)
