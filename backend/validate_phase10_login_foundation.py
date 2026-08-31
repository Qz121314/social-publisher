from sqlalchemy import inspect

from app.database import engine, init_db
from app.services.cookie_session import normalize_cookie_payload
from app.services.credential_vault import account_secret_reference, credential_vault
from app.services.login_engine import (
    LoginCapabilities,
    LoginResult,
    LoginState,
    LoginStateMachine,
    build_login_plan,
    generate_totp,
    normalize_totp_secret,
)


def main() -> None:
    init_db()
    assert inspect(engine).has_table("account_auth_configs"), "account_auth_configs table is missing"

    capabilities = LoginCapabilities(
        cookie_configured=True,
        password_configured=True,
        totp_configured=True,
    )
    plan = build_login_plan(capabilities)
    assert plan.steps == (
        "existing_session",
        "cookie_restore",
        "password",
        "totp",
        "manual_takeover",
    )

    machine = LoginStateMachine(capabilities)
    assert machine.start() == LoginState.OPENING_PROFILE
    assert machine.profile_opened() == LoginState.CHECKING_SESSION
    assert machine.session_checked(False) == LoginState.RESTORING_COOKIES
    assert machine.cookies_restored(False) == LoginState.ENTERING_CREDENTIALS
    assert machine.credentials_result(LoginResult.TOTP_REQUIRED) == LoginState.SUBMITTING_TOTP
    assert machine.totp_result(True) == LoginState.VERIFYING_IDENTITY
    assert machine.identity_verified(True) == LoginState.SUCCESS

    manual_machine = LoginStateMachine(LoginCapabilities())
    manual_machine.start()
    manual_machine.profile_opened()
    assert manual_machine.session_checked(False) == LoginState.WAITING_FOR_USER

    checkpoint_machine = LoginStateMachine(LoginCapabilities(password_configured=True))
    checkpoint_machine.start()
    checkpoint_machine.profile_opened()
    checkpoint_machine.session_checked(False)
    assert checkpoint_machine.credentials_result(LoginResult.CHECKPOINT) == LoginState.CHECKPOINT

    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert normalize_totp_secret(secret) == secret
    assert generate_totp(secret, at=59, digits=8) == "94287082"

    facebook_cookie_json = '[{"name":"c_user","value":"123","domain":".facebook.com"},{"name":"third","value":"x","domain":"example.com"}]'
    normalized, count = normalize_cookie_payload(facebook_cookie_json, "facebook")
    assert count == 1
    assert "c_user" in normalized
    assert "example.com" not in normalized

    reference = account_secret_reference(123, "password")
    assert reference == "social-publisher/account/123/password"
    status = credential_vault.status()
    assert status["backend"] == "windows_dpapi"
    assert isinstance(status["supported"], bool)

    print("phase10 login foundation ok")


if __name__ == "__main__":
    main()
