# Image conversion dependency provenance

Only the Qt WebP image plugin is added for 0.2.0. No FFmpeg encoder, OpenH264,
hardware encoder or video-conversion runtime is part of this delivery. Existing
ffprobe media-width probing is outside this dependency addition.

`provenance.json` pins the actual 6.11.2 runtime plugin from the installed
`PySide6_Essentials==6.11.2` Windows wheel against both its wheel RECORD and
SHA256. `bin/qwebp.dll` is an unmodified copy. The corresponding full Qt
ImageFormats v6.11.2 source ZIP is retained under `sources/`, including the
vendored libwebp 1.6.0 source and Qt's source/build system. Selected redistribution
license is Qt's LGPL-3.0-only alternative. Relevant upstream license alternatives
are provided verbatim in `qtimageformats/LICENSES`; libwebp's BSD-3-Clause notice,
AUTHORS and PATENTS grant are retained under `qtimageformats/src/3rdparty/libwebp`.
Qt/PySide base runtime notices continue to come from existing `third_party/qt`.

Prepare with the project's read-only pinned runtime:

```powershell
& .venv/Scripts/python.exe -X utf8 packaging/prepare-conversion.py
```

The preparation script only downloads missing developer source material, checks
its hash, extracts notices, copies the existing plugin and writes provenance. It
does not install a package, modify `.venv`, or need a network at application
runtime. It rejects a runtime version/plugin hash or source hash mismatch.

For a replacement-plugin rebuild, use the retained source ZIP and a compatible
Qt 6.11.2 MSVC x64 developer SDK. From a Visual Studio x64 developer shell:

```text
<Qt6.11.2>/bin/qt-cmake -S qtimageformats-6.11.2 -B build -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TESTS=OFF
cmake --build build --config Release
cmake --install build --config Release --prefix <replacement-runtime>
```

Keep the rebuilt `plugins/imageformats/qwebp.dll` dynamically replaceable along
with the matching Qt runtime; rebuilding is not required to use the app. Original
source has no FileHub patches. The application-level tiny-WebP workaround merely
adds a legal empty RIFF JUNK chunk to generated files shorter than 40 bytes, and
uses the same padding in memory when decoding such inputs; it does not change
native code or original input bytes.

Final packaging must include `qwebp.dll` at `PySide6/plugins/imageformats`, add it
to the existing image-plugin allowlist and keep this directory's source and
notices. The existing spec currently filters this plugin out. Validate JPEG, PNG
and WebP encode/re-read, including a tiny transparent lossless WebP, in the
isolated packaged runtime without developer PATH before accepting an installer.
