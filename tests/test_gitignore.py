from pathlib import Path


def test_gitignore_ignores_logs_directory():
    gitignore = Path(".gitignore").read_text(encoding="utf-8").splitlines()

    assert "logs/" in gitignore
