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
        or name in {"coverage.xml", ".pytest_cache", ".ruff_cache", ".venv"}
        or any(part in {"build", "dist", "htmlcov", "logs"} for part in parts)
        or name.endswith((".db", ".duckdb", ".sqlite", ".sqlite3"))
    )


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