"""Fail closed if the release's pinned runtime/license inputs drift."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import json
import sys

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "third_party/components.json").read_text(encoding="utf-8"))
if manifest["redistribution_status"] != "prepared":
    raise SystemExit("Redistribution input preparation is incomplete")
if ".".join(map(str, sys.version_info[:3])) != manifest["python_version"]:
    raise SystemExit("Pinned Python runtime version mismatch")
for relative, expected in manifest["file_hashes"].items():
    actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"SHA256 mismatch: {relative}")
for distribution, expected in manifest["python_distributions"].items():
    if metadata.version(distribution) != expected:
        raise SystemExit(f"Version mismatch: {distribution}")
for archive in manifest["source_archives"]:
    path = root / "sandbox/vendor-downloads" / archive["file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != archive["sha256"]:
        raise SystemExit(f"Corresponding-source SHA256 mismatch: {path.name}")
print("Pinned runtime and notice input hashes verified")
