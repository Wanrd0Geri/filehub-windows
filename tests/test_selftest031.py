from filehub.ui.app import self_test


def test_selftest_includes_true_runtime_manual_restore_and_undo(tmp_path):
    report=self_test(tmp_path)
    assert report['ok'],report['error']
    assert all(report['checks'][key] for key in (
        'manual_legacy_send_tag_entry','manual_restore_confirmation_only',
        'manual_restore_preserves_history','manual_real_archive_durable_ack','manual_archive_undo'))
    assert report['release031']['restored_files']==2
