# Image conversion core — Sol handoff and frozen interface

Scope reflects the latest user direction: image conversion only. Video encoding
was stopped before any build; no FFmpeg encoder/OpenH264 implementation or
redistribution was added. Diagnostic OpenH264 download stays in owned sandbox.
Original F checkout, live FileHub, registry, shared `.venv` and user folders were
not modified. No stage/commit and no child agents. Engine/journal/rules/UI/shared
packaging manifests were not edited by this task.

## Frozen API

Public module: `filehub.conversion`. `ConversionSpec` is frozen and accepts:

| Field | Default | Contract |
| --- | --- | --- |
| kind | image | Other kinds rejected |
| output_format | jpeg | jpeg/png/webp; `extension` maps to .jpg/.png/.webp |
| quality | 90 | Integer 0–100; JPEG quality and lossy WebP |
| background | #FFFFFF | Six-digit opaque RGB; transparent JPEG composition |
| lossless | false | Boolean; WebP lossless uses Qt quality=100 |
| timeout_seconds | 60 | Positive finite ≤3600 seconds, checked at stage boundaries |
| max_pixels | 40000000 | Positive ≤40M, validated before decode |

`capabilities()` returns `ConversionCapabilities(qt_version, inputs, outputs,
digest)` using actual native reader/writer registration. Only JPEG, PNG, WebP
are exposed. Codec signature binds Qt version plus available image formats.

`inspect(source, spec=None)` / alias `validate` fully decodes under source Guard,
returning `ConversionPlan(source, spec, source_fingerprint, input_format, width,
height, orientation_applied, capability_digest, warnings)`. Oriented dimensions
are the expected output dimensions. Input format follows detected content.

`generate(source, staging, spec=None, cancel_event=None, progress=None, *,
expected_source=None, expected_capability_digest=None)` returns
`ConversionResult(source, staging, source_fingerprint, output_fingerprint,
input_format, output_format, width, height, orientation_applied,
capability_digest, warnings)`. Integration must pass the plan's expected source
fingerprint and capability digest; it also owns binding the exact spec/target.
Errors are `ConversionError`; cancellation subclasses it as
`ConversionCancelled`. `cancel_event` supports `is_set()`, e.g. threading.Event.

Progress callback receives `ConversionProgress(phase, percent)`:
start=0, decoded=35, encoded=75, verified=95, complete=100. This is codec-stage
progress, not within-codec pixel progress. Native Qt decode/encode calls cannot
be interrupted mid-call: cancellation/timeout is detected upon return and owned
staging is discarded. Do not advertise a hard realtime timeout or cancellation.
Use the independent single conversion worker; this core holds no global lock.

## Safety, real outputs and limits

Source Guard prevents simultaneous writes, rename and deletion, including held
named streams, and fingerprints before/after decoding/generation. Staging is
`CREATE_NEW` under a held read/write/delete handle with no write/delete sharing.
Qt borrows this descriptor without re-opening the path. Cleanup removes only
the exact created handle, never a caller's existing path. Successful staging is
closed and fingerprinted; engine must hold/validate it again before publication.
No final filename is selected, no publication occurs and source is never deleted.
Task3 implements retained-copy or transactional in-place replacement/undo.

Qt writes actual JPEG/PNG/WebP bytes; output is fully decoded again and checked
for requested format/dimensions, then fingerprinted. PNG is lossless. JPEG
transparent pixels are composed on white, black or custom RGB. EXIF orientation
is applied once by autoTransform. WebP lossy quality=100 is clamped to99 so the
explicit lossless toggle remains authoritative. No resize is performed.

Reject unsupported formats, animated/multipage input, APNG acTL, animated WebP
ANIM/ANMF/VP8X flag, invalid container lengths/PNG CRC, missing JPEG EOI,
undecodable input, PNG >8-bit and decoded depth>32. Metadata fidelity is not
promised (EXIF/text/ICC/times/ADS); this is not an archival/pro color/HDR pipeline.
Maximum input size is256MiB; maximum decode is40M pixels (about160MB per RGBA
surface). Composition, plugin working buffers and validation may transiently
use several such surfaces, roughly480–640MB plus encoded input/output overhead.
Allocation failure is reported, and Qt's own allocation guard remains enabled.

Native Qt6.11.2 qwebp `ensureScanned` requires40byte input before inspecting
features. Valid tiny lossless WebP can be34bytes. Inputs get a legal empty RIFF
JUNK chunk **in memory only**; generated outputs below40bytes get the same empty
chunk with a corrected RIFF length. Native plugin is unmodified. Tests read the
result via ordinary `QImageReader(path)` and validate RIFF length/alignment and
alpha. Root independently confirmed a1×1 transparent42B file decodes normally.

## Dependencies and precise packaging delta

`packaging/prepare-conversion.py` uses the pinned read-only `.venv`, optionally
fetches missing developer source, verifies source/plugin hashes, verifies wheel
RECORD, copies qwebp and retains full corresponding source/license materials.
Run succeeded with Qt/PySide6_Essentials6.11.2. No pip or runtime network.

- qwebp.dll:564536B, SHA256
  `6b2c53cc4423140c29a6a1eb6dd908016e09d794b5739a05a3a39c8c49a0df8a`.
- QtImageFormats v6.11.2 ZIP:3041992B, SHA256
  `a0003652945eeafc8bc28cc639f5941350fe27e91236908306d4733b703a23b5`.
- Complete source ZIP is `third_party/conversion/sources`; notices and selected
  LGPL3 license alternatives are `third_party/conversion/qtimageformats`.
- Vendored libwebp1.6.0 BSD3 COPYING/AUTHORS/PATENTS/qt_attribution retained;
  corresponding full code is within the source ZIP. Provenance and replacement
  plugin rebuild instructions are in `third_party/conversion`.
- Final packager must allow `qwebp.dll` in `packaging/filehub.spec`'s Qt image
  allowlist and place it at `PySide6/plugins/imageformats`. It may use the pinned
  `third_party/conversion/bin/qwebp.dll` copy as an explicit binary.
- Preserve conversion source ZIP/notices, update third-party notice and input
  manifests/hashes and payload audit allowlists. Existing spec's recursive
  non-bin third_party data already picks up conversion notices/source ZIP.
- Packaged smoke must test real JPEG/PNG/WebP and tiny transparent lossless WebP
  without developer PATH. No additional native encoder/DLL dependency is needed.

## Verification and ownership freeze

Initial RED:25 focused real-output/safety/settings tests failed because API was
absent. GREEN reached26 after tiny-WebP regression, then33 after corruption,
16-bit/animation, stage timeout, capability binding and completion-cancel cases.
Final focused command:

```powershell
& .venv/Scripts/python.exe -X utf8 -m pytest tests/test_conversion_images.py --basetemp=sandbox/media-core-final -q --junitxml=sandbox/media-core-build/pytest-images.xml
```

Result:33 passed, no failures. Real temporary JPEG/PNG/WebP outputs are retained
under owned test sandbox. Full suite is intentionally reserved to root's final
combined gate, per task brief. Preparation script and emitted hash/RECORD
provenance verified directly; no standalone video tests/builds were run.

All owned deliverable files are frozen on handoff: new conversion models/images/
exports, `tests/test_conversion_images.py`, `third_party/conversion/*`,
`packaging/prepare-conversion.py` and this report. No active owned process/tool
session remains. Transaction/undo, rule action, planner/runner/UI and packaged
acceptance are pending tasks outside this backend scope.
