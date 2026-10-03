from filehub.selftest030 import extend_report


def test_external_acceptance_uses_real_catalogue_and_owned_files(tmp_path):
    report = {'checks': {}}
    extend_report(tmp_path, report)
    assert len(report['checks']) == 7
    assert all(report['checks'].values())
    assert report['release030']['imported_disabled']
    assert report['release030']['restored_bytes'] == 'external acceptance'
    assert report['release030']['invalid_replace_preserved_bytes']


def test_failed_030_hook_fails_entry(tmp_path, monkeypatch):
    import filehub.selftest030 as smoke
    import filehub.ui.app as app
    monkeypatch.setattr(smoke, 'extend_report', lambda *a: (_ for _ in ()).throw(ValueError('injected 030 failure')))
    assert app.run(['--self-test', '--state-dir', str(tmp_path)]) == 1
    import json
    report = json.loads((tmp_path / 'self-test.json').read_text(encoding='utf-8'))
    assert not report['ok'] and 'injected 030 failure' in report['error']


def test_frozen_help_validates_static_examples_without_installing_them(tmp_path,monkeypatch):
    import json
    import shutil
    import sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    inventory=json.loads((root/'packaging/runtime-inventory.json').read_text(encoding='utf-8'))
    payload=tmp_path/'payload'
    for item in inventory['help']:
        target=payload/item['destination'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/item['source'],target)
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'_MEIPASS',str(payload),raising=False)
    report={'checks':{}}
    extend_report(tmp_path,report)
    assert len(report['release030']['help_files'])==7
    state=Path(report['release030']['work_dir'])/'state/rule-catalog.json'
    assert [entry['package']['id'] for entry in json.loads(state.read_text(encoding='utf-8'))['packages']]==['acceptance030']
