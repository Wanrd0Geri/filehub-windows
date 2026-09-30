# Explicit onedir manifest. Nothing under reference/tests/sandbox is swept in.
from pathlib import Path

root = Path(SPECPATH).parent
probe = root / "third_party" / "ffprobe" / "bin"
if not (probe / "ffprobe.exe").is_file():
    raise SystemExit("Run packaging/prepare-ffprobe.ps1 first")
datas = [(str(p), "third_party/" + str(p.relative_to(root / "third_party").parent))
         for p in sorted((root / "third_party").rglob("*"))
         if p.is_file() and "bin" not in p.relative_to(root / "third_party").parts]
datas += [(str(root / "docs" / "第三方许可.md"), "third_party"),
         (str(root / "resources" / "app.ico"), "resources")]
datas += [(str(root / "resources/selftest/tiny.mp4"), "resources/selftest")]
datas += [(str(root / "resources/selftest" / name), "resources/selftest")
          for name in ("tiny-1920-yellow.mp4", "tiny-1920-blue.mp4")]
datas += [(str(root / "sandbox/vendor-downloads" / name), "third_party/sources")
          for name in ("ffmpeg-source.zip", "qtbase-source.zip", "pyside-source.zip")]
binaries = [(str(p), "resources/ffprobe") for p in sorted(probe.iterdir())
            if p.suffix.lower() in (".exe", ".dll")]
webp = root / "third_party/conversion/bin/qwebp.dll"
if not webp.is_file():
    raise SystemExit("Missing reviewed Qt WebP plugin")
binaries += [(str(webp), "PySide6/plugins/imageformats")]
a = Analysis([str(root / "packaging" / "entrypoint.py")],
             pathex=[str(root / "src")], binaries=binaries, datas=datas,
             hiddenimports=["filehub.__main__"],
             excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
                       "PySide6.QtWebEngineWidgets", "PySide6.QtPdf", "PySide6.QtSvg",
                       "PySide6.QtSvgWidgets", "PySide6.QtNetwork", "pytest"], noarchive=False)
# QtBase raster plugins plus the sole reviewed QtImageFormats WebP plugin.
# Replace hook discovery with one exact pinned source; no other addon plugins.
a.binaries = [item for item in a.binaries if Path(item[0]).name.lower() != "qwebp.dll"]
a.binaries += [("PySide6/plugins/imageformats/qwebp.dll", str(webp), "BINARY")]
allowed_images = {"qgif.dll", "qico.dll", "qjpeg.dll", "qwbmp.dll", "qwebp.dll"}
a.binaries = [item for item in a.binaries
              if "imageformats" not in item[0].replace("\\", "/")
              or Path(item[0]).name.lower() in allowed_images]
allowed_qt = {"qt6core.dll", "qt6gui.dll", "qt6widgets.dll"}
a.binaries = [item for item in a.binaries
              if not Path(item[0]).name.lower().startswith("qt6")
              or Path(item[0]).name.lower() in allowed_qt]
allowed_plugins = {"imageformats", "platforms", "styles"}
a.binaries = [item for item in a.binaries
              if "/plugins/" not in item[0].replace("\\", "/")
              or item[0].replace("\\", "/").split("/plugins/")[1].split("/")[0] in allowed_plugins]
# Qt's Windows build imports the OS ICU API, whose symbols are unversioned.
# A PATH-discovered Poppler ICU78 has renamed symbols and must never override it.
ffmpeg_dlls = {"avcodec-62.dll", "avformat-62.dll", "avutil-60.dll"}
a.binaries = [item for item in a.binaries
              if not Path(item[0]).name.lower().startswith(("icu", "api-ms-win-", "ext-ms-win-"))
              # Raster Widgets never requests Qt's Mesa/LLVM software OpenGL fallback.
              and Path(item[0]).name.lower() != "opengl32sw.dll"
              and (Path(item[0]).name.lower() not in ffmpeg_dlls
                   or item[0].replace("\\", "/").startswith("resources/ffprobe/"))]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FileHub",
          console=False, icon=str(root / "resources" / "app.ico"),
          version=str(root / "packaging/version-info.txt"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FileHub")
