from uuid import uuid4

from sqlalchemy import delete

from app.api.accounts import edit_accounts_batch
from app.api.resource_pools import preview_account_pool_import
from app.database import SessionLocal, init_db
from app.main import app
from app.models.account import Account, AccountGroup
from app.models.auth import AccountAuthConfig
from app.models.resource_pool import ProxyEndpoint
from app.schemas.account import AccountBatchEdit
from app.schemas.resource_pool import AccountPoolImportText


init_db()
token = uuid4().hex[:10]
paths = app.openapi()["paths"]
assert "/api/accounts/batch/edit" in paths
assert "post" in paths["/api/accounts/batch/edit"]
assert "/api/account-pool/import/preview" in paths
assert "post" in paths["/api/account-pool/import/preview"]

db = SessionLocal()
account_ids: list[int] = []
group_ids: list[int] = []
proxy_ids: list[int] = []

try:
    group_a = AccountGroup(name=f"__phase10_batch_edit_a_{token}__")
    group_b = AccountGroup(name=f"__phase10_batch_edit_b_{token}__")
    db.add_all([group_a, group_b])
    db.flush()
    group_ids.extend([group_a.id, group_b.id])

    proxies = [
        ProxyEndpoint(
            endpoint_key=f"__phase10_batch_edit_proxy_{token}_{index}__",
            protocol="socks5",
            host=f"127.0.0.{index}",
            port=19000 + index,
            label=f"phase10-{token}-{index}",
            status="healthy",
            enabled=True,
        )
        for index in range(1, 4)
    ]
    db.add_all(proxies)
    db.flush()
    proxy_ids.extend([item.id for item in proxies])

    account_a = Account(
        name=f"__phase10_batch_edit_account_a_{token}__",
        platform="facebook",
        group_id=group_a.id,
        proxy_id=proxies[0].id,
        status="prepared",
    )
    account_b = Account(
        name=f"__phase10_batch_edit_account_b_{token}__",
        platform="facebook",
        group_id=group_a.id,
        proxy_id=None,
        status="prepared",
    )
    db.add_all([account_a, account_b])
    db.flush()
    account_ids.extend([account_a.id, account_b.id])
    db.add(
        AccountAuthConfig(
            account_id=account_a.id,
            login_identifier=f"phase10-existing-{token}@example.com",
        )
    )
    db.commit()

    result = edit_accounts_batch(
        AccountBatchEdit(
            account_ids=account_ids,
            group_mode="set",
            group_id=group_b.id,
            proxy_mode="auto_replace",
            enabled=False,
        ),
        db,
    )
    assert result["edited"] == 2
    refreshed = list(
        db.query(Account).filter(Account.id.in_(account_ids)).order_by(Account.id).all()
    )
    assert all(item.group_id == group_b.id for item in refreshed)
    assert all(item.enabled is False for item in refreshed)
    assert all(item.proxy_id is not None for item in refreshed)
    assert len({item.proxy_id for item in refreshed}) == 2

    preview = preview_account_pool_import(
        AccountPoolImportText(
            text=(
                "账号名称,平台,分组,登录账号,密码,2fa,cookie,proxy,备注\n"
                f"重复账号,facebook,{group_b.name},phase10-existing-{token}@example.com,SecretPassword,"
                f"JBSWY3DPEHPK3PXP,,{proxies[0].id},duplicate\n"
                f"新账号,facebook,Phase10 New Group {token},phase10-new-{token}@example.com,AnotherSecret,"
                f"JBSWY3DPEHPK3PXP,,{proxies[1].id},new\n"
            )
        ),
        db,
    )
    assert preview.received == 2
    assert preview.creatable == 1
    assert preview.skipped == 1
    assert preview.groups_to_create == [f"Phase10 New Group {token}"]
    payload = preview.model_dump_json()
    assert "SecretPassword" not in payload
    assert "AnotherSecret" not in payload
    assert "JBSWY3DPEHPK3PXP" not in payload
    assert preview.rows[0].action == "skip"
    assert preview.rows[1].action == "create"
finally:
    db.rollback()
    if account_ids:
        db.execute(delete(Account).where(Account.id.in_(account_ids)))
        db.commit()
    if group_ids:
        db.execute(delete(AccountGroup).where(AccountGroup.id.in_(group_ids)))
        db.commit()
    if proxy_ids:
        db.execute(delete(ProxyEndpoint).where(ProxyEndpoint.id.in_(proxy_ids)))
        db.commit()
    db.close()

print("phase10 account pool batch edit and import preview ok")
