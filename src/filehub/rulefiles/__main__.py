"""Dependency-free authoring validator; no app bootstrap or state access."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from .protocol import MAX_PACKAGE_BYTES, PackageError, parse_package


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m filehub.rulefiles')
    parser.add_argument('command', choices=['validate'])
    parser.add_argument('file', type=Path)
    args = parser.parse_args(argv)
    try:
        with args.file.open('rb') as stream: data = stream.read(MAX_PACKAGE_BYTES + 1)
        package = parse_package(data)
        result = {'valid': True, 'package_id': package.id, 'rules': len(package.rules), 'diagnostics': []}; code = 0
    except (OSError, ValueError) as exc:
        diagnostic = asdict(exc.diagnostic) if isinstance(exc, PackageError) else {'path': '$', 'message': str(exc)[:512]}
        diagnostic['message'] = diagnostic['message'][:512]
        result = {'valid': False, 'diagnostics': [diagnostic]}; code = 1
    print(json.dumps(result, ensure_ascii=False)); return code


if __name__ == '__main__': raise SystemExit(main())
