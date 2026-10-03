"""Offline authoring materials share runtime validation and a fixed inventory."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

import pytest
from filehub.rulefiles import parse_package, encode_package

ROOT=Path(__file__).resolve().parents[1]
EXAMPLES=('01-move.json','02-copy-rename-subfolder.json','03-image-keep-ordered.json',
          '04-image-replace.json','05-archive-compatibility.json')


@pytest.mark.parametrize('name',EXAMPLES)
def test_complete_examples_shared_cli_schema_no_local_state(name,tmp_path):
    jsonschema=pytest.importorskip('jsonschema')
    source=ROOT/'examples/rules-v1'/name
    raw=source.read_bytes();package=parse_package(raw)
    assert parse_package(encode_package(package)).id==package.id
    schema=json.loads((ROOT/'schemas/filehub-rules-v1.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(json.loads(raw))
    result=subprocess.run([sys.executable,'-B','-X','utf8','-m','filehub.rulefiles','validate',str(source)],
        cwd=tmp_path,capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['valid']
    assert list(tmp_path.iterdir())==[]
    text=raw.decode('utf-8')
    assert 'C:\\' not in text and 'F:\\' not in text and 'Gerry' not in text
    assert 'enabled' not in json.loads(raw)
    for rule in package.rules: assert 'enabled' not in rule.to_document()


def test_fixed_bundle_inventory_hashes_and_reproducibility(tmp_path):
    script=ROOT/'packaging/create-rule-guide.py'
    spec=importlib.util.spec_from_file_location('rule_guide030',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    first=tmp_path/'first.zip';second=tmp_path/'second.zip'
    module.build_guide(first);module.build_guide(second)
    assert first.read_bytes()==second.read_bytes()
    expected={'AI规则编写指南.md','filehub-rules-v1.schema.json','manifest.json',*(f'examples/{name}' for name in EXAMPLES)}
    with zipfile.ZipFile(first) as bundle:
        assert len(bundle.namelist())==len(expected) and set(bundle.namelist())==expected
        manifest=json.loads(bundle.read('manifest.json'))
        assert manifest['format']=='filehub.rule-guide' and manifest['version']==1
        assert {entry['path'] for entry in manifest['files']}==expected-{'manifest.json'}
        for entry in manifest['files']:
            raw=bundle.read(entry['path'])
            assert entry['bytes']==len(raw)
            assert entry['sha256']==hashlib.sha256(raw).hexdigest()
        assert bundle.read('AI规则编写指南.md')==(ROOT/'docs/AI规则编写指南.md').read_bytes()
    assert list(tmp_path.glob('*.tmp'))==[]


def test_bundle_cli_requires_explicit_output_and_no_auto_install(tmp_path):
    script=ROOT/'packaging/create-rule-guide.py'
    missing=subprocess.run([sys.executable,'-B','-X','utf8',str(script)],cwd=tmp_path,capture_output=True)
    assert missing.returncode!=0 and list(tmp_path.iterdir())==[]
    output=tmp_path/'offline-guide.zip'
    result=subprocess.run([sys.executable,'-B','-X','utf8',str(script),'--output',str(output)],
        cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONPATH':''})
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['files']==8
    assert list(tmp_path.iterdir())==[output]


def test_guide_standalone_full_examples_match_downloaded_files():
    guide=(ROOT/'docs/AI规则编写指南.md').read_text(encoding='utf-8')
    documents=[json.loads(block) for block in re.findall(r'```json\n(.*?)\n```',guide,re.S)]
    assert len(documents)==len(EXAMPLES)
    assert documents==[json.loads((ROOT/'examples/rules-v1'/name).read_text(encoding='utf-8')) for name in EXAMPLES]
    for document in documents:parse_package(json.dumps(document,ensure_ascii=False).encode('utf-8'))
    assert '纯指南 ZIP 不带 FileHub Python 包' in guide
    assert '不意味着重跑同一个已处理来源' in guide
