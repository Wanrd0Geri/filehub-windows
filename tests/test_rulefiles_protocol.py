import json
from pathlib import Path
import subprocess
import sys
import pytest

from filehub.rulefiles import parse_package, encode_package


def document():
    return {'format': 'filehub.rules', 'version': 1, 'id': 'images', 'name': 'Images',
            'bindings': {'input': {'label': 'Input'}, 'output': {'label': 'Output'}, 'unused': {'label': 'Unused'}},
            'variables': {'folder': 'PNG'}, 'rules': [{'id': 'convert', 'name': 'Convert',
            'scope': [{'binding': 'input', 'relative': ''}],
            'condition': {'field': 'extension', 'operator': 'glob', 'value': '.jp*g'},
            'actions': [{'kind': 'image_convert', 'options': {'output_format': 'png', 'destination': {'binding': 'output', 'relative': '${folder}'}}}]}]}


def parse(doc):
    return parse_package(json.dumps(doc).encode())


def test_round_trip_immutable():
    package = parse(document())
    assert encode_package(parse_package(encode_package(package))) == encode_package(package)
    with pytest.raises(TypeError): package.variables['folder'] = 'oops'


@pytest.mark.parametrize('change', [
    lambda d: d.update(version=True), lambda d: d.update(version=2), lambda d: d.update(extra=1),
    lambda d: d['rules'][0]['actions'][0].update(kind='script'),
    lambda d: d['rules'][0]['actions'][0]['options']['destination'].update(relative='../x'),
    lambda d: d['rules'][0]['scope'][0].update(binding='missing'),
    lambda d: d['variables'].update(folder='${OTHER}'), lambda d: d['variables'].update(folder='x/y'),
    lambda d: d['rules'][0].update(enabled=True),
    lambda d: d.update(compatibility={'anything': True}),
    lambda d: d['rules'][0]['actions'][0]['options']['destination'].update(relative='CON'),
    lambda d: d['variables'].update(folder='😀' * 128),
    lambda d: d.update(name='${folder}'),
])
def test_rejections(change, tmp_path):
    doc = document(); change(doc)
    with pytest.raises(ValueError): parse(doc)
    assert list(tmp_path.iterdir()) == []


def test_duplicate_nonfinite_and_size():
    for data in (b'{"format":1,"format":2}', b'{"x":NaN}', b' ' * 2_000_001):
        with pytest.raises(ValueError): parse_package(data)


def test_condition_and_action_limits():
    doc = document(); leaf = doc['rules'][0]['condition']
    for _ in range(5): leaf = {'mode': 'all', 'children': [leaf]}
    doc['rules'][0]['condition'] = leaf
    with pytest.raises(ValueError): parse(doc)
    doc = document(); doc['rules'][0]['actions'] *= 21
    with pytest.raises(ValueError): parse(doc)
    doc = document(); leaf = doc['rules'][0]['condition']
    doc['rules'][0]['condition'] = {'mode': 'all', 'children': [{'mode': 'all', 'children': [leaf] * 60}] * 2}
    with pytest.raises(ValueError): parse(doc)


def test_variables_rejected_outside_expansion_fields():
    doc = document(); doc['rules'][0]['condition']['value'] = '${folder}'
    with pytest.raises(ValueError, match='condition'): parse(doc)


def test_diagnostic_locates_nested_unknown_condition_key():
    doc = document(); doc['rules'][0]['condition'] = {'mode': 'any', 'children': [
        {'field': 'name', 'operator': 'equals', 'value': 'x', 'surprise': 1}]}
    with pytest.raises(ValueError, match=r'children\[0\]'): parse(doc)


@pytest.mark.parametrize('relative', ['C:/secret', '//server/share', 'a//b', 'a\\b', 'a:b', 'COM1.txt', 'x.', 'x ', '/root'])
def test_windows_relative_rejections(relative):
    doc = document(); doc['rules'][0]['scope'][0]['relative'] = relative
    with pytest.raises(ValueError): parse(doc)


def test_expanded_name_limits_and_runtime_tokens():
    doc = document(); doc['variables']['folder'] = 'x' * 255
    parse(doc)
    doc['rules'][0]['actions'] = [{'kind': 'rename', 'options': {'pattern': '${folder}x'}}]
    with pytest.raises(ValueError): parse(doc)
    doc['rules'][0]['actions'][0]['options']['pattern'] = '{prefix}{ext}'
    with pytest.raises(ValueError): parse(doc)
    doc['rules'][0]['actions'][0]['options']['pattern'] = '{stem}_{sequence}{ext}'
    parse(doc)


def test_shared_cli_valid_invalid_no_state(tmp_path):
    source = tmp_path/'rules.json'; source.write_bytes(encode_package(parse(document())))
    command = [sys.executable, '-B', '-X', 'utf8', '-m', 'filehub.rulefiles', 'validate', str(source)]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', cwd=tmp_path)
    assert result.returncode == 0 and json.loads(result.stdout)['valid']
    source.write_bytes(b'{"format":1,"format":2}')
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', cwd=tmp_path)
    assert result.returncode == 1
    assert json.loads(result.stdout)['diagnostics'][0]['path'] == '$'
    assert list(tmp_path.iterdir()) == [source]


def test_schema_complete_example():
    jsonschema = pytest.importorskip('jsonschema')
    schema = json.loads((Path(__file__).parents[1]/'schemas/filehub-rules-v1.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(document())
    doc = document(); doc['rules'][0]['actions'][0]['options']['surprise'] = 1
    with pytest.raises(jsonschema.ValidationError): jsonschema.Draft202012Validator(schema).validate(doc)


def test_schema_core_closed_and_references_exist():
    schema = json.loads((Path(__file__).parents[1]/'schemas/filehub-rules-v1.schema.json').read_text(encoding='utf-8'))
    assert schema['$schema'].endswith('/draft/2020-12/schema')
    assert 'compatibility' not in schema['properties']
    def visit(node):
        if isinstance(node, dict):
            if node.get('type') == 'object' and 'properties' in node:
                assert node['additionalProperties'] is False
            if '$ref' in node: assert node['$ref'].split('/')[-1] in schema['$defs']
            for child in node.values(): visit(child)
        elif isinstance(node, list):
            for child in node: visit(child)
    visit(schema)
