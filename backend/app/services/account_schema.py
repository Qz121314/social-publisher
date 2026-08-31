from sqlalchemy import Engine, text


def ensure_phase10_account_schema(engine: Engine) -> bool:
    """Upgrade existing SQLite account storage for AccountGroup support.

    SQLAlchemy create_all() creates the new account_groups table but does not add
    columns to an existing accounts table. Keep this migration intentionally
    narrow: add nullable group_id and its index. Existing accounts remain in the
    virtual 'ungrouped' bucket.
    """

    with engine.begin() as connection:
        columns = {
            str(row[1])
            for row in connection.execute(text("PRAGMA table_info(accounts)")).fetchall()
        }
        if not columns or "group_id" in columns:
            return False

        connection.execute(
            text(
                "ALTER TABLE accounts "
                "ADD COLUMN group_id INTEGER REFERENCES account_groups(id) ON DELETE SET NULL"
            )
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_accounts_group_id ON accounts(group_id)")
        )
        return True
