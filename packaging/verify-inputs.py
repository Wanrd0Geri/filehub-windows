"""Fail closed if the release's pinned runtime/license inputs drift."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import json
import re
import sys
import tomllib
import zipfile
import base64
import pefile

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "third_party/components.json").read_text(encoding="utf-8"))
version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
installer = (root / "packaging/installer.iss").read_text(encoding="utf-8")
version_info = (root / "packaging/version-info.txt").read_text(encoding="utf-8")
if version != "0.2.0" or manifest["app_version"] != version or f'#define AppVersion "{version}"' not in installer:
    raise SystemExit("App/installer/input manifest version mismatch")
for key in ("FileVersion", "ProductVersion"):
    if f"StringStruct('{key}', '{version}')" not in version_info:
        raise SystemExit("EXE string version mismatch")
for key in ("filevers", "prodvers"):
    if not re.search(rf"{key}=\(0,\s*2,\s*0,\s*0\)", version_info):
        raise SystemExit("EXE fixed version mismatch")
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
    path = root / archive["relative_path"] if "relative_path" in archive else root / "sandbox/vendor-downloads" / archive["file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != archive["sha256"]:
        raise SystemExit(f"Corresponding-source SHA256 mismatch: {path.name}")

conversion = json.loads((root / "third_party/conversion/provenance.json").read_text(encoding="utf-8"))
if manifest["image_conversion"] != conversion or conversion["qt_version"] != "6.11.2":
    raise SystemExit("Image conversion provenance mismatch")
plugin = root / "third_party/conversion/bin/qwebp.dll"
plugin_sha = "6b2c53cc4423140c29a6a1eb6dd908016e09d794b5739a05a3a39c8c49a0df8a"
source_sha = "a0003652945eeafc8bc28cc639f5941350fe27e91236908306d4733b703a23b5"
if hashlib.sha256(plugin.read_bytes()).hexdigest() != plugin_sha or conversion["plugin"]["sha256"] != plugin_sha:
    raise SystemExit("Reviewed qwebp binary mismatch")
dist = metadata.distribution("PySide6_Essentials")
record = next(item for item in dist.files if str(item).endswith("plugins/imageformats/qwebp.dll"))
if (hashlib.sha256(Path(dist.locate_file(record)).read_bytes()).hexdigest() != plugin_sha
        or base64.urlsafe_b64decode(record.hash.value + "=").hex() != plugin_sha):
    raise SystemExit("qwebp does not match pinned wheel and RECORD")
source = root / "third_party/conversion/sources/qtimageformats-6.11.2.zip"
if hashlib.sha256(source.read_bytes()).hexdigest() != source_sha or conversion["source_archive"]["sha256"] != source_sha:
    raise SystemExit("Reviewed QtImageFormats source mismatch")
with zipfile.ZipFile(source) as archive:
    attribution = json.loads(archive.read("qtimageformats-6.11.2/src/3rdparty/libwebp/qt_attribution.json"))
    if attribution["Version"] != "1.6.0" or attribution["LicenseId"] != "BSD-3-Clause":
        raise SystemExit("libwebp attribution mismatch")
    for material in (root / "third_party/conversion/qtimageformats").rglob("*"):
        if material.is_file():
            relative = material.relative_to(root / "third_party/conversion/qtimageformats").as_posix()
            if material.read_bytes() != archive.read("qtimageformats-6.11.2/" + relative):
                raise SystemExit(f"Modified conversion notice: {relative}")
required = ("LICENSES/LGPL-3.0-only.txt", "LICENSES/BSD-3-Clause.txt",
            "src/3rdparty/libwebp/COPYING", "src/3rdparty/libwebp/PATENTS",
            "src/3rdparty/libwebp/AUTHORS", "src/3rdparty/libwebp/qt_attribution.json")
if any(not (root / "third_party/conversion/qtimageformats" / name).is_file() for name in required):
    raise SystemExit("Missing required conversion license/patent material")

def imports(path):
    with pefile.PE(str(path)) as binary:
        return sorted(entry.dll.decode("ascii").lower() for entry in binary.DIRECTORY_ENTRY_IMPORT)

for name, expected in manifest["ffprobe_imports"].items():
    if imports(root / "third_party/ffprobe/bin" / name) != sorted(value.lower() for value in expected):
        raise SystemExit(f"Frozen ffprobe native imports changed: {name}")
probe_payload = {path.name for path in (root / "third_party/ffprobe/bin").iterdir() if path.is_file()}
if probe_payload != set(manifest["ffprobe_imports"]):
    raise SystemExit("Unexpected ffprobe payload file")
conversion_payload = {path.name for path in (root / "third_party/conversion/bin").iterdir() if path.is_file()}
if conversion_payload != {"qwebp.dll"}:
    raise SystemExit("Unexpected conversion payload: only reviewed qwebp is allowed")
expected_webp = {"qt6gui.dll", "qt6core.dll", "vcruntime140.dll", "kernel32.dll",
                 *[f"api-ms-win-crt-{name}-l1-1-0.dll" for name in ("string", "heap", "math", "utility", "runtime")]}
if set(imports(plugin)) != expected_webp:
    raise SystemExit("Unreviewed qwebp native dependency")
print("0.2.0 metadata, pinned runtime/source/notice hashes, wheel RECORD and native imports verified")
