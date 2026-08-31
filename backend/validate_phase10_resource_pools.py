from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.main import app
from app.models.account import Account
from app.models.resource_pool import ProxyEndpoint
from app.schemas.account import AccountCreate
from app.services.account_schema import ensure_phase10_account_schema
from app.services.resource_pool import parse_account_import_csv, parse_proxy_import_text


def validate_parsers() -> None:
    proxies = parse_proxy_import_text(
        """
        1.2.3.4:1080:user1:pass1
        socks5://user2:pass2@5.6.7.8:2080
        9.9.9.9,3080,,,backup
        """
    )
    assert len(proxies) == 3
    assert proxies[0].host == "1.2.3.4"
    assert proxies[0].username == "user1"
    assert proxies[1].port == 2080
    assert proxies[2].label == "backup"
    assert len({item.endpoint_key for item in proxies}) == 3

    accounts = parse_account_import_csv(
        '账号名称,平台,分组,登录账号,密码,2fa,proxy,备注\n'
        'FB-001,facebook,Store A,user@example.com,pwd,JBSWY3DPEHPK3PXP,12,main\n'
    )
    assert len(accounts) == 1
    assert accounts[0].group_name == "Store A"
    assert accounts[0].proxy == "12"
    assert accounts[0].totp_secret == "JBSWY3DPEHPK3PXP"


def validate_models() -> None:
    assert Account.__table__.c.ix_profile_id.nullable is True
    assert "proxy_id" in Account.__table__.c
    proxy_columns = set(ProxyEndpoint.__table__.c.keys())
    assert "username" not in proxy_columns
    assert "password" not in proxy_columns
    assert AccountCreate(name="A", platform="facebook").ix_profile_id is None


def validate_legacy_migration() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "legacy.db"
        engine = create_engine(f"sqlite:///{path.as_posix()}")
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE browser_profiles (profile_id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE account_groups (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE proxy_endpoints (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql(
                """
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL,
                    platform VARCHAR(50) NOT NULL,
                    ix_profile_id INTEGER NOT NULL REFERENCES browser_profiles(profile_id),
                    group_id INTEGER REFERENCES account_groups(id),
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    status VARCHAR(50) NOT NULL DEFAULT 'unknown',
                    notes TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    UNIQUE(platform, ix_profile_id)
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE TABLE account_auth_configs (account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE)"
            )
            connection.exec_driver_sql("INSERT INTO browser_profiles(profile_id) VALUES (17)")
            connection.exec_driver_sql(
                "INSERT INTO accounts(id,name,platform,ix_profile_id,enabled,status,created_at,updated_at) "
                "VALUES (5,'Legacy','facebook',17,1,'logged_in',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
            connection.exec_driver_sql("INSERT INTO account_auth_configs(account_id) VALUES (5)")

        assert ensure_phase10_account_schema(engine) is True
        columns = {item["name"]: item for item in inspect(engine).get_columns("accounts")}
        assert columns["ix_profile_id"]["nullable"] is True
        assert "proxy_id" in columns
        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT id, ix_profile_id, proxy_id FROM accounts WHERE id=5"
            ).first()
            assert row == (5, 17, None)
            auth_row = connection.exec_driver_sql(
                "SELECT account_id FROM account_auth_configs WHERE account_id=5"
            ).first()
            assert auth_row == (5,)
            fk = connection.exec_driver_sql("PRAGMA foreign_key_list(account_auth_configs)").first()
            assert fk is not None and fk[2] == "accounts"
        engine.dispose()


def validate_routes() -> None:
    paths = set(app.openapi()["paths"])
    required = {
        "/api/proxy-pool",
        "/api/proxy-pool/import",
        "/api/proxy-pool/batch/delete",
        "/api/account-pool/import",
        "/api/account-pool/batch/assign-proxy",
    }
    missing = required - paths
    assert not missing, f"missing resource pool API paths: {sorted(missing)}"


if __name__ == "__main__":
    validate_parsers()
    validate_models()
    validate_legacy_migration()
    validate_routes()
    print("phase10 resource pool foundation ok")
