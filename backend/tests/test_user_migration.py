import ast
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20261025_01_create_users_table.py"
)


def test_initial_user_migration_declares_only_users_table_operations() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    def operation_calls(function_name: str) -> list[ast.Call]:
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        )
        return [
            statement.value
            for statement in function.body
            if isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == "op"
        ]

    upgrades = operation_calls("upgrade")
    downgrades = operation_calls("downgrade")

    assert [call.func.attr for call in upgrades] == [
        "create_table",
        "create_index",
        "create_index",
    ]
    create_table = upgrades[0]
    assert ast.literal_eval(create_table.args[0]) == "users"
    columns = {
        ast.literal_eval(column.args[0])
        for column in create_table.args[1:]
        if isinstance(column, ast.Call)
        and isinstance(column.func, ast.Attribute)
        and column.func.attr == "Column"
    }
    assert columns == {
        "id",
        "username",
        "email",
        "hashed_password",
        "is_active",
        "created_at",
        "updated_at",
    }
    for index_call in upgrades[1:]:
        assert ast.literal_eval(index_call.args[1]) == "users"
        assert index_call.keywords[0].arg == "unique"
        assert ast.literal_eval(index_call.keywords[0].value) is True

    assert [call.func.attr for call in downgrades] == [
        "drop_index",
        "drop_index",
        "drop_table",
    ]
    for index_call in downgrades[:2]:
        table_name = next(
            keyword.value
            for keyword in index_call.keywords
            if keyword.arg == "table_name"
        )
        assert ast.literal_eval(table_name) == "users"
    assert ast.literal_eval(downgrades[2].args[0]) == "users"
