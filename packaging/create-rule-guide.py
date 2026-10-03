"""Build a deterministic offline Help bundle using only Python's standard library."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import zipfile

EXAMPLES = ('01-move.json', '02-copy-rename-subfolder.json', '03-image-keep-ordered.json',
            '04-image-replace.json', '05-archive-compatibility.json')


def build_guide(output: Path, *, source_root: Path | None = None) -> dict:
    source_root = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[1]
    output = Path(output)
    if output.suffix.casefold() != '.zip': raise ValueError('Explicit output must be a .zip file')
    inventory = {'AI规则编写指南.md': source_root/'docs/AI规则编写指南.md',
                 'filehub-rules-v1.schema.json': source_root/'schemas/filehub-rules-v1.schema.json',
                 **{f'examples/{name}': source_root/'examples/rules-v1'/name for name in EXAMPLES}}
    files = {name: path.read_bytes() for name, path in sorted(inventory.items())}
    manifest = {'format': 'filehub.rule-guide', 'version': 1,
                'files': [{'path': name, 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}
                          for name, raw in files.items()]}
    files['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.rule-guide-', suffix='.tmp', dir=output.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, raw in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                bundle.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        with open(temporary, 'r+b') as stream: os.fsync(stream.fileno())
        with zipfile.ZipFile(temporary) as bundle:
            if bundle.testzip() is not None or set(bundle.namelist()) != set(files):
                raise ValueError('Guide ZIP verification failed')
            for name, raw in files.items():
                if bundle.read(name) != raw: raise ValueError('Guide ZIP byte verification failed')
        digest = sha256(Path(temporary).read_bytes()).hexdigest()
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return {'files': len(files), 'sha256': digest}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='Explicit destination ZIP path')
    args = parser.parse_args(argv)
    print(json.dumps(build_guide(args.output), ensure_ascii=False))


if __name__ == '__main__': main()
