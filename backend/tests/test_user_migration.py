import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20261025_01_create_users_table.py"
)

spec = importlib.util.spec_from_file_location(
    "findai_initial_user_migration",
    MIGRATION_PATH,
)
assert spec is not None and spec.loader is not None
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def _render_migration(operation_name: str) -> str:
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="mysql",
        opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        getattr(migration, operation_name)()
    return output.getvalue().lower()


def test_initial_migration_renders_expected_users_schema() -> None:
    sql = _render_migration("upgrade")

    expected_fragments = (
        "create table users (",
        "id integer not null auto_increment",
        "username varchar(50) not null",
        "email varchar(255) not null",
        "hashed_password varchar(255) not null",
        "is_active bool not null",
        "created_at datetime not null default current_timestamp",
        "updated_at datetime not null default current_timestamp",
        "primary key (id)",
        "create unique index ix_users_username on users (username)",
        "create unique index ix_users_email on users (email)",
    )
    for fragment in expected_fragments:
        assert fragment in sql

    assert sql.count("create table ") == 1
    assert "create table other_" not in sql


def test_initial_migration_downgrade_removes_only_users_objects() -> None:
    sql = _render_migration("downgrade")

    assert "drop index ix_users_email on users" in sql
    assert "drop index ix_users_username on users" in sql
    assert "drop table users" in sql
    assert sql.count("drop table ") == 1
