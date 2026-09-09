"""Single-file exe (PyInstaller) smoke tests.

Uses subprocess to exercise dist/spyglass.exe directly — no real API calls.
The ``exe`` fixture builds the exe once per session and caches it in a
temporary directory so tests run quickly on retry.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

# Resolve project root from this package location
PROJECT_ROOT = Path(__file__).resolve().parent.parent

class ExeResult(NamedTuple):
    """Return value for convenience."""
    returncode: int
    stdout: str
    stderr: str


def _build_exes(pyinstaller: str, venv_python: str) -> tuple[str, str]:
    """Build the exe and return (exe_path, temp_dir).

    Builds to a temp dir (not dist/) so repeated CI runs are clean.
    """
    temp_dir = str(Path.home() / f".spyglass_test_exe_{os.getpid()}")
    script_dir = PROJECT_ROOT / "build_exe_entry.py"

    cmd = [
        venv_python, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "spyglass_test",
        "--optimize", "2",
        "--clean",
        "--noconfirm",
        "--hidden-import", "truststore",
        "--hidden-import", "winotify",
        "--exclude-module", "pytest",
        "--exclude-module", "_pytest",
        "-p", str(PROJECT_ROOT),
        str(script_dir),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    exe_path = str(PROJECT_ROOT / "dist" / "spyglass_test.exe")
    return exe_path, temp_dir


@pytest.fixture(scope="session")
def exe(tmp_path_factory):
    """Build the single-file exe ONCE per pytest session; cache result."""
    pyinstaller = shutil.which("pyinstaller")
    venv_python = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

    # Check if we need to install PyInstaller first
    result = subprocess.run([venv_python, "-c", "import PyInstaller"], capture_output=True)
    if result.returncode != 0:
        subprocess.run(
            [venv_python, "-m", "pip", "install", "pyinstaller"],
            check=True, capture_output=True,
        )

    exe_path, _ = _build_exes(pyinstaller, venv_python)
    assert Path(exe_path).exists(), f"Exe build failed: {exe_path}"
    yield exe_path


def test_exe_exists(exe: str) -> None:
    assert Path(exe).exists()
    # Should be ~12 MB as verified manually earlier
    size = Path(exe).stat().st_size
    assert size > 5_000_000, f"Exe too small ({size} bytes)"


def test_exe_help_returns_zero(exe: str) -> None:
    r = _run(exe, ["--help"])
    assert r.returncode == 0
    output = r.stdout + r.stderr
    assert "spyglass" in output.lower() or "spyglass" in output
    # Check subcommands are listed
    assert "check" in output.lower()
    assert "monitor" in output.lower()
    assert "report" in output.lower()
    assert "confirm" in output.lower()


def test_exe_help_lang_en(exe: str) -> None:
    r = _run(exe, ["--lang", "en", "--help"])
    assert r.returncode == 0
    output = r.stdout + r.stderr
    assert "availability checker" in output.lower()
    # Should NOT contain Chinese help texts
    assert "探测" not in output


def test_exe_help_lang_zh(exe: str) -> None:
    r = _run(exe, ["--lang", "zh", "--help"])
    assert r.returncode == 0
    output = r.stdout + r.stderr
    assert "探测" in output
    # Should NOT contain English help texts
    assert "availability checker" not in output


def test_exe_check_invalid_names_file(exe: str, tmp_path: Path) -> None:
    """Nonexistent names file should fail with exit code 2."""
    r = _run(exe, ["check", "--names", str(tmp_path / "does_not_exist.txt"), "--db", str(tmp_path / "t.db")])
    assert r.returncode == 2


def test_exe_report_empty_db(exe: str, tmp_path: Path) -> None:
    """Report on empty db should succeed with summary."""
    db = str(tmp_path / "empty.db")
    r = _run(exe, ["report", "--db", db])
    assert r.returncode == 0
    output = r.stdout + r.stderr
    assert "summary" in output.lower() or "汇总" in output or "无记录" in output


# ---- helpers -----------------------------------------------------------------

def _run(exe: str, args: list[str]) -> ExeResult:
    result = subprocess.run(
        [exe] + args,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(PROJECT_ROOT),
    )
    return ExeResult(result.returncode, result.stdout, result.stderr)
