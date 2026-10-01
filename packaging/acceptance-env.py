"""Shared acceptance-only clean child-process environment; never shipped."""
from pathlib import Path
import json
import os

ROOT = Path(__file__).resolve().parents[1]
QA = json.loads((ROOT / "sandbox/task6-qa-session.json").read_text(encoding="utf-8"))

def clean_environment():
    result = {name: value for name, value in os.environ.items()
              if name.upper() not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
              and not name.upper().startswith(("QT_", "PYSIDE"))}
    windows = Path(os.environ["SystemRoot"])
    result["PATH"] = str(windows / "System32") + os.pathsep + str(windows)
    result["LOCALAPPDATA"] = QA["localappdata"]
    return result
