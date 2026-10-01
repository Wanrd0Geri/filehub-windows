"""Prepare only the pinned Qt WebP plugin, corresponding source and notices.

Developer/build operation; no pip, runtime downloads, encoder, or live state.
Run with the already-pinned .venv Python. Source archive is downloaded only if
missing, verified before any vendor copy. Final packager includes qwebp.dll at
PySide6/plugins/imageformats and preserves conversion source/notices verbatim.
"""
import argparse
import base64
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import shutil
from urllib.request import urlopen
import zipfile

SOURCE_URL = 'https://codeload.github.com/qt/qtimageformats/zip/refs/tags/v6.11.2'
SOURCE_SHA256 = 'a0003652945eeafc8bc28cc639f5941350fe27e91236908306d4733b703a23b5'
PLUGIN_SHA256 = '6b2c53cc4423140c29a6a1eb6dd908016e09d794b5739a05a3a39c8c49a0df8a'
PREFIX = 'qtimageformats-6.11.2/'


def prepare(archive, output):
    from PySide6.QtCore import qVersion
    from PySide6.QtGui import QImageReader, QImageWriter
    dist = distribution('PySide6_Essentials')
    if dist.version != '6.11.2' or qVersion() != '6.11.2':
        raise ValueError('Pinned PySide6_Essentials/Qt 6.11.2 required')
    record = next(item for item in dist.files if str(item).endswith('plugins/imageformats/qwebp.dll'))
    plugin = Path(dist.locate_file(record))
    plugin_hash = hashlib.sha256(plugin.read_bytes()).hexdigest()
    record_hash = base64.urlsafe_b64decode(record.hash.value + '=').hex()
    if plugin_hash != PLUGIN_SHA256 or record_hash != PLUGIN_SHA256:
        raise ValueError('qwebp.dll does not match pinned wheel RECORD/SHA256')
    for query in (QImageReader.supportedImageFormats, QImageWriter.supportedImageFormats):
        if b'webp' not in {bytes(value) for value in query()}:
            raise ValueError('Actual Qt runtime lacks native WebP codec')
    if not archive.is_file():
        archive.parent.mkdir(parents=True, exist_ok=True)
        # Exact developer-owned download file; never overwrite existing content.
        with urlopen(SOURCE_URL, timeout=60) as response, archive.open('xb') as stream:
            shutil.copyfileobj(response, stream)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('QtImageFormats source SHA256 mismatch')
    with zipfile.ZipFile(archive) as source:
        metadata_name = PREFIX + 'src/3rdparty/libwebp/qt_attribution.json'
        metadata = json.loads(source.read(metadata_name))
        if metadata['Version'] != '1.6.0' or metadata['LicenseId'] != 'BSD-3-Clause':
            raise ValueError('Expected bundled libwebp 1.6.0 attribution')
        notices = [name for name in source.namelist() if name.startswith(PREFIX + 'LICENSES/')
                   and not name.endswith('/')]
        notices += [PREFIX + 'src/3rdparty/libwebp/' + name
                    for name in ('COPYING', 'PATENTS', 'AUTHORS', 'qt_attribution.json')]
        for name in notices:
            relative = Path(name.removeprefix(PREFIX))
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Invalid source archive path')
            target = output / 'qtimageformats' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read(name))
    (output / 'bin').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(plugin, output / 'bin/qwebp.dll')
    (output / 'sources').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(archive, output / 'sources/qtimageformats-6.11.2.zip')
    manifest = {
        'scope': 'Image conversion only; no FFmpeg encoder or OpenH264 delivery.',
        'qt_version': qVersion(),
        'plugin': {'name': 'qwebp.dll', 'size': plugin.stat().st_size,
                   'sha256': plugin_hash, 'distribution': 'PySide6_Essentials==6.11.2',
                   'wheel_record_sha256': record_hash,
                   'wheel_tag': 'cp310-abi3-win_amd64',
                   'source_repository': 'https://github.com/qt/qtimageformats',
                   'source_tag': 'v6.11.2',
                   'license': 'LGPL-3.0-only (selected upstream alternative)'},
        'source_archive': {'name': 'qtimageformats-6.11.2.zip', 'url': SOURCE_URL,
                           'sha256': SOURCE_SHA256},
        'libwebp': {'version': metadata['Version'], 'license': metadata['LicenseId'],
                    'source': 'Included verbatim in the corresponding QtImageFormats source archive',
                    'notice': 'qtimageformats/src/3rdparty/libwebp/COPYING',
                    'patent_grant': 'qtimageformats/src/3rdparty/libwebp/PATENTS'},
        'local_source_modifications': [],
        'runtime_network_required': False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / 'provenance.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-archive', type=Path,
                        default=root / 'sandbox/media-core-build/qtimageformats-6.11.2.zip')
    parser.add_argument('--output', type=Path, default=root / 'third_party/conversion')
    args = parser.parse_args()
    result = prepare(args.source_archive, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
