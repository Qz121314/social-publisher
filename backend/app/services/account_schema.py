from sqlalchemy import Engine, inspect, text


def ensure_phase10_account_schema(engine: Engine) -> bool:
    """Upgrade legacy account storage to the Phase 10 resource-pool shape.

    New account-pool rows may exist before a real iX Profile is materialized, so
    ``ix_profile_id`` must be nullable. Accounts can also hold a stable
    ``proxy_id`` assignment from the product-level IP pool. SQLite cannot change
    NOT NULL in place; existing installations are rebuilt without changing ids.
    Child tables keep referring to the canonical ``accounts`` table name.
    """

    inspector = inspect(engine)
    if "accounts" not in inspector.get_table_names():
        return False

    columns = {column["name"]: column for column in inspector.get_columns("accounts")}
    needs_rebuild = (
        "proxy_id" not in columns
        or bool(columns.get("ix_profile_id", {}).get("nullable", True)) is False
        or "group_id" not in columns
    )
    if not needs_rebuild:
        with engine.begin() as connection:
            _create_account_indexes(connection)
        return False

    _rebuild_accounts(engine, set(columns))
    return True


def _rebuild_accounts(engine: Engine, existing_columns: set[str]) -> None:
    raw = engine.raw_connection()
    cursor = raw.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("DROP TABLE IF EXISTS accounts_phase10_new")
        cursor.execute(
            """
            CREATE TABLE accounts_phase10_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL,
                platform VARCHAR(50) NOT NULL,
                ix_profile_id INTEGER REFERENCES browser_profiles(profile_id) ON DELETE RESTRICT,
                group_id INTEGER REFERENCES account_groups(id) ON DELETE SET NULL,
                proxy_id INTEGER REFERENCES proxy_endpoints(id) ON DELETE SET NULL,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                status VARCHAR(50) NOT NULL DEFAULT 'unknown',
                notes TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT uq_accounts_platform_profile UNIQUE (platform, ix_profile_id)
            )
            """
        )

        target_columns = [
            "id",
            "name",
            "platform",
            "ix_profile_id",
            "group_id",
            "proxy_id",
            "enabled",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        fallbacks = {
            "ix_profile_id": "NULL",
            "group_id": "NULL",
            "proxy_id": "NULL",
            "enabled": "1",
            "status": "'unknown'",
            "notes": "NULL",
            "created_at": "CURRENT_TIMESTAMP",
            "updated_at": "CURRENT_TIMESTAMP",
        }
        select_parts = [
            name if name in existing_columns else fallbacks[name]
            for name in target_columns
        ]
        cursor.execute(
            f"INSERT INTO accounts_phase10_new ({', '.join(target_columns)}) "
            f"SELECT {', '.join(select_parts)} FROM accounts"
        )
        cursor.execute("DROP TABLE accounts")
        cursor.execute("ALTER TABLE accounts_phase10_new RENAME TO accounts")
        _create_account_indexes(cursor)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
            raw.close()


def _create_account_indexes(connection) -> None:
    statements = (
        "CREATE INDEX IF NOT EXISTS ix_accounts_platform ON accounts(platform)",
        "CREATE INDEX IF NOT EXISTS ix_accounts_ix_profile_id ON accounts(ix_profile_id)",
        "CREATE INDEX IF NOT EXISTS ix_accounts_group_id ON accounts(group_id)",
        "CREATE INDEX IF NOT EXISTS ix_accounts_proxy_id ON accounts(proxy_id)",
    )
    for statement in statements:
        if hasattr(connection, "exec_driver_sql"):
            connection.exec_driver_sql(statement)
        else:
            connection.execute(statement)
