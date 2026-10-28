import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "edbcd7d0b3df_create_lost_items_table.py"
)

spec = importlib.util.spec_from_file_location("findai_lost_items_migration", MIGRATION_PATH)
assert spec is not None and spec.loader is not None
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def render_migration(operation_name: str) -> str:
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="mysql",
        opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        getattr(migration, operation_name)()
    return output.getvalue().lower()


def test_migration_creates_only_the_lost_items_table_and_expected_indexes():
    sql = render_migration("upgrade")

    expected_fragments = (
        "create table lost_items (",
        "id integer not null auto_increment",
        "title varchar(200) not null",
        "description text",
        "category varchar(50) not null",
        "location varchar(255) not null",
        "date_lost date not null",
        "image_path varchar(512)",
        "status varchar(20) not null default 'open'",
        "user_id integer not null",
        "created_at datetime not null default current_timestamp",
        "updated_at datetime not null default current_timestamp",
        "constraint fk_lost_items_user_id_users foreign key(user_id) references users (id)",
        "primary key (id)",
        "create index ix_lost_items_status on lost_items (status)",
        "create index ix_lost_items_user_id on lost_items (user_id)",
    )
    for fragment in expected_fragments:
        assert fragment in sql

    assert sql.count("create table ") == 1
    assert "create table users" not in sql
    assert "alter table users" not in sql
    assert "drop table" not in sql


def test_migration_downgrade_drops_only_lost_items_objects():
    sql = render_migration("downgrade")

    assert "drop index ix_lost_items_user_id on lost_items" in sql
    assert "drop index ix_lost_items_status on lost_items" in sql
    assert "drop table lost_items" in sql
    assert sql.count("drop table ") == 1
    assert "drop table users" not in sql
