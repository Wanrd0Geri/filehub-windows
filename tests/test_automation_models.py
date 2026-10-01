from dataclasses import replace
import json
import pytest

from filehub.automation.models import Action, ConditionGroup, Predicate, Rule, RuleSet, RuleStore


def rule(**kwargs):
    return Rule(name='图片归档', condition=Predicate('extension', 'equals', 'PNG'),
                actions=(Action('rename', {'pattern': '{stem}_完成{ext}'}),), **kwargs)


def test_semantic_revision_ignores_display_but_binds_actions_and_scope(tmp_path):
    original = rule()
    renamed = replace(original, name='另一名称', enabled=True)
    assert original.revision == renamed.revision
    assert RuleSet((original,)).revision != RuleSet((renamed,)).revision
    changed = replace(original, actions=(Action('rename', {'pattern': '{stem}_新版{ext}'}),))
    assert original.revision != changed.revision
    assert original.revision != replace(original, scope=(str(tmp_path),)).revision


def test_ruleset_reorder_duplicate_delete_and_immutable_definition():
    first, second = rule(), rule()
    rules = RuleSet((first, second))
    assert rules.reorder((second.id, first.id)).rules == (second, first)
    assert rules.reorder((second.id, first.id)).revision != rules.revision
    duplicate = rules.duplicate(first.id, '副本')
    assert len(duplicate.rules) == 3
    assert duplicate.rules[-1].id not in {first.id, second.id}
    assert not duplicate.rules[-1].enabled
    assert duplicate.rules[-1].revision == first.revision
    assert len(duplicate.delete(first.id).rules) == 2
    with pytest.raises(TypeError): first.actions[0].options['pattern'] = 'bad'
    with pytest.raises(ValueError): rules.reorder((first.id, first.id))


def test_store_missing_read_only_roundtrip_and_stale_save(tmp_path):
    state = tmp_path/'absent'
    store = RuleStore(state)
    initial = store.load()
    assert not state.exists()
    saved = store.save(RuleSet((rule(enabled=True),)), expected_revision=initial.revision)
    assert store.load() == saved
    assert store.load().rules[0].enabled
    with pytest.raises(ValueError): store.save(initial, expected_revision=initial.revision)
    assert store.load() == saved


def test_import_disabled_fresh_ids_append_and_atomic_failure(tmp_path):
    store = RuleStore(tmp_path/'state')
    saved = store.save(RuleSet((rule(enabled=True),)))
    exported = store.export_document()
    imported = store.import_document(exported)
    assert imported.rules[0] == saved.rules[0]
    assert not imported.rules[1].enabled
    assert imported.rules[1].id != imported.rules[0].id
    assert imported.rules[1].revision == imported.rules[0].revision
    before = store.path.read_bytes()
    bad = json.loads(json.dumps(exported))
    bad['rules'].append(dict(bad['rules'][0], id='bad', actions=[{'kind': 'script', 'options': {}}]))
    with pytest.raises(ValueError): store.import_document(bad)
    assert store.path.read_bytes() == before
    assert set(exported) == {'version', 'rules'}


@pytest.mark.parametrize('condition', [
    {'mode': 'all', 'children': []},
    {'field': 'size_bytes', 'operator': 'ge', 'value': True},
    {'field': 'size_bytes', 'operator': 'ge', 'value': float('nan')},
    {'field': 'stable_age_seconds', 'operator': 'lt', 'value': -1},
    {'field': 'created', 'operator': 'ge', 'value': '2026-01-01T00:00:00'},
    {'field': 'name', 'operator': 'regex', 'value': '.*'},
    {'field': 'unknown', 'operator': 'equals', 'value': 'x'},
    {'field': 'name', 'operator': 'equals', 'value': 'x', 'script': 'bad'},
])
def test_reject_unsupported_condition_atomically(tmp_path, condition):
    store = RuleStore(tmp_path/'state')
    saved = store.save(RuleSet((rule(),)))
    doc = saved.to_document()
    doc['rules'][0]['condition'] = condition
    with pytest.raises(ValueError): store.import_document(doc)
    assert store.load() == saved


def test_limits_groups_leaves_actions_and_duplicate_ids():
    leaf = Predicate('name', 'equals', 'a')
    group = leaf
    for _ in range(4): group = ConditionGroup('all', (group,))
    Rule(condition=group, actions=(Action('rename', {'pattern': 'a'}),))
    with pytest.raises(ValueError): ConditionGroup('all', (group,))
    with pytest.raises(ValueError): ConditionGroup('all', tuple(leaf for _ in range(101)))
    with pytest.raises(ValueError): Rule(condition=leaf, actions=())
    with pytest.raises(ValueError): Rule(condition=leaf, actions=tuple(Action('rename', {'pattern': 'a'}) for _ in range(21)))
    r = rule()
    with pytest.raises(ValueError): RuleSet((r, r))


@pytest.mark.parametrize('kind,options', [
    ('rename', {'pattern': '../bad'}), ('rename', {'pattern': '{stem.__class__}'}),
    ('rename', {'pattern': 'CON{ext}'}), ('subfolder', {'path': '../bad'}),
    ('subfolder', {'path': 'C:/bad'}), ('move', {'destination': 'relative'}),
    ('move', {'destination': '\\\\?\\C:\\out'}), ('copy', {'destination': '\\\\.\\C:\\out'}),
    ('copy', {'destination': '\\\\bad?server\\share\\out'}),
    ('image_convert', {'output_format': 'mp4'}), ('video_convert', {}),
    ('image_convert', {'output_format': 'png', 'mode': 'replace', 'destination': 'C:/out'}),
    ('image_convert', {'output_format': 'png', 'mode': 'replace', 'backup': 'C:/hack'}),
    ('image_convert', {'output_format': 'png', 'quality': True}),
])
def test_actions_reject_unsafe_paths_tokens_code_and_conversion(kind, options):
    with pytest.raises(ValueError): Action(kind, options)


def test_project_route_terminal_and_replacement_default(tmp_path):
    assert Action('image_convert', {'output_format': 'png', 'destination': str(tmp_path)}).options['mode'] == 'keep'
    with pytest.raises(ValueError): Rule(condition=Predicate('kind', 'equals', 'file'), actions=(
        Action('project_route', {'tag': 'LYX参考'}), Action('rename', {'pattern': 'a'})))


def test_malformed_existing_store_not_reset_or_overwritten(tmp_path):
    store = RuleStore(tmp_path)
    store.path.write_text('{"version":1,"version":1,"rules":[]}', encoding='utf-8')
    before = store.path.read_bytes()
    with pytest.raises(ValueError): store.load()
    with pytest.raises(ValueError): store.save(RuleSet())
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('definition', [
    {'field': [], 'operator': 'equals', 'value': 'x'},
    {'field': 'name', 'operator': [], 'value': 'x'},
    {'field': 'size_bytes', 'operator': 'ge', 'value': 10**1000},
    {'mode': [], 'children': [{'field': 'name', 'operator': 'equals', 'value': 'x'}]},
])
def test_malformed_field_types_are_validation_errors(definition):
    doc = RuleSet((rule(),)).to_document()
    doc['rules'][0]['condition'] = definition
    with pytest.raises(ValueError): RuleSet.from_document(doc)


def test_oversized_import_does_not_create_missing_state(tmp_path):
    store = RuleStore(tmp_path/'newstate')
    doc = RuleSet((rule(),)).to_document()
    doc['rules'][0]['name'] = 'x'*3_000_000
    with pytest.raises(ValueError): store.import_document(doc)
    assert not store.state_dir.exists()


def test_atomic_replace_failure_retains_rules_and_cleans_owned_temp(tmp_path, monkeypatch):
    import filehub.automation.models as models
    store = RuleStore(tmp_path)
    original = store.save(RuleSet((rule(),)))
    before = store.path.read_bytes()
    def fail(*args): raise OSError('injected replace failure')
    monkeypatch.setattr(models.os, 'replace', fail)
    with pytest.raises(OSError): store.save(RuleSet())
    assert store.path.read_bytes() == before
    assert store.load() == original
    assert not tuple(tmp_path.glob('.automation-rules-*'))


def test_store_reparse_state_and_lock_rejected(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from pathlib import Path
    import stat
    store = RuleStore(tmp_path/'state')
    store.save(RuleSet((rule(),)))
    lstat = Path.lstat
    def reparse(self, *args, **kwargs):
        if self.name == 'engine.lock': return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
        return lstat(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', reparse)
    with pytest.raises(ValueError): store.load()
    with pytest.raises(ValueError): store.save(RuleSet())


def test_deleting_rule_preserves_unrelated_run_records(tmp_path):
    store = RuleStore(tmp_path)
    original = rule()
    store.save(RuleSet((original,)))
    history = tmp_path/'automation-ledger.sqlite'
    history.write_bytes(b'historical records')
    store.save(store.load().delete(original.id))
    assert history.read_bytes() == b'historical records'


def test_rule_count_limit_fails_visibly_without_truncation():
    first = rule()
    rules = tuple(replace(first, id=f'r{index}') for index in range(1001))
    with pytest.raises(ValueError, match='1000'): RuleSet(rules)
