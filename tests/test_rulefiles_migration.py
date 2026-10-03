from dataclasses import replace
import json
import pytest
from filehub.config import Config, ConfigStore
from filehub.automation.models import Rule, RuleSet, RuleStore, Predicate, Action
from filehub.rulefiles.catalog import RuleCatalogStore


def test_read_only_migration_and_original_identity(tmp_path):
    from filehub.rulefiles.migration import inspect_legacy
    state = tmp_path/'state'; original = Rule(id='legacy', name='Old', enabled=True,
        scope=(str(tmp_path/'in'),), condition=Predicate('name','glob','*'), actions=(Action('copy',{'destination':str(tmp_path/'out')}),))
    RuleStore(state).save(RuleSet((original,)))
    raw = (state/'automation-rules.json').read_bytes()
    candidate = inspect_legacy(state, Config())
    assert candidate and (state/'automation-rules.json').read_bytes() == raw
    store = RuleCatalogStore(state); snap = store.adopt_legacy(candidate, expected_revision=store.load().revision)
    assert snap.compiled.rules[0].id == original.id
    assert snap.compiled.rules[0].revision == original.revision
    assert not snap.compiled.rules[0].enabled
    assert (state/'automation-rules.json').read_bytes() == raw
    assert inspect_legacy(state, Config()) is None
    backup = next((state/'legacy-migration-backups').iterdir())
    assert (backup/'automation-rules.json').read_bytes() == raw
    assert store.list_backups() == ()


def test_migration_digest_race_and_invalid_sources(tmp_path):
    from filehub.rulefiles.migration import inspect_legacy
    state = tmp_path/'state'; ConfigStore(state).save(Config(sync_root=tmp_path/'sync'))
    candidate = inspect_legacy(state, ConfigStore(state).load())
    (state/'config.json').write_bytes(b'{}')
    store = RuleCatalogStore(state)
    with pytest.raises(ValueError, match='changed'): store.adopt_legacy(candidate, expected_revision=store.load().revision)
    assert not store.path.exists()
    (state/'automation-rules.json').write_bytes(b'broken')
    with pytest.raises(ValueError, match='automation-rules.json'): inspect_legacy(state, Config())


def test_default_config_is_not_legacy(tmp_path):
    from filehub.rulefiles.migration import inspect_legacy
    state = tmp_path/'state'; ConfigStore(state).save(Config())
    assert inspect_legacy(state, Config()) is None


def test_complete_templates_and_dormant_assignments_are_preserved(tmp_path):
    from filehub.rulefiles.migration import inspect_legacy
    from filehub.templates import TemplateStore,TemplateLibrary
    state=tmp_path/'state';root=tmp_path/'sync'
    (root/'1_work/项目/260101_XYZ_project').mkdir(parents=True)
    library=TemplateLibrary().copy_template('default','custom','Custom').assign('ABSENT','custom')
    ConfigStore(state).save(Config(sync_root=root));TemplateStore(state).save(library)
    candidate=inspect_legacy(state,ConfigStore(state).load());profile=candidate.packages[0].compatibility
    assert profile.assignments['ABSENT']=='custom'
    assert 'ABSENT' not in profile.projects
    assert {t.id for t in profile.templates}=={'default','custom'}
    store=RuleCatalogStore(state);snapshot=store.adopt_legacy(candidate,expected_revision=store.load().revision)
    assert snapshot.compatibility_selection is None and not snapshot.compatibility_permissions


@pytest.mark.parametrize('stage',['after_legacy_backup','before_swap'])
def test_interrupted_adoption_raw_backup_never_becomes_restore_candidate(tmp_path,monkeypatch,stage):
    from filehub.rulefiles.migration import inspect_legacy
    state=tmp_path/'state';ConfigStore(state).save(Config(sync_root=tmp_path/'root'))
    original=(state/'config.json').read_bytes();candidate=inspect_legacy(state,ConfigStore(state).load())
    store=RuleCatalogStore(state)
    monkeypatch.setattr(store,'_fault',lambda phase: (_ for _ in ()).throw(OSError('owned injected failure')) if phase==stage else None)
    with pytest.raises(OSError):store.adopt_legacy(candidate,expected_revision=store.load().revision)
    assert not store.path.exists() and store.list_backups()==()
    assert (state/'config.json').read_bytes()==original
    raw=next((state/'legacy-migration-backups').iterdir())
    assert (raw/'config.json').read_bytes()==original
    assert store.load().compiled.rules==()
    assert inspect_legacy(state,ConfigStore(state).load()) is not None


def test_missing_optional_legacy_files_valid_alias_and_strict_invalid_config(tmp_path):
    from filehub.rulefiles.migration import inspect_legacy
    state=tmp_path/'state';state.mkdir()
    config={'sync_root':str(tmp_path/'root'),'watch':[str(tmp_path/'watch')],'ffprobe':'custom.exe'}
    (state/'config.json').write_text(json.dumps(config),encoding='utf-8')
    candidate=inspect_legacy(state,ConfigStore(state).load())
    assert candidate and candidate.source_digests['templates.json'] is None
    assert candidate.source_digests['automation-rules.json'] is None
    config['unknown']=1;(state/'config.json').write_text(json.dumps(config),encoding='utf-8')
    with pytest.raises(ValueError,match='config.json'):inspect_legacy(state,Config())


def test_legacy_unsupported_ordinary_token_is_precise_and_read_only(tmp_path):
    from filehub.rulefiles.migration import inspect_legacy
    state=tmp_path/'state';rule=Rule(id='needs-token-review',condition=Predicate('name','glob','*'),
        actions=(Action('rename',{'pattern':'{prefix}_{stem}{ext}'}),))
    RuleStore(state).save(RuleSet((rule,)));raw=(state/'automation-rules.json').read_bytes()
    with pytest.raises(ValueError,match=r'needs-token-review.*rename.pattern.*prefix'):
        inspect_legacy(state,Config())
    assert (state/'automation-rules.json').read_bytes()==raw
    assert not (state/'rule-catalog.json').exists()


def test_project_route_migration_keeps_semantic_revision_and_requires_selection(tmp_path):
    from filehub.rulefiles.migration import inspect_legacy
    from filehub.service import FileHubService
    state=tmp_path/'state';root=tmp_path/'sync'
    (root/'1_work/项目/260101_XYZ_project').mkdir(parents=True)
    ConfigStore(state).save(Config(sync_root=root))
    rule=Rule(id='legacy-route',condition=Predicate('name','glob','*'),actions=(Action('project_route',{'tag':'XYZ参考'}),),enabled=True)
    RuleStore(state).save(RuleSet((rule,)))
    candidate=inspect_legacy(state,ConfigStore(state).load());store=RuleCatalogStore(state)
    snapshot=store.adopt_legacy(candidate,expected_revision=store.load().revision)
    assert snapshot.compiled.rules[0].revision==rule.revision and not snapshot.compiled.rules[0].enabled
    source=tmp_path/'a.txt';source.write_bytes(b'a');service=FileHubService(Config(),state)
    assert service.automation.preview([source],rule.id).errors
    store.set_compatibility('legacy-import',frozenset({'manual_archive'}),expected_revision=snapshot.revision)
    preview=service.automation.preview([source],rule.id)
    assert not preview.errors and preview.plans[0].ok
