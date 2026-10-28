"""Portable media paths. Keep runtime inputs/outputs inside this checkout."""
from __future__ import annotations
import os
import re
import shutil
from pathlib import Path
from ass_parser import PROJECT_ROOT

def project_path(value: str | Path) -> Path:
    path = Path(value)
    path = (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
    if not path.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError("Use a file inside this checkout (for example data/input/).")
    return path

def relative_path(path: str | Path) -> str:
    return project_path(path).relative_to(PROJECT_ROOT).as_posix()

def executable(name: str) -> str:
    result = shutil.which(os.environ.get(name.upper() + "_BINARY", name))
    if not result:
        raise FileNotFoundError(f"{name} not found. Add it to PATH or set {name.upper()}_BINARY.")
    return result

def ass_time_to_ms(value: str) -> int:
    match = re.fullmatch(r"(\d+):([0-5]\d):([0-5]\d)[.](\d{1,3})", value)
    if not match:
        raise ValueError(f"Invalid subtitle timestamp: {value!r}")
    h, m, s, fraction = match.groups()
    return (int(h)*3600 + int(m)*60 + int(s))*1000 + int(fraction.ljust(3, "0"))

def ms_to_ffmpeg_time(value: int) -> str:
    if value < 0:
        raise ValueError("Negative media timestamp")
    return f"{value/1000:.3f}"
