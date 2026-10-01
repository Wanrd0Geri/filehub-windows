"""Bounded Qt codecs with source guards and exclusive generated-output staging.

Run on the single dedicated conversion worker. Cancellation and timeout are
checked between native codec calls; a running QImage codec call is not forcibly
interrupted. This module never renames/publishes output into a final location.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import struct
import time
import zlib

from PySide6.QtCore import QByteArray, QBuffer, QFile, QIODevice, qVersion
from PySide6.QtGui import QColor, QImage, QImageIOHandler, QImageReader, QImageWriter, QPainter

from ..models import checked_path
from ..platform.windows import Guard
from .models import (ConversionCapabilities, ConversionCancelled, ConversionError,
                     ConversionPlan, ConversionProgress, ConversionResult, ConversionSpec)

_FORMATS = ('jpeg', 'png', 'webp')
_MAX_FILE_BYTES = 256 * 1024 * 1024
_WARNINGS = ('输出不保证保留 EXIF、文本、ICC、时间及其他元数据或命名流。',
             '按图片方向信息应用旋转；不支持动画、多页、HDR、16 位或专业色彩工作流。',
             '取消和超时在解码/编码阶段结束后生效，不会保留取消的临时输出。')


def capabilities():
    """Query the loaded native Qt plugins, not a filename-based promise."""
    readers = {bytes(value).decode('ascii').lower() for value in QImageReader.supportedImageFormats()}
    writers = {bytes(value).decode('ascii').lower() for value in QImageWriter.supportedImageFormats()}
    inputs = tuple(value for value in _FORMATS if value in readers)
    outputs = tuple(value for value in _FORMATS if value in writers)
    signature = f'{qVersion()}|{",".join(inputs)}|{",".join(outputs)}'
    return ConversionCapabilities(qVersion(), inputs, outputs, hashlib.sha256(signature.encode()).hexdigest())


@contextmanager
def _qt_file(guard, *, writing=False):
    """Borrow the held native fd without opening/replacing the guarded path."""
    guard.stream.flush()
    guard.stream.seek(0)
    file = QFile()
    mode = QIODevice.OpenModeFlag.ReadWrite if writing else QIODevice.OpenModeFlag.ReadOnly
    if not file.open(guard.stream.fileno(), mode, QFile.FileHandleFlag.DontCloseHandle):
        raise ConversionError(f'无法读取临时媒体：{file.errorString()}')
    try:
        if not file.seek(0):
            raise ConversionError('无法定位媒体文件')
        # Qt 6.11.2 qwebp requires sizeof(WebPBitstreamFeatures) (40 bytes)
        # before inspecting features. Valid tiny lossless WebP can be 34 bytes.
        # Supply a legal empty RIFF JUNK chunk in memory; never alter the source.
        if not writing and file.size() < 40 and bytes(file.peek(12))[8:12] == b'WEBP':
            buffer = QBuffer()
            buffer.setData(QByteArray(_pad_tiny_webp(bytes(file.readAll()))))
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            try:
                yield buffer
            finally:
                buffer.close()
        else:
            yield file
    finally:
        file.close()


def _pad_tiny_webp(data):
    if len(data) < 40 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        data += b'JUNK\0\0\0\0'
        data = data[:4] + struct.pack('<I', len(data) - 8) + data[8:]
    return data


class _Checkpoints:
    def __init__(self, spec, cancel_event, progress):
        self.spec, self.cancel_event, self.progress = spec, cancel_event, progress
        self.started = time.monotonic()

    def check(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise ConversionCancelled('图片转换已取消，原件保留')
        if time.monotonic() - self.started > self.spec.timeout_seconds:
            raise ConversionError('图片转换分阶段超时，原件保留')

    def emit(self, phase, percent):
        self.check()
        if self.progress is not None:
            self.progress(ConversionProgress(phase, percent))
        self.check()


def _container_checks(guard, format):
    """Reject APNG/animated WebP even if Qt would decode only their first image."""
    size = guard.fingerprint().size
    stream = guard.stream
    stream.seek(0)
    if format == 'png':
        if stream.read(8) != b'\x89PNG\r\n\x1a\n':
            raise ConversionError('PNG 文件头损坏')
        seen_end = False
        while header := stream.read(8):
            if len(header) != 8:
                raise ConversionError('PNG 块截断')
            length, tag = struct.unpack('>I4s', header)
            if length > _MAX_FILE_BYTES or stream.tell() + length + 4 > size:
                raise ConversionError('PNG 块长度无效')
            if tag == b'acTL':
                raise ConversionError('不支持动画或多页图片')
            crc = zlib.crc32(tag)
            if tag == b'IHDR':
                data = stream.read(length)
                if len(data) != 13 or data[8] > 8:
                    raise ConversionError('不支持损坏、HDR 或 16 位 PNG')
                crc = zlib.crc32(data, crc)
            else:
                remaining = length
                while remaining:
                    data = stream.read(min(remaining, 65536))
                    if not data:
                        raise ConversionError('PNG 图片截断')
                    crc = zlib.crc32(data, crc)
                    remaining -= len(data)
            if struct.unpack('>I', stream.read(4))[0] != crc:
                raise ConversionError('PNG 块校验失败，图片损坏')
            if tag == b'IEND':
                seen_end = True
                break
        if not seen_end:
            raise ConversionError('PNG 缺少结束块')
    elif format == 'webp':
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b'RIFF' or header[8:] != b'WEBP':
            raise ConversionError('WebP 文件头损坏')
        declared = struct.unpack('<I', header[4:8])[0] + 8
        if declared != size:
            raise ConversionError('WebP 文件长度无效')
        while stream.tell() < size:
            header = stream.read(8)
            if len(header) != 8:
                raise ConversionError('WebP 块截断')
            tag, length = struct.unpack('<4sI', header)
            if stream.tell() + length + (length & 1) > size:
                raise ConversionError('WebP 块长度无效')
            if tag in (b'ANIM', b'ANMF'):
                raise ConversionError('不支持动画或多页图片')
            if tag == b'VP8X':
                data = stream.read(length)
                if len(data) != 10 or data[0] & 0x02:
                    raise ConversionError('不支持动画或损坏的 WebP')
            else:
                stream.seek(length, 1)
            if length & 1:
                stream.read(1)
    elif format == 'jpeg':
        stream.seek(-2, 2)
        if stream.read(2) != b'\xff\xd9':
            raise ConversionError('JPEG 图片缺少结束标记，文件损坏或截断')
    stream.seek(0)


def _read(guard, spec, caps):
    if not 0 < os.fstat(guard.stream.fileno()).st_size <= _MAX_FILE_BYTES:
        raise ConversionError('图片文件为空或超过 256 MiB 上限')
    before = guard.fingerprint()
    with _qt_file(guard) as file:
        reader = QImageReader(file)
        reader.setDecideFormatFromContent(True)
        format = bytes(reader.format()).decode('ascii').lower()
        if format not in caps.inputs:
            raise ConversionError('输入仅支持静态 JPEG、PNG、WebP；格式不支持或插件缺失')
    _container_checks(guard, format)
    with _qt_file(guard) as file:
        reader = QImageReader(file)
        reader.setDecideFormatFromContent(True)
        if not reader.canRead():
            raise ConversionError(f'图片损坏或无法解码：{reader.errorString()}')
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > spec.max_pixels:
            raise ConversionError('图片像素超过上限或尺寸无效，已避免大内存分配')
        if reader.imageCount() > 1:
            raise ConversionError('不支持动画或多页图片')
        orientation = reader.transformation() != QImageIOHandler.Transformation.TransformationNone
    with _qt_file(guard) as file:
        reader = QImageReader(file)
        reader.setDecideFormatFromContent(True)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            raise ConversionError(f'图片损坏、解码失败或内存不足：{reader.errorString()}')
        if image.width() * image.height() > spec.max_pixels or image.depth() > 32:
            raise ConversionError('不支持超限、HDR 或高位深图片')
    if guard.fingerprint() != before:
        raise ConversionError('源文件指纹变化，请重新预览')
    return before, format, orientation, image


def inspect(source, spec=None):
    """Read/validate input and bind immutable settings, fingerprint and codecs."""
    spec = spec or ConversionSpec()
    caps = capabilities()
    if spec.output_format not in caps.outputs:
        raise ConversionError('所选输出格式的 Qt 编码插件不可用')
    try:
        source = checked_path(source)
        with Guard(source) as guard:
            fingerprint, format, oriented, image = _read(guard, spec, caps)
            return ConversionPlan(source, spec, fingerprint, format, image.width(), image.height(),
                                  oriented, caps.digest, _WARNINGS)
    except ConversionError:
        raise
    except (OSError, ValueError, MemoryError) as error:
        raise ConversionError(f'图片验证失败：{error}') from error


validate = inspect


def generate(source, staging, spec=None, cancel_event=None, progress=None, *,
             expected_source=None, expected_capability_digest=None):
    """Create only a nonexistent caller-owned staging path; verify actual output.

    Pass the plan's expected_source and expected_capability_digest at execution.
    Returns a closed, fingerprinted staging file for engine publication. Caller
    must publish atomically or discard it; this function never chooses a target.
    """
    spec = spec or ConversionSpec()
    checkpoint = _Checkpoints(spec, cancel_event, progress)
    output = None
    try:
        checkpoint.emit('start', 0)
        source, staging = checked_path(source), checked_path(staging)
        if source == staging or not staging.parent.is_dir():
            raise ConversionError('临时输出路径无效，必须使用独立文件且父目录已存在')
        caps = capabilities()
        if expected_capability_digest is not None and caps.digest != expected_capability_digest:
            raise ConversionError('图片编解码能力变化，请重新预览')
        if spec.output_format not in caps.outputs:
            raise ConversionError('所选输出格式的 Qt 编码插件不可用')
        with Guard(source) as original:
            if expected_source is not None and original.fingerprint() != expected_source:
                raise ConversionError('源文件指纹变化，请重新预览')
            fingerprint, format, oriented, image = _read(original, spec, caps)
            if expected_source is not None and fingerprint != expected_source:
                raise ConversionError('源文件指纹变化，请重新预览')
            checkpoint.emit('decoded', 35)
            if spec.output_format == 'jpeg' and image.hasAlphaChannel():
                flattened = QImage(image.size(), QImage.Format.Format_RGB32)
                if flattened.isNull():
                    raise ConversionError('图片背景处理内存不足')
                flattened.fill(QColor(spec.background))
                painter = QPainter(flattened)
                try:
                    painter.drawImage(0, 0, image)
                finally:
                    painter.end()
                image = flattened
            # CREATE_NEW + no write/delete sharing; removal is by this held handle.
            output = Guard(staging, create=True, destructive=True)
            with _qt_file(output, writing=True) as file:
                writer = QImageWriter(file, spec.output_format.encode('ascii'))
                if spec.output_format != 'png':
                    # Qt's corresponding qwebp source selects lossless at quality=100.
                    quality = 100 if spec.output_format == 'webp' and spec.lossless else spec.quality
                    if spec.output_format == 'webp' and not spec.lossless:
                        quality = min(quality, 99)
                    writer.setQuality(quality)
                if not writer.write(image):
                    raise ConversionError(f'图片编码失败或内存不足：{writer.errorString()}')
                if not file.flush():
                    raise ConversionError('临时图片写入失败')
            output.flush()
            if spec.output_format == 'webp' and output.fingerprint().size < 40:
                # Make our emitted file interoperable with the native reader,
                # including readers outside this backend, without pixel changes.
                output.stream.seek(0)
                padded = _pad_tiny_webp(output.stream.read())
                output.stream.seek(0)
                output.stream.write(padded)
                output.flush()
            checkpoint.emit('encoded', 75)
            with _qt_file(output) as file:
                reader = QImageReader(file)
                reader.setDecideFormatFromContent(True)
                actual_format = bytes(reader.format()).decode('ascii').lower()
                actual = reader.read()
                if (actual_format != spec.output_format or actual.isNull()
                        or actual.size() != image.size() or reader.imageCount() > 1):
                    raise ConversionError('生成图片格式或尺寸验证失败')
            output_fingerprint = output.fingerprint()
            if original.fingerprint() != fingerprint:
                raise ConversionError('源文件指纹变化，已取消生成输出')
            checkpoint.emit('verified', 95)
            result = ConversionResult(source, staging, fingerprint, output_fingerprint, format,
                                      spec.output_format, image.width(), image.height(), oriented,
                                      caps.digest, _WARNINGS)
            checkpoint.emit('complete', 100)
            output.close()
            output = None
            return result
    except ConversionError:
        raise
    except (OSError, ValueError, MemoryError) as error:
        raise ConversionError(f'图片转换失败，原件保留：{error}') from error
    finally:
        if output is not None:
            try:
                output.remove()
            finally:
                output.close()
