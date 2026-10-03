import json
import pytest
from filehub.rulefiles.catalog import RuleCatalogStore

def package(name='Example'):
    return json.dumps(dict(format='filehub.rules', version=1, id='example', name=name,
        bindings={'input': {'label': 'Input'}}, variables={}, rules=[dict(id='one', name='One',
        scope=[{'binding': 'input', 'relative': ''}], condition={'field': 'extension', 'operator': 'glob', 'value': '.jpg'},
        actions=[{'kind': 'rename', 'options': {'pattern': '{stem}'}}])])).encode()

def test_import_replace_and_binding(tmp_path):
    store=RuleCatalogStore(tmp_path/'state'); empty=store.load()
    first=store.import_package(package(), None, expected_revision=empty.revision)
    assert not first.enabled['example']
    with pytest.raises(ValueError): store.import_package(package(), None, expected_revision=first.revision)
    with pytest.raises(ValueError): store.set_enabled('example','one',True,expected_revision=first.revision)
    bound=store.bind('example', {'input':tmp_path/'input'},expected_revision=first.revision)
    active=store.set_enabled('example','one',True,expected_revision=bound.revision)
    changed=store.replace_package('example',package('Renamed'),None,expected_revision=active.revision)
    assert not changed.enabled['example']
    assert changed.compiled.rules[0].revision==active.compiled.rules[0].revision
    assert changed.revision!=active.revision
    assert changed.bindings==active.bindings
    assert store.export_package('example')==package_canonical(package('Renamed'))

def package_canonical(data):
    from filehub.rulefiles.protocol import encode_package,parse_package
    return encode_package(parse_package(data))

@pytest.mark.parametrize('stage',['before_backup','after_backup','after_temp_write','before_swap','after_swap'])
def test_fault_complete_snapshots(tmp_path,stage):
    store=RuleCatalogStore(tmp_path/'state')
    old=store.import_package(package(),expected_revision=store.load().revision)
    prior=store.path.read_bytes()
    def fail(point):
        if point==stage: raise OSError('injected')
    store._fault=fail
    with pytest.raises(OSError): store.replace_package('example',package('New'),expected_revision=old.revision)
    store._fault=lambda stage:None
    loaded=store.load()
    assert loaded.packages['example'].name==('New' if stage=='after_swap' else 'Example')
    if stage!='before_backup': assert any(p.read_bytes()==prior for p in store.backup_dir.glob('*.json'))
    assert not list(store.state_dir.glob('*.tmp'))

def test_partial_temp_and_backup_failures(tmp_path):
    store=RuleCatalogStore(tmp_path/'state'); old=store.import_package(package(),expected_revision=store.load().revision)
    prior=store.path.read_bytes(); flush=store._flush
    def partial(path,data,exclusive=True):
        if path.suffix=='.tmp':
            path.write_bytes(data[:12]); raise OSError('partial')
        flush(path,data,exclusive)
    store._flush=partial
    with pytest.raises(OSError): store.replace_package('example',package('New'),expected_revision=old.revision)
    assert store.path.read_bytes()==prior
    assert any(p.read_bytes()==prior for p in store.backup_dir.glob('*.json'))
    def failure(*args,**kwargs): raise OSError('backup denied')
    store._flush=failure
    with pytest.raises(OSError): store.replace_package('example',package('New'),expected_revision=old.revision)
    assert store.path.read_bytes()==prior

@pytest.mark.parametrize('corrupt',[False,True])
def test_explicit_recovery_disabled_and_cas(tmp_path,corrupt):
    store=RuleCatalogStore(tmp_path/'state'); first=store.import_package(package(),expected_revision=store.load().revision)
    bound=store.bind('example',{'input':tmp_path/'input'},expected_revision=first.revision)
    active=store.set_enabled('example','one',True,expected_revision=bound.revision)
    replaced=store.replace_package('example',package('New'),expected_revision=active.revision)
    backup=next(b for b in store.list_backups() if b.revision==active.revision)
    if corrupt: store.path.write_bytes(b'{broken')
    else: store.path.unlink()
    with pytest.raises(ValueError): store.load()
    token=store.recovery_revision()
    store.path.write_bytes(b'{different')
    with pytest.raises(ValueError): store.restore(backup.id,expected_revision=token)
    restored=store.restore(backup.id,expected_revision=store.recovery_revision())
    assert restored.enabled['example']==frozenset()
    assert restored.revision!=active.revision
    assert restored.compiled.rules[0].revision==active.compiled.rules[0].revision
    assert all(p.read_bytes()!=b'{different' for p in store.backup_dir.glob('*.json'))
    with pytest.raises(ValueError): store.restore('../escape',expected_revision=restored.revision)

def test_strict_local_and_orphans(tmp_path):
    store=RuleCatalogStore(tmp_path/'state'); first=store.import_package(package(),expected_revision=store.load().revision)
    (store.state_dir/'.rule-catalog-orphan.tmp').write_bytes(b'broken')
    assert store.load().revision==first.revision
    doc=json.loads(store.path.read_bytes());doc['surprise']=True;store.path.write_text(json.dumps(doc))
    with pytest.raises(ValueError): store.load()

def test_order_delta_ids_and_history(tmp_path):
    from filehub.rulefiles.catalog import compare_packages
    from filehub.rulefiles.protocol import parse_package
    store=RuleCatalogStore(tmp_path/'state'); first=store.import_package(package(),expected_revision=store.load().revision)
    other=json.loads(package());other['id']='other'
    second=store.import_package(json.dumps(other).encode(),expected_revision=first.revision)
    ordered=store.reorder(('other','example'),expected_revision=second.revision)
    assert ordered.order==('other','example') and ordered.revision!=second.revision
    with pytest.raises(ValueError): store.remove('example',expected_revision=second.revision)
    ledger=store.state_dir/'ledger.fixture';ledger.write_bytes(b'history')
    removed=store.remove('example',expected_revision=ordered.revision)
    assert ledger.read_bytes()==b'history'
    assert 'example' not in removed.packages
    delta=compare_packages(parse_package(package()),parse_package(package('Renamed')))
    assert delta.added==delta.changed==delta.removed==delta.binding_changes==()

def test_replacement_changed_and_new_ids(tmp_path):
    from filehub.rulefiles.catalog import compare_packages
    from filehub.rulefiles.protocol import parse_package
    store=RuleCatalogStore(tmp_path/'state');old=store.import_package(package(),expected_revision=store.load().revision)
    doc=json.loads(package());doc['rules'][0]['name']='Changed';new_rule=dict(doc['rules'][0],id='two');doc['rules'].append(new_rule)
    incoming=json.dumps(doc).encode();delta=compare_packages(parse_package(package()),parse_package(incoming))
    assert delta.added==('two',) and delta.changed==('one',)
    new=store.replace_package('example',incoming,expected_revision=old.revision)
    assert new.runtime_ids['example']['one']==old.runtime_ids['example']['one']
    assert not new.enabled['example']

def test_local_duplicate_unknown_and_permission_fail_closed(tmp_path):
    store=RuleCatalogStore(tmp_path/'state');initial=store.import_package(package(),expected_revision=store.load().revision)
    prior=store.path.read_bytes()
    for mutate in [lambda d:d['packages'][0].update(enabled=['missing']),lambda d:d.update(compatibility_permissions=['cleanup']),
                   lambda d:d['packages'][0].update(runtime_ids={'one':'bad id'}),lambda d:d['packages'][0].update(bindings={'unknown':str(tmp_path)})]:
        doc=json.loads(prior);mutate(doc);store.path.write_text(json.dumps(doc))
        with pytest.raises(ValueError): store.load()
    store.path.write_bytes(prior)
    with pytest.raises(ValueError): store.set_compatibility('example',frozenset(),expected_revision=initial.revision)
    assert store.path.read_bytes()==prior

def test_malformed_enable_type_is_value_error(tmp_path):
    store=RuleCatalogStore(tmp_path/'state');first=store.import_package(package(),expected_revision=store.load().revision)
    doc=json.loads(store.path.read_bytes());doc['packages'][0]['enabled']=[{}]
    store.path.write_text(json.dumps(doc))
    with pytest.raises(ValueError): store.load()

def test_import_invalid_never_creates_state(tmp_path):
    store=RuleCatalogStore(tmp_path/'state')
    with pytest.raises(ValueError): store.import_package(b'{broken',expected_revision=store.load().revision)
    assert not store.state_dir.exists()

def test_identical_replace_invalidates_and_export_omits_locals(tmp_path):
    store=RuleCatalogStore(tmp_path/'state');first=store.import_package(package(),str(tmp_path/'source.json'),expected_revision=store.load().revision)
    bound=store.bind('example',{'input':tmp_path/'input'},expected_revision=first.revision)
    enabled=store.set_enabled('example','one',True,expected_revision=bound.revision)
    again=store.replace_package('example',package(),expected_revision=enabled.revision)
    assert again.revision!=enabled.revision
    assert again.compiled.rules[0].revision==enabled.compiled.rules[0].revision
    output=store.export_package('example')
    assert str(tmp_path).encode() not in output
    assert not {'enabled','runtime_ids','source','generation','compatibility_permissions'} & json.loads(output).keys()

def test_unused_missing_binding_does_not_block_enable(tmp_path):
    doc=json.loads(package());doc['rules'][0]['scope']=[]
    store=RuleCatalogStore(tmp_path/'state');first=store.import_package(json.dumps(doc).encode(),expected_revision=store.load().revision)
    active=store.set_enabled('example','one',True,expected_revision=first.revision)
    assert active.enabled['example']==frozenset({'one'})
    assert not (tmp_path/'input').exists()

def test_delta_variable_behavior_change():
    from filehub.rulefiles.catalog import compare_packages
    from filehub.rulefiles.protocol import parse_package
    old=json.loads(package());old['variables']={'folder':'PNG'}
    old['rules'][0]['actions']=[{'kind':'subfolder','options':{'path':'${folder}'}}]
    new=json.loads(json.dumps(old));new['variables']['folder']='JPEG'
    delta=compare_packages(parse_package(json.dumps(old).encode()),parse_package(json.dumps(new).encode()))
    assert delta.changed==('one',) and delta.variables_changed
    assert not delta.compatibility_changed

def test_rule_order_only_delta_and_semantics(tmp_path):
    from filehub.rulefiles.catalog import compare_packages
    from filehub.rulefiles.protocol import parse_package
    doc=json.loads(package());doc['rules'][0]['scope']=[]
    doc['rules'].append(dict(doc['rules'][0],id='two',name='Two'))
    original=json.dumps(doc).encode()
    doc['rules'].reverse();incoming=json.dumps(doc).encode()
    delta=compare_packages(parse_package(original),parse_package(incoming))
    assert delta.order_changed and not delta.changed
    assert not delta.metadata_changed and not delta.variables_changed and not delta.compatibility_changed
    store=RuleCatalogStore(tmp_path/'state')
    first=store.import_package(original,expected_revision=store.load().revision)
    changed=store.replace_package('example',incoming,expected_revision=first.revision)
    assert [r.id for r in changed.compiled.rules]==[r.id for r in reversed(first.compiled.rules)]
    assert {r.id:r.revision for r in changed.compiled.rules}=={r.id:r.revision for r in first.compiled.rules}
    assert changed.revision!=first.revision and not changed.enabled['example']
