from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _is_runtime_artifact(path: str) -> bool:
    parts = Path(path).parts
    name = parts[-1]
    return (
        name == ".env"
        or (name.startswith(".env.") and name != ".env.example")
        or name.startswith(".coverage")
        or name.startswith("debug")
        or name in {
            "coverage.xml",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            ".cache",
            ".venv",
            "venv",
            "__pycache__",
        }
        or any(
            part in {"build", "dist", "htmlcov", "logs", ".venv", "venv"}
            for part in parts
        )
        or name.endswith(
            (
                ".db",
                ".duckdb",
                ".sqlite",
                ".sqlite3",
                ".pyc",
                ".pyo",
                ".pyd",
                ".log",
            )
        )
    )


def test_tracked_files_exclude_runtime_artifacts() -> None:
    tracked_files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    deleted_files = set(
        subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=D"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    )
    assert not [
        path
        for path in tracked_files
        if path not in deleted_files and _is_runtime_artifact(path)
    ], tracked_files


def test_distributions_exclude_runtime_artifacts(tmp_path: Path) -> None:
    distribution_dir = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--out-dir", str(distribution_dir)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    archives = [
        path
        for path in distribution_dir.iterdir()
        if path.is_file() and path.suffix in {".whl", ".gz"}
    ]
    assert {archive.suffix for archive in archives} == {".whl", ".gz"}

    for archive in archives:
        if archive.suffix == ".whl":
            with zipfile.ZipFile(archive) as package:
                names = package.namelist()
        else:
            with tarfile.open(archive) as package:
                names = package.getnames()
        assert not [name for name in names if _is_runtime_artifact(name)], names


def test_packaging_test_runs_with_current_python() -> None:
    assert sys.version_info >= (3, 12)