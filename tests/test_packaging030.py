import ast
import json
from pathlib import Path
import tomllib

ROOT=Path(__file__).resolve().parents[1]


def test_version_inventory_and_help_are_complete_and_explicit():
    inventory=json.loads((ROOT/'packaging/runtime-inventory.json').read_text(encoding='utf-8'))
    assert inventory['version']==tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']=='0.3.0'
    actual=set()
    for path in (ROOT/'src/filehub').rglob('*.py'):
        parts=list(path.relative_to(ROOT/'src').with_suffix('').parts)
        if parts[-1]=='__init__':parts.pop()
        actual.add('.'.join(parts))
    required=set(inventory['required_modules']);excluded=set(inventory['excluded_modules'])
    assert not required & excluded and required | excluded==actual
    assert len(required)==len(inventory['required_modules'])
    assert excluded=={'filehub.ui.templates_page','filehub.ui.condition_editor','filehub.rulefiles.__main__'}
    assert {'filehub.rulefiles.compatibility','filehub.rulefiles.migration','filehub.selftest020',
            'filehub.selftest030','filehub.ui.action_editor'} <= required
    assert len(inventory['help'])==7
    assert {item['destination'] for item in inventory['help']} == {
        'help/AI规则编写指南.md','help/filehub-rules-v1.schema.json',
        *['help/examples/'+path.name for path in (ROOT/'examples/rules-v1').glob('*.json')]}
    for item in inventory['help']:assert (ROOT/item['source']).is_file()
    for name in required:
        path=ROOT/'src'/Path(*name.split('.')).with_suffix('.py')
        if not path.is_file():path=ROOT/'src'/Path(*name.split('.'))/'__init__.py'
        tree=ast.parse(path.read_text(encoding='utf-8'))
        assert not any(isinstance(node,ast.ImportFrom) and node.module in ('condition_editor','templates_page')
            for node in ast.walk(tree)),name


def test_spec_consumes_inventory_and_build_scopes_new_artifacts():
    spec=(ROOT/'packaging/filehub.spec').read_text(encoding='utf-8')
    assert "hiddenimports=inventory['required_modules']" in spec
    assert "*inventory['excluded_modules']" in spec
    assert "for item in inventory['help']" in spec
    build=(ROOT/'packaging/build.ps1').read_text(encoding='utf-8')
    assert 'Get-ChildItem dist/installer/*.exe' not in build
    assert 'FileHub-0.3.0-windows-x64-setup.exe' in build
    assert 'create-rule-guide.py' in build and 'PYTHONDONTWRITEBYTECODE' in build
