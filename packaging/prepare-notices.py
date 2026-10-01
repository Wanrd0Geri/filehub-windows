"""Collect upstream attribution metadata and referenced license files verbatim."""
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "sandbox/vendor-downloads"

# CPython's _decimal embeds libmpdec. Its BSD notice is separate from PSF LICENSE.
mpdecimal = VENDOR / "mpdecimal-3.12.10.h"
text = mpdecimal.read_text(encoding="utf-8")
notice = text[:text.index("*/") + 2]
target = ROOT / "third_party/python/libmpdec-LICENSE.txt"
target.write_text(notice + "\n\nSource: https://raw.githubusercontent.com/python/cpython/v3.12.10/Modules/_decimal/libmpdec/mpdecimal.h\n", encoding="utf-8")

for source_name, destination in (
    ("qtbase-source/qtbase-6.11.2", "third_party/qt/qtbase"),
    ("pyside-source/pyside-setup-6.11.2", "third_party/qt/pyside"),
):
    source = VENDOR / source_name
    target = ROOT / destination
    shutil.copytree(source / "LICENSES", target / "LICENSES", dirs_exist_ok=True)
    records = []
    for metadata in sorted(source.rglob("qt_attribution.json")):
        relative = metadata.relative_to(source)
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(metadata, output)
        # Upstream qtattributionsscanner accepts raw multiline descriptions.
        data = json.loads(metadata.read_text(encoding="utf-8"), strict=False)
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            entry = dict(entry)
            entry["metadata_path"] = relative.as_posix()
            records.append(entry)
            files = entry.get("LicenseFile", [])
            if isinstance(files, str):
                files = [files]
            for name in files:
                license_path = (metadata.parent / name).resolve()
                if not license_path.is_relative_to(source.resolve()):
                    raise ValueError(f"License path escapes source: {license_path}")
                if not license_path.is_file():
                    raise FileNotFoundError(license_path)
                output = target / license_path.relative_to(source)
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(license_path, output)
    (target / "attributions.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{destination}: {len(records)} upstream attribution entries")

target = ROOT / "third_party/pyinstaller"
target.mkdir(parents=True, exist_ok=True)
shutil.copyfile(ROOT / ".venv/Lib/site-packages/pyinstaller-6.19.0.dist-info/licenses/COPYING.txt",
                target / "COPYING.txt")
