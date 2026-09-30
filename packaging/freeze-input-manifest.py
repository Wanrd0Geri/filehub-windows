"""Maintainer command: freeze reviewed inputs, never called implicitly by build."""
from pathlib import Path
import hashlib
import json
import tomllib

root = Path(__file__).resolve().parents[1]
previous = json.loads((root / "third_party/components.json").read_text(encoding="utf-8"))
conversion = json.loads((root / "third_party/conversion/provenance.json").read_text(encoding="utf-8"))
app_version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

sources = [
    ("ffmpeg-source.zip", "https://codeload.github.com/FFmpeg/FFmpeg/zip/29e619e767cde9045a75c29bc9a8278ae7b3a98b",
     "29e619e767cde9045a75c29bc9a8278ae7b3a98b", "69ea98adb1b80aabdbecefdb0b545ff19ebcd7c6fc0cea9dd550b02f5b642a21"),
    ("qtbase-source.zip", "https://codeload.github.com/qt/qtbase/zip/refs/tags/v6.11.2",
     "ef55f427f2c8b410d34f8a7681020a3000cf6866", "02d5195d165949318340d27fee6c28d047f0d4682b40c8fa75509a785e686051"),
    ("pyside-source.zip", "https://codeload.github.com/pyside/pyside-setup/zip/refs/tags/v6.11.2",
     "24627cd36e1593adf22eb1f2950e4248e7bcc1ec", "7c357b79dcc0e38da49bcd667dedf342ff7b2c557e2e858dea2a5690f80a37e7"),
]
archives = []
for name, url, commit, expected in sources:
    path = root / "sandbox/vendor-downloads" / name
    assert sha(path) == expected, name
    archives.append({"file": name, "source_url": url, "source_commit": commit,
                     "sha256": expected, "bytes": path.stat().st_size})
conversion_source = root / "third_party/conversion/sources" / conversion["source_archive"]["name"]
assert sha(conversion_source) == conversion["source_archive"]["sha256"]
archives.append({"file": conversion_source.name,
                 "relative_path": conversion_source.relative_to(root).as_posix(),
                 "source_url": conversion["source_archive"]["url"],
                 "source_tag": conversion["plugin"]["source_tag"],
                 "sha256": conversion["source_archive"]["sha256"],
                 "bytes": conversion_source.stat().st_size})
paths = [p for p in (root / "third_party").rglob("*") if p.is_file()
         and p.name != "components.json"]
paths += [root / "resources/app.ico", root / "resources/selftest/tiny.mp4",
          root / "resources/selftest/tiny-1920-yellow.mp4", root / "resources/selftest/tiny-1920-blue.mp4",
          root / "docs/第三方许可.md", root / "packaging/version-info.txt"]
requirements = {}
for line in (root / "packaging/build-requirements.txt").read_text().splitlines():
    name, version = line.split("==")
    requirements[name] = version
manifest = {
    "schema_version": 1, "app_version": app_version, "redistribution_status": "prepared",
    "python_version": "3.12.10", "ffprobe_version": "8.1.3-filehub1",
    "ffprobe_license": "LGPL-2.1-or-later", "qt_license_option": "LGPL-3.0-only",
    "source_archives": archives, "python_distributions": requirements,
    "font_assets": [], "fonts": "Installed Inter/Noto Sans SC, then Windows system fallbacks",
    "file_hashes": {p.relative_to(root).as_posix(): sha(p) for p in sorted(paths)},
    "ffprobe_imports": previous["ffprobe_imports"],
    "image_conversion": conversion,
    "tools": {"inno": {"version": "6.7.3", "source_url": "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe",
                         "sha256": "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"},
              "make": {"version": "4.4.1-3", "source_url": "https://repo.msys2.org/msys/x86_64/make-4.4.1-3-x86_64.pkg.tar.zst",
                         "sha256": "af0bdba17f06fe037f0194069adaa31a8fe45f1a11381501896aea1fae37bd5d"}},
    "evidence_scope": "0.2.0 pinned inputs only; actual packaged acceptance pending. Historical 0.1 installation evidence is separate; no 0.2 live install/uninstall performed.",
}
(root / "third_party/components.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(f"Frozen {len(paths)} inputs and {len(archives)} source archives")
