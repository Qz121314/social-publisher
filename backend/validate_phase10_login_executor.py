from sqlalchemy import inspect

from app.database import engine, init_db
from app.main import app
from app.services.login_engine import LoginCapabilities, LoginResult, LoginState, LoginStateMachine
from app.services.platforms.facebook_login import classify_facebook_login_page


def main() -> None:
    init_db()
    assert inspect(engine).has_table("account_login_identities"), "account_login_identities table is missing"

    # FastAPI 0.141 keeps included routers as internal wrapper objects in
    # app.routes. OpenAPI is the authoritative flattened public route surface.
    paths = set(app.openapi().get("paths", {}))
    assert "/api/accounts/auth/{account_id}" in paths
    assert "/api/accounts/{account_id}/login/recover" in paths
    assert "/api/accounts/{account_id}/login/check" in paths
    assert "/api/accounts/{account_id}/login/confirm-identity" in paths

    result, _ = classify_facebook_login_page(
        current_url="https://www.facebook.com/",
        page_text="",
        identity_id="12345",
        login_form_visible=False,
        otp_input_visible=False,
    )
    assert result == LoginResult.SUCCESS

    result, _ = classify_facebook_login_page(
        current_url="https://www.facebook.com/checkpoint/",
        page_text="Use your authentication app to get a code",
        identity_id=None,
        login_form_visible=False,
        otp_input_visible=True,
    )
    assert result == LoginResult.TOTP_REQUIRED

    result, _ = classify_facebook_login_page(
        current_url="https://www.facebook.com/checkpoint/",
        page_text="Confirm your identity",
        identity_id=None,
        login_form_visible=False,
        otp_input_visible=False,
    )
    assert result == LoginResult.CHECKPOINT

    result, _ = classify_facebook_login_page(
        current_url="https://www.facebook.com/login/",
        page_text="",
        identity_id=None,
        login_form_visible=True,
        otp_input_visible=False,
    )
    assert result is None

    machine = LoginStateMachine(LoginCapabilities(totp_configured=True))
    machine.start()
    machine.profile_opened()
    assert machine.session_result(LoginResult.TOTP_REQUIRED) == LoginState.SUBMITTING_TOTP
    assert machine.totp_result(LoginResult.CHECKPOINT) == LoginState.CHECKPOINT

    unsafe_fallback_machine = LoginStateMachine(
        LoginCapabilities(cookie_configured=True, password_configured=True)
    )
    unsafe_fallback_machine.start()
    unsafe_fallback_machine.profile_opened()
    assert unsafe_fallback_machine.session_result(LoginResult.UNKNOWN) == LoginState.NEEDS_REVIEW

    print("phase10 login executor ok")


if __name__ == "__main__":
    main()
