"""Acceptance entry must exercise real frozen APIs and fail the executable gate."""
import json
from pathlib import Path

from filehub.ui.app import self_test

OLD_CHECKS = {
    'default_unconfigured_paused', 'valid_png', 'png_archive', 'png_undo',
    'bundled_probe_width_64', 'paused_no_source_mutation',
    'video_1920_distinct_content', 'video_1920_archive_naming',
    'video_1920_distinct_sequence', 'video_1920_undo',
}
NEW_CHECKS = {
    'image_jpeg_png_webp_roundtrip', 'image_transparency_png_webp',
    'image_tiny42_webp_native_decode', 'image_jpeg_backgrounds',
    'image_keep_original_and_undo', 'image_cross_extension_replace_backup_undo',
    'image_same_path_replace_backup_undo', 'generic_rule_no_sync_before_legacy_gate',
    'ordered_copy_convert_move_history_undo', 'imported_rule_disabled_persisted',
    'template_route_persisted_undo',
    'image_collision_max_number_replace_backup_undo',
    'image_collision_preview_late_occupancy_rejected',
}


def test_existing_selftest_runs_real_020_acceptance_in_owned_fixture(tmp_path):
    report = self_test(tmp_path / 'acceptance')
    assert report['ok'], report
    assert OLD_CHECKS | NEW_CHECKS <= report['checks'].keys()
    assert all(report['checks'][name] for name in OLD_CHECKS | NEW_CHECKS)
    details = report['release020']
    assert details['qt_version'] == '6.11.2'
    assert set(details['capabilities']['inputs']) == {'jpeg', 'png', 'webp'}
    assert set(details['capabilities']['outputs']) == {'jpeg', 'png', 'webp'}
    assert details['tiny_webp']['bytes'] == 42
    assert details['tiny_webp']['native_alpha'] == 0
    assert details['rule_chain']['journal_kinds'] == ['copy', 'convert', 'move']
    assert details['rule_chain']['restored_original']
    assert details['template']['persisted'] and details['template']['undone']
    assert details['collision_numbering']['target'].endswith('numbered-020.jpg')
    assert details['collision_numbering']['backup_verified'] and details['collision_numbering']['undone']
    assert details['collision_numbering']['occupied_preserved'] and details['collision_numbering']['late_occupancy_rejected']
    fixture = Path(report['fixture_dir'])
    assert fixture.is_relative_to(tmp_path / 'acceptance')
    for row in details['images']:
        assert Path(row['source']).is_relative_to(fixture)
        assert Path(row['target']).is_relative_to(fixture)
    for row in details['replacements']:
        assert Path(row['backup']).is_relative_to(fixture)
        assert Path(row['backup']).read_bytes() == Path(row['source']).read_bytes()


def test_failed_020_hook_fails_existing_executable_entry_and_writes_json(tmp_path, monkeypatch):
    import filehub.selftest020 as smoke
    import filehub.ui.app as app

    def fail(*args):
        raise ValueError('injected 0.2 acceptance failure')

    monkeypatch.setattr(smoke, 'extend_report', fail)
    monkeypatch.setattr(app.sys, 'stdout', None)
    parent = tmp_path / 'failure'
    assert app.run(['--self-test', '--state-dir', str(parent)]) == 1
    report = json.loads((parent / 'self-test.json').read_text(encoding='utf-8'))
    assert not report['ok'] and 'injected 0.2 acceptance failure' in report['error']
    assert OLD_CHECKS <= report['checks'].keys()
    assert all(report['checks'][name] for name in OLD_CHECKS)
