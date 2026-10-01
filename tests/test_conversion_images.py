"""Real Qt outputs and conservative staging contracts (no publication)."""
import importlib
import struct
import threading
import time
import zlib

import pytest
from PySide6.QtGui import QColor, QImage, QImageReader


def core():
    return importlib.import_module('filehub.conversion')


def source_image(tmp_path, *, width=17, height=11, transparent=False, format='PNG'):
    path = tmp_path / ('source.' + format.lower())
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 0, 0, 0 if transparent else 255))
    assert image.save(str(path), format)
    return path


@pytest.mark.parametrize('format,magic', [('jpeg', b'\xff\xd8'), ('png', b'\x89PNG'), ('webp', b'RIFF')])
def test_generation_encodes_real_requested_format_and_preserves_source(tmp_path, format, magic):
    api = core()
    source = source_image(tmp_path)
    original = source.read_bytes()
    output = tmp_path / '.owned-stage'
    events = []
    result = api.generate(source, output, api.ConversionSpec(output_format=format), progress=events.append)
    assert output.read_bytes().startswith(magic)
    assert output.read_bytes() != original or format == 'png'
    reader = QImageReader(str(output))
    assert bytes(reader.format()).decode() == format
    assert reader.read().size().width() == 17
    assert result.width == 17 and result.height == 11
    assert result.output_fingerprint.sha256 and result.source_fingerprint.sha256
    assert source.read_bytes() == original
    assert events[0].percent == 0 and events[-1].percent == 100
    assert all(a.percent <= b.percent for a, b in zip(events, events[1:]))
    assert result.warnings


@pytest.mark.parametrize('background', ['#FFFFFF', '#000000', '#40A0E0'])
def test_jpeg_transparency_uses_explicit_background(tmp_path, background):
    api = core()
    source = source_image(tmp_path, transparent=True)
    output = tmp_path / '.stage'
    api.generate(source, output, api.ConversionSpec(output_format='jpeg', background=background))
    pixel = QImage(str(output)).pixelColor(8, 5)
    expected = QColor(background)
    assert all(abs(actual - target) <= 3 for actual, target in zip(pixel.getRgb()[:3], expected.getRgb()[:3]))


def test_lossless_webp_preserves_rgba(tmp_path):
    api = core()
    source = source_image(tmp_path, transparent=True)
    output = tmp_path / '.stage'
    api.generate(source, output, api.ConversionSpec(output_format='webp', lossless=True))
    decoded = QImage(str(output))
    assert decoded.hasAlphaChannel()
    assert decoded.pixelColor(2, 2).alpha() == 0
    raw = output.read_bytes()
    assert struct.unpack('<I', raw[4:8])[0] + 8 == len(raw)
    assert len(raw) % 2 == 0


def test_valid_tiny_lossless_webp_input_is_decoded_without_changing_original(tmp_path):
    api = core()
    source = tmp_path / 'tiny.webp'
    raw = bytes.fromhex('524946461a000000574542505650384c0d0000002f10800210071011118888fe0700')
    source.write_bytes(raw)
    output = tmp_path / '.stage'
    result = api.generate(source, output, api.ConversionSpec(output_format='png'))
    assert (result.width, result.height) == (17, 11)
    assert QImage(str(output)).pixelColor(2, 2).alpha() == 0
    assert source.read_bytes() == raw


def test_exif_orientation_applied_once_and_reported(tmp_path):
    api = core()
    source = source_image(tmp_path, width=7, height=13, format='JPEG')
    jpeg = source.read_bytes()
    # Little-endian TIFF with one IFD orientation entry, value 6 = rotate 90 CW.
    exif = b'Exif\0\0II*\0\x08\0\0\0' + struct.pack('<H', 1)
    exif += struct.pack('<HHI', 0x112, 3, 1) + struct.pack('<H', 6) + b'\0\0' + b'\0\0\0\0'
    source.write_bytes(jpeg[:2] + b'\xff\xe1' + struct.pack('>H', len(exif) + 2) + exif + jpeg[2:])
    output = tmp_path / '.stage'
    result = api.generate(source, output, api.ConversionSpec(output_format='png'))
    assert (result.width, result.height) == (13, 7)
    assert result.orientation_applied
    assert QImageReader(str(output)).read().size().width() == 13


def test_animated_png_rejected_instead_of_flattened(tmp_path):
    api = core()
    source = source_image(tmp_path)
    raw = source.read_bytes()
    payload = b'acTL' + struct.pack('>II', 2, 0)
    chunk = struct.pack('>I', 8) + payload + struct.pack('>I', zlib.crc32(payload))
    source.write_bytes(raw[:33] + chunk + raw[33:])
    with pytest.raises(api.ConversionError, match='动画|多页'):
        api.inspect(source, api.ConversionSpec())


def test_corrupt_image_rejected_without_output(tmp_path):
    api = core()
    source = tmp_path / 'broken.png'
    source.write_bytes(b'\x89PNG\r\n\x1a\nnot-an-image')
    output = tmp_path / '.stage'
    with pytest.raises(api.ConversionError):
        api.generate(source, output, api.ConversionSpec())
    assert not output.exists()


def test_bad_png_checksum_rejected_instead_of_reencoded(tmp_path):
    api = core()
    source = source_image(tmp_path)
    raw = bytearray(source.read_bytes())
    raw[29] ^= 0xFF  # IHDR CRC; content itself remains decodable by tolerant readers.
    source.write_bytes(raw)
    with pytest.raises(api.ConversionError, match='损坏|校验'):
        api.generate(source, tmp_path / '.stage', api.ConversionSpec())


def test_jpeg_without_end_marker_rejected_instead_of_tolerated(tmp_path):
    api = core()
    source = source_image(tmp_path, format='JPEG')
    source.write_bytes(source.read_bytes()[:-2])
    with pytest.raises(api.ConversionError, match='损坏|截断'):
        api.inspect(source, api.ConversionSpec())


def test_high_depth_png_rejected_before_normalization(tmp_path):
    api = core()
    source = tmp_path / 'depth16.png'
    image = QImage(12, 8, QImage.Format.Format_RGBA64)
    image.fill(QColor('#AABBCC'))
    assert image.save(str(source), 'PNG')
    with pytest.raises(api.ConversionError, match='16 位|位深'):
        api.inspect(source, api.ConversionSpec())


def test_animated_webp_rejected_by_container_flag(tmp_path):
    api = core()
    source = source_image(tmp_path, format='WEBP')
    data = source.read_bytes()
    # Extended WebP header has animation flag and same canvas dimensions.
    extended = b'VP8X' + struct.pack('<I', 10) + b'\x02\0\0\0\x10\0\0\x0a\0\0'
    raw = data[:12] + extended + data[12:]
    raw = raw[:4] + struct.pack('<I', len(raw)-8) + raw[8:]
    source.write_bytes(raw)
    with pytest.raises(api.ConversionError, match='动画|多页'):
        api.inspect(source, api.ConversionSpec())


def test_memory_cap_rejected_before_decode(tmp_path):
    api = core()
    source = source_image(tmp_path)
    with pytest.raises(api.ConversionError, match='像素|内存'):
        api.inspect(source, api.ConversionSpec(max_pixels=100))


def test_existing_staging_never_overwritten_or_removed(tmp_path):
    api = core()
    source = source_image(tmp_path)
    output = tmp_path / '.stage'
    output.write_bytes(b'foreign-owned')
    with pytest.raises(api.ConversionError):
        api.generate(source, output, api.ConversionSpec())
    assert output.read_bytes() == b'foreign-owned'


@pytest.mark.parametrize('phase', ['start', 'decoded', 'encoded', 'verified', 'complete'])
def test_cancellation_removes_only_owned_staging(tmp_path, phase):
    api = core()
    source = source_image(tmp_path)
    original = source.read_bytes()
    output = tmp_path / '.stage'
    other = tmp_path / '.unrelated'
    other.write_bytes(b'keep')
    cancel = threading.Event()
    def on_progress(event):
        if event.phase == phase:
            cancel.set()
    with pytest.raises(api.ConversionCancelled):
        api.generate(source, output, api.ConversionSpec(), cancel, on_progress)
    assert not output.exists()
    assert source.read_bytes() == original and other.read_bytes() == b'keep'


def test_stage_timeout_discards_generated_file(tmp_path):
    api = core()
    source = source_image(tmp_path)
    output = tmp_path / '.stage'
    def slow_consumer(event):
        if event.phase == 'encoded':
            time.sleep(0.06)
    with pytest.raises(api.ConversionError, match='超时'):
        api.generate(source, output, api.ConversionSpec(timeout_seconds=0.05), progress=slow_consumer)
    assert not output.exists() and QImage(str(source)).width() == 17


def test_changed_capability_binding_rejects_before_staging(tmp_path):
    api = core()
    source = source_image(tmp_path)
    output = tmp_path / '.stage'
    with pytest.raises(api.ConversionError, match='能力变化'):
        api.generate(source, output, api.ConversionSpec(), expected_capability_digest='stale')
    assert not output.exists()


def test_plan_fingerprint_binding_rejects_changed_source(tmp_path):
    api = core()
    source = source_image(tmp_path)
    spec = api.ConversionSpec()
    plan = api.inspect(source, spec)
    source.write_bytes(source.read_bytes() + b'changed')
    with pytest.raises(api.ConversionError, match='指纹|变化'):
        api.generate(source, tmp_path / '.stage', spec, expected_source=plan.source_fingerprint)


def test_generation_guard_prevents_concurrent_source_write(tmp_path):
    api = core()
    source = source_image(tmp_path)
    errors = []
    def mutate(event):
        if event.phase == 'decoded':
            try:
                source.write_bytes(b'bad')
            except OSError as error:
                errors.append(error)
    api.generate(source, tmp_path / '.stage', api.ConversionSpec(), progress=mutate)
    assert errors and QImage(str(source)).width() == 17


def test_capabilities_prove_all_three_actual_codecs():
    caps = core().capabilities()
    assert caps.qt_version == '6.11.2'
    assert set(caps.inputs) == {'jpeg', 'png', 'webp'}
    assert set(caps.outputs) == {'jpeg', 'png', 'webp'}
    assert caps.digest


@pytest.mark.parametrize('changes', [dict(kind='video'), dict(output_format='gif'), dict(quality=101),
                                     dict(background='bad'), dict(max_pixels=0), dict(timeout_seconds=0)])
def test_invalid_settings_rejected(changes):
    api = core()
    with pytest.raises((api.ConversionError, ValueError)):
        api.ConversionSpec(**changes)
