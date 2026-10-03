from dataclasses import replace
from pathlib import Path
import subprocess
import pytest
from filehub.rulefiles import compile_package, encode_package
from test_rulefiles_protocol import document, parse


def test_portable_bindings_and_semantic_identity(tmp_path):
    package = parse(document())
    first = compile_package(package, {'input': tmp_path/'a/in', 'output': tmp_path/'a/out'}, {}, frozenset(), state_dir=tmp_path/'state')
    second = compile_package(package, {'input': tmp_path/'b/in', 'output': tmp_path/'b/out'}, {}, frozenset(), state_dir=tmp_path/'state')
    assert not first.diagnostics and not second.diagnostics
    assert first.rules[0].id == second.rules[0].id
    assert first.rules[0].id.startswith('ext_')
    assert first.rules[0].revision != second.rules[0].revision
    renamed = replace(package, rules=(replace(package.rules[0], name='New name'),))
    changed = compile_package(renamed, {'input': tmp_path/'a/in', 'output': tmp_path/'a/out'}, {}, frozenset({'convert'}), state_dir=tmp_path/'state')
    assert first.rules[0].revision == changed.rules[0].revision
    assert changed.rules[0].enabled
    assert str(tmp_path).encode() not in encode_package(package)
    assert not (tmp_path/'a').exists()


def test_missing_used_only(tmp_path):
    package = parse(document())
    result = compile_package(package, {'input': tmp_path/'in'}, {}, frozenset(), state_dir=tmp_path/'state')
    assert result.unresolved == frozenset({'output'})
    assert not result.rules and result.diagnostics


def test_state_overlap_and_case_alias(tmp_path):
    package = parse(document())
    result = compile_package(package, {'input': tmp_path, 'output': tmp_path/'out'}, {}, frozenset(), state_dir=tmp_path/'state')
    assert not result.rules and result.diagnostics
    doc = document(); doc['rules'][0]['scope'].append({'binding': 'output', 'relative': ''})
    package = parse(doc)
    result = compile_package(package, {'input': tmp_path/'in', 'output': Path(str(tmp_path/'IN'))}, {}, frozenset(), state_dir=tmp_path/'state')
    assert not result.rules and result.diagnostics


def test_checked_reparse_path(tmp_path):
    target = tmp_path/'target'; target.mkdir()
    link = tmp_path/'link'
    try: link.symlink_to(target, target_is_directory=True)
    except OSError:
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
        if result.returncode: pytest.skip('reparse fixture creation unavailable')
    result = compile_package(parse(document()), {'input': link, 'output': tmp_path/'out'}, {}, frozenset(), state_dir=tmp_path/'state')
    assert result.diagnostics and not result.rules


def test_binding_root_overlapping_state_even_with_safe_relative(tmp_path):
    doc = document(); doc['rules'][0]['scope'][0]['relative'] = 'safe'
    result = compile_package(parse(doc), {'input': tmp_path, 'output': tmp_path/'out'}, {}, frozenset(), state_dir=tmp_path/'state')
    assert result.diagnostics and not result.rules


def test_bound_path_oserror_is_per_rule_diagnostic(tmp_path,monkeypatch):
    import filehub.rulefiles.compiler as compiler
    original=compiler.checked_path
    def denied(path):
        if path==tmp_path/'in':raise OSError('owned lstat error')
        return original(path)
    monkeypatch.setattr(compiler,'checked_path',denied)
    result=compile_package(parse(document()),{'input':tmp_path/'in','output':tmp_path/'out'}, {},frozenset(),state_dir=tmp_path/'state')
    assert not result.rules and result.diagnostics[0].path=='$.rules[0].scope[0]'
    assert 'lstat error' in result.diagnostics[0].message
