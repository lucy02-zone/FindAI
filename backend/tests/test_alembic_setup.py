import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db.base import Base
from app.models import User  # noqa: F401 - registers model metadata

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_alembic_uses_application_migration_directory_and_metadata() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    script_directory = ScriptDirectory.from_config(config)

    assert script_directory.dir == str(BACKEND_DIR / "alembic")
    assert (BACKEND_DIR / "alembic" / "env.py").is_file()
    assert "users" in Base.metadata.tables
    assert User.__table__.metadata is Base.metadata


def test_alembic_can_generate_offline_sql_without_a_database() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from alembic.config import main; main()",
            "upgrade",
            "base",
            "--sql",
        ],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "BEGIN" in result.stdout
    assert "COMMIT" in result.stdout
