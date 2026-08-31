from uuid import uuid4

from sqlalchemy import inspect

from app.database import SessionLocal, engine, init_db
from app.models.account import Account, AccountGroup, BrowserProfile


def main() -> None:
    init_db()

    columns = {column["name"] for column in inspect(engine).get_columns("accounts")}
    assert "group_id" in columns, "accounts.group_id schema upgrade is missing"
    assert inspect(engine).has_table("account_groups"), "account_groups table is missing"

    suffix = uuid4().hex[:10]
    profile_id = 900_000_000 + int(suffix[:6], 16) % 90_000_000

    with SessionLocal() as db:
        while db.get(BrowserProfile, profile_id) is not None:
            profile_id += 1

        profile = BrowserProfile(
            profile_id=profile_id,
            name=f"Phase10 Account Profile {suffix}",
            raw_json="{}",
            is_available=True,
        )
        group = AccountGroup(name=f"Phase10 Group {suffix}", description="validator")
        db.add_all([profile, group])
        db.flush()

        account = Account(
            name=f"Phase10 Account {suffix}",
            platform="other",
            ix_profile_id=profile_id,
            group_id=group.id,
        )
        db.add(account)
        db.commit()

        db.refresh(account)
        assert account.group_id == group.id
        assert account.group is not None
        assert account.group.name == group.name

        account.group_id = None
        db.commit()
        db.refresh(account)
        assert account.group_id is None

        db.delete(account)
        db.delete(group)
        db.delete(profile)
        db.commit()

    print("phase10 account groups ok")


if __name__ == "__main__":
    main()
