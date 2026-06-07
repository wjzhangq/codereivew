import os
import shutil
import subprocess
import tempfile
from pathlib import Path

os.environ.setdefault("CR_CONFIG", str(Path(__file__).parents[2] / "config" / "config.example.yaml"))

import pytest


@pytest.fixture(scope="session")
def test_repo() -> str:
    d = tempfile.mkdtemp(prefix="cr_test_repo_")
    run = lambda *a: subprocess.run(["git", *a], cwd=d, check=True, capture_output=True)
    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Tester")
    (Path(d) / "src" / "auth").mkdir(parents=True)
    (Path(d) / "src" / "auth" / "login.py").write_text(
        "def login(u, p):\n    return verify(u, p)\ndef verify(u, p):\n    return True\n")
    run("add", "-A"); run("commit", "-qm", "feat: add auth")
    (Path(d) / "src" / "auth" / "login.py").write_text(
        "def login(u, p):\n    return verify(u, p)\ndef logout(u):\n    pass\n")
    run("add", "-A"); run("commit", "-qm", "wip")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def _init_db():
    from app.db.session import init_db
    init_db()
