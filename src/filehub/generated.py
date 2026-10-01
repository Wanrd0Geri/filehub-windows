"""Image-only owned staging and conservative backed-up publication.

Encoding is deliberately outside the engine lock. Capabilities are process-issued,
bound to one engine instance and exact paths/options/result, and consumed once.
Recovery uses durable ownership records and exact fingerprints, never tickets or
hash-only guesses. All file mutations use the existing guarded platform API.
"""
from dataclasses import dataclass, replace
from pathlib import Path
import os
import threading
import uuid

from .models import Fingerprint, Operation, checked_path
from .platform.metadata import set_times


def path_key(path):
    return os.path.normcase(os.path.abspath(path))


@dataclass(frozen=True)
class OwnedStaging:
    path: Path
    source: Path
    target: Path
    source_fingerprint: Fingerprint
    output_fingerprint: Fingerprint
    spec: object
    result: object
    owner: object
    token: str


_tickets = {}
_ticket_lock = threading.Lock()


def _outside_state(engine, *paths):
    state = checked_path(engine.state_dir)
    for path in paths:
        checked_path(path)
        if engine.overlaps(Path(path_key(path)), Path(path_key(state))):
            raise ValueError('不能操作应用状态目录')


def generate_owned(engine, source, target, spec=None, cancel_event=None, progress=None, *,
                   expected_source=None, expected_capability_digest=None):
    """Return a single-use artifact belonging to this exact engine and plan.

    ``engine`` is mandatory so staging creation cannot bypass state protection
    or cross a demo/service replacement. Frozen backend generate is unchanged.
    """
    from .conversion import ConversionSpec, generate
    source, target = checked_path(source), checked_path(target)
    _outside_state(engine, source, target)
    if path_key(source) != path_key(target) and engine.overlaps(source, target):
        raise ValueError('源与目标路径重叠')
    if not source.is_file():
        raise ValueError('转换只支持普通文件')
    spec = spec or ConversionSpec()
    checked_path(target.parent)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name('.filehub-generated-' + uuid.uuid4().hex + '.tmp')
    _outside_state(engine, staging)
    result = generate(source, staging, spec, cancel_event, progress,
                      expected_source=expected_source,
                      expected_capability_digest=expected_capability_digest)
    ticket = OwnedStaging(staging, source, target, result.source_fingerprint,
                         result.output_fingerprint, spec, result, engine, uuid.uuid4().hex)
    with _ticket_lock:
        _tickets[ticket.token] = ticket
    return ticket


def discard_owned(engine, staging):
    """Consume and discard only the exact verified process-owned artifact."""
    with _ticket_lock:
        if not isinstance(staging, OwnedStaging) or _tickets.get(staging.token) is not staging or staging.owner is not engine:
            raise ValueError('临时输出不属于此引擎或已使用')
        del _tickets[staging.token]
    with engine.platform.guard(staging.path, destructive=True) as guard:
        guard.verify(staging.output_fingerprint)
        guard.remove()


def _consume(engine, source, target, expected_source, staging, expected_output):
    with _ticket_lock:
        if not isinstance(staging, OwnedStaging) or _tickets.get(staging.token) is not staging or staging.owner is not engine:
            raise ValueError('必须使用此引擎生成的未使用临时图片')
        if (path_key(staging.source) != path_key(source) or path_key(staging.target) != path_key(target)
                or staging.source_fingerprint != expected_source or staging.output_fingerprint != expected_output):
            raise ValueError('转换计划与临时图片绑定不匹配')
        del _tickets[staging.token]
    return staging.path


def _cancelled(event):
    return event is not None and event.is_set()


def _cancel(event):
    if _cancelled(event):
        raise ValueError('图片转换已取消；原件保留')


def _backup_path(engine, item):
    if len(item.operation_id) != 32 or any(c not in '0123456789abcdef' for c in item.operation_id):
        raise ValueError('备份操作身份无效')
    return checked_path(engine.state_dir / 'conversion-backups' / item.operation_id / item.source.name)


def _swap_path(item, *, undo=False):
    return checked_path(item.source.with_name('.filehub-convert-' + item.operation_id + ('-undo' if undo else '') + '.tmp'))


def _record(engine, item):
    record = engine.journal.generated(item.operation_id)
    if record.backup and path_key(record.backup) != path_key(_backup_path(engine, item)):
        raise ValueError('备份归属不明确，拒绝内部路径')
    if record.swap and path_key(record.swap) != path_key(_swap_path(item)):
        raise ValueError('交换文件归属不明确')
    if record.undo_swap and path_key(record.undo_swap) != path_key(_swap_path(item, undo=True)):
        raise ValueError('撤销交换文件归属不明确')
    if record.undo_stage and path_key(record.undo_stage) != path_key(item.source.with_name('.filehub-convert-' + item.operation_id + '-restore.tmp')):
        raise ValueError('撤销暂存归属不明确')
    return record


def _step(engine, item, phase, state, message='', **fields):
    engine.journal.generated_transition(item.operation_id, phase, state, message, **fields)


def _remove_owned(engine, path, fingerprint):
    with engine.platform.guard(path, destructive=True) as guard:
        guard.verify(fingerprint)
        guard.remove()


def _cleanup_stage(engine, item):
    if item.staging and item.staging.exists():
        _outside_state(engine, item.staging)
        # A journaled staging is only actionable at its allocated sibling name.
        if item.staging.parent != item.target.parent or not item.staging.name.startswith('.filehub-generated-'):
            raise ValueError('临时图片归属不明确')
        _remove_owned(engine, item.staging, item.target_fingerprint)


def publish_generated(engine, source, target, expected_source, staging, expected_output,
                      label, *, mode='keep', batch_id=None, cancel_event=None):
    source, target = Path(os.path.abspath(source)), Path(os.path.abspath(target))
    with engine.locked():
        operation = Operation('convert', source, target, expected_source)
        if batch_id is None:
            batch_id = engine.journal.create_batch(label, [operation])
            item = engine.journal.items(batch_id)[-1]
        else:
            operation_id = engine.journal.append_operations(batch_id, [operation])[0]
            item = next(i for i in engine.journal.items(batch_id) if i.operation_id == operation_id)
        owned = False
        try:
            if mode not in {'keep', 'replace'}:
                raise ValueError('转换模式必须为 keep 或 replace')
            _outside_state(engine, source, target)
            same = path_key(source) == path_key(target)
            if same and mode != 'replace':
                raise ValueError('保留原件模式不能使用原路径')
            if not same and engine.overlaps(source, target):
                raise ValueError('源与目标路径重叠')
            # Also protect originals already selected into this shared batch.
            for other in engine.journal.items(batch_id):
                if other.operation_id != item.operation_id and path_key(other.source) == path_key(target):
                    raise ValueError('目标与批次其他选中源重叠')
            if not same and target.exists():
                raise FileExistsError('目标已存在，不能覆盖')
            path = _consume(engine, source, target, expected_source, staging, expected_output)
            owned = True
            _outside_state(engine, path)
            if path.parent != target.parent or path_key(path) in {path_key(source), path_key(target)}:
                raise ValueError('生成暂存必须是独立目标兄弟文件')
            engine.journal.create_generated(item.operation_id, mode, path, expected_output)
            item = next(i for i in engine.journal.items(batch_id) if i.operation_id == item.operation_id)
            _cancel(cancel_event)
            with engine.platform.guard(source, destructive=mode == 'replace') as original, \
                    engine.platform.guard(path, destructive=True) as output:
                original.verify(expected_source)
                output.verify(expected_output)
                engine.platform.checkpoint('generated_validated', item)
                _cancel(cancel_event)
                if mode == 'replace':
                    backup = _backup_path(engine, item)
                    checked_path(backup.parent.parent).mkdir(parents=True, exist_ok=True)
                    backup.parent.mkdir(exist_ok=False)
                    _step(engine, item, 'backing_up', 'copying', '准备保存完整原件备份', backup=backup)
                    engine.platform.checkpoint('before_generated_backup', item)
                    _cancel(cancel_event)
                    with engine.platform.create_target(backup) as saved:
                        backup_fp = engine._copy(original, saved, item)
                        saved.verify(backup_fp)
                        if (backup_fp.creation_ns, backup_fp.mtime_ns) != (expected_source.creation_ns, expected_source.mtime_ns):
                            raise ValueError('备份时间校验失败')
                        original.verify(expected_source)
                        _step(engine, item, 'backed_up', 'copied', '完整原件备份已验证', backup_fp=backup_fp)
                    engine.platform.checkpoint('generated_backup_verified', item)
                    _cancel(cancel_event)
                # Final cancellation gate. Once durable critical intent is set,
                # finish or conservatively settle; no return with a vacant source.
                engine.platform.checkpoint('before_generated_critical', item)
                _cancel(cancel_event)
                original.verify(expected_source)
                output.verify(expected_output)
                if mode == 'replace' and same:
                    swap = _swap_path(item)
                    _step(engine, item, 'swapping', 'publishing', '准备交换绑定原件', swap=swap)
                    engine.platform.checkpoint('before_generated_swap', item)
                    original.rename(swap)
                    engine.platform.checkpoint('after_generated_swap', item)
                _step(engine, item, 'publishing', 'publishing', '准备独占发布已验证生成图片')
                engine.platform.checkpoint('before_generated_publish', item)
                output.verify(expected_output)
                output.rename(target)
                engine.platform.checkpoint('after_generated_rename_before_binding', item)
                published_fp = output.fingerprint()
                # NTFS name tunneling may inherit a recently removed name's
                # creation time. Accept that one OS rename effect only from the
                # continuously held owned handle, preserving every other field.
                bound_output = replace(expected_output, creation_ns=published_fp.creation_ns) if same else expected_output
                if published_fp != bound_output:
                    raise ValueError('发布后生成文件指纹变化')
                engine.journal.transition(item.operation_id, 'publishing', '已发布生成图片，身份已绑定', target_fp=published_fp)
                expected_output = published_fp
                item = next(i for i in engine.journal.items(batch_id) if i.operation_id == item.operation_id)
                engine.platform.checkpoint('after_generated_publish', item)
                output.close()
                with engine.platform.guard(target) as survivor:
                    survivor.verify(expected_output)
                    if mode == 'replace':
                        record = _record(engine, item)
                        with engine.platform.guard(record.backup) as saved:
                            saved.verify(record.backup_fingerprint)
                            original.verify(expected_source)
                            _step(engine, item, 'removing_original', 'removing_source', '输出和备份已验证，准备移除绑定原件')
                            engine.platform.checkpoint('before_generated_remove', item)
                            original.verify(expected_source)
                            survivor.verify(expected_output)
                            saved.verify(record.backup_fingerprint)
                            original.remove()
                            original.close()
                            engine.platform.checkpoint('after_generated_remove', item)
                    _step(engine, item, 'committed', 'committed',
                          '图片替换完成；原件备份：' + str(_record(engine, item).backup) if mode == 'replace' else '图片转换完成；原件保留')
                    if _cancelled(cancel_event):
                        engine.journal.transition(item.operation_id, 'committed', '取消在关键阶段到达；本项已安全完成，停止后续项')
        except Exception as exc:
            current = next(i for i in engine.journal.items(batch_id) if i.operation_id == item.operation_id)
            if owned:
                try:
                    recover_generated(engine, current, failure=exc)
                except Exception as recovery_error:
                    engine.journal.transition(item.operation_id, 'conflict', f'转换停止：{exc}；恢复未确定：{recovery_error}；保留备份/交换文件，请人工核对')
            else:
                engine.journal.transition(item.operation_id, 'failed', str(exc))
        return engine.journal.batch(batch_id)


def _restore_backup(engine, item, record):
    """Create a new original only into a vacant name; pin all survivors."""
    if item.source.exists():
        raise FileExistsError('原路径已占用；保留备份')
    restore_path = item.source.with_name('.filehub-convert-' + item.operation_id + '-restore.tmp')
    _step(engine, item, 'undo_copying', 'undo_copying', '准备完整恢复原件', undo_stage=restore_path)
    with engine.platform.guard(record.backup) as saved, engine.platform.create_target(restore_path) as restored:
        saved.verify(record.backup_fingerprint)
        restored_fp = engine._copy(saved, restored, item)
        engine.journal.transition(item.operation_id, 'undo_publishing', '恢复原件已验证，准备发布', undo_fp=restored_fp)
        _step(engine, item, 'undo_publishing', 'undo_publishing')
        engine.platform.checkpoint('before_generated_restore_publish', item)
        restored.verify(restored_fp)
        restored.rename(item.source)
        # The owned writable restore handle lets us undo NTFS name tunneling
        # without reopening or writing through an unbound user pathname.
        set_times(restored.handle, restored_fp.creation_ns, restored_fp.mtime_ns)
        restored.flush()
        restored.verify(restored_fp)
        engine.platform.checkpoint('after_generated_restore_publish', item)
        return restored_fp


def undo_generated(engine, item):
    record = _record(engine, item)
    _outside_state(engine, item.source, item.target)
    if record.mode == 'keep':
        with engine.platform.guard(item.source) as original, engine.platform.guard(item.target, destructive=True) as output:
            original.verify(item.expected_source)
            output.verify(item.target_fingerprint)
            _step(engine, item, 'undo_removing_output', 'undo_removing_copy', '原件与生成输出已验证，准备移除输出')
            engine.platform.checkpoint('before_generated_undo_remove', item)
            original.verify(item.expected_source)
            output.verify(item.target_fingerprint)
            output.remove()
            output.close()
            engine.platform.checkpoint('after_generated_undo_remove', item)
            _step(engine, item, 'undone', 'undone', '图片转换已撤销；原件保留')
        return
    same = path_key(item.source) == path_key(item.target)
    with engine.platform.guard(record.backup) as saved, engine.platform.guard(item.target, destructive=True) as output:
        saved.verify(record.backup_fingerprint)
        output.verify(item.target_fingerprint)
        if not saved.fingerprint().same_content(item.expected_source) or (record.backup_fingerprint.creation_ns, record.backup_fingerprint.mtime_ns) != (item.expected_source.creation_ns, item.expected_source.mtime_ns):
            raise ValueError('原件备份内容或时间不匹配')
        if not same and item.source.exists():
            raise FileExistsError('原位置已占用，不能覆盖')
        if same:
            undo_swap = _swap_path(item, undo=True)
            _step(engine, item, 'undo_swapping', 'undo_copying', '准备交换绑定生成输出', undo_swap=undo_swap)
            engine.platform.checkpoint('before_generated_undo_swap', item)
            output.verify(item.target_fingerprint)
            output.rename(undo_swap)
            engine.platform.checkpoint('after_generated_undo_swap', item)
        restored_fp = _restore_backup(engine, item, record)
        with engine.platform.guard(item.source) as original:
            original.verify(restored_fp)
            saved.verify(record.backup_fingerprint)
            output.verify(item.target_fingerprint)
            _step(engine, item, 'undo_removing_output', 'undo_removing_target', '原件恢复已验证，准备移除生成输出')
            engine.platform.checkpoint('before_generated_undo_remove', item)
            original.verify(restored_fp)
            output.verify(item.target_fingerprint)
            output.remove()
            output.close()
            engine.platform.checkpoint('after_generated_undo_remove', item)
            engine._complete_file_inverse(item, restored_fp)
            _step(engine, item, 'undone', 'undone', '原件已完整恢复；备份继续保留：' + str(record.backup))


def recover_generated(engine, item, *, failure=None):
    """Classify durable phases without retrying generation or uncertain removal."""
    record = _record(engine, item)
    _outside_state(engine, item.source, item.target)
    original = engine._matches(item.source, item.expected_source)
    output = engine._matches(item.target, item.target_fingerprint)
    backup = record.backup is not None and engine._matches(record.backup, record.backup_fingerprint)
    swap = record.swap is not None and engine._matches(record.swap, item.expected_source)
    same = path_key(item.source) == path_key(item.target)
    location = f'备份：{record.backup}；交换：{record.swap}；撤销交换：{record.undo_swap}；暂存：{item.staging}'
    if record.phase.startswith('undo_'):
        _recover_undo(engine, item, record, location)
        return
    if record.phase == 'committed':
        if failure is not None:
            _step(engine, item, 'committed', 'conflict', f'撤销停止：{failure}；所有副本保留；' + location)
        return
    if record.mode == 'keep':
        if original and output and record.phase == 'publishing' and (not item.staging or not item.staging.exists()):
            _step(engine, item, 'committed', 'committed', '已恢复完成的图片转换')
            return
        if original and not item.target.exists() and record.phase in {'prepared', 'publishing'}:
            _cleanup_stage(engine, item)
            _step(engine, item, 'aborted', 'failed', f'转换未发布；{failure or "操作中断"}')
            return
    elif backup:
        if failure is not None and output and (original and not same or swap and same):
            _rollback_failed_publication(engine, item, record, location, failure)
            return
        # Removal happened only after durable verifying+remove intent. The
        # source/swap must be absent, never an unexpected object at that name.
        if output and record.phase == 'removing_original' and ((same and not record.swap.exists()) or (not same and not item.source.exists())):
            _step(engine, item, 'committed', 'committed', '已恢复完成的图片替换；' + location)
            return
        if swap and not item.source.exists() and not item.target.exists():
            with engine.platform.guard(record.swap, destructive=True) as old, engine.platform.guard(record.backup) as saved:
                old.verify(item.expected_source)
                saved.verify(record.backup_fingerprint)
                old.rename(item.source)
            _cleanup_stage(engine, item)
            _step(engine, item, 'aborted', 'failed', '替换中断，绑定原件已还原；' + location)
            return
        if original and not item.target.exists() and not same:
            _cleanup_stage(engine, item)
            _step(engine, item, 'aborted', 'failed', f'替换未发布，原件保留；{failure or "操作中断"}；' + location)
            return
        if original and same and record.phase in {'prepared', 'backing_up', 'backed_up', 'swapping'} and not (record.swap and record.swap.exists()):
            _cleanup_stage(engine, item)
            _step(engine, item, 'aborted', 'failed', f'替换未发布，原件保留；{failure or "操作中断"}；' + location)
            return
    # Backup failure/cancel before critical phase leaves original untouched.
    if original and record.phase in {'prepared', 'backing_up'}:
        _cleanup_stage(engine, item)
        _step(engine, item, 'aborted', 'failed', f'转换未进入关键阶段；{failure or "操作中断"}；' + location)
        return
    _step(engine, item, record.phase, 'conflict', f'转换中断，文件全部保留；{failure or "结果未确定"}；' + location)


def _rollback_failed_publication(engine, item, record, location, failure):
    same = path_key(item.source) == path_key(item.target)
    old_path = record.swap if same else item.source
    with engine.platform.guard(old_path, destructive=same) as old, \
            engine.platform.guard(record.backup) as backup, \
            engine.platform.guard(item.target, destructive=True) as output:
        old.verify(item.expected_source)
        backup.verify(record.backup_fingerprint)
        output.verify(item.target_fingerprint)
        _step(engine, item, 'rollback_removing_output', 'removing_source', '失败后准备移除确属本操作的生成输出')
        engine.platform.checkpoint('before_generated_rollback_remove', item)
        old.verify(item.expected_source)
        backup.verify(record.backup_fingerprint)
        output.verify(item.target_fingerprint)
        output.remove()
        output.close()
        if same:
            _step(engine, item, 'rollback_restoring_original', 'publishing', '准备归还绑定原件')
            engine.platform.checkpoint('before_generated_rollback_restore', item)
            old.verify(item.expected_source)
            old.rename(item.source)
        _step(engine, item, 'aborted', 'failed', f'替换失败，原件已保留或归位；{failure}；' + location)


def _recover_undo(engine, item, record, location):
    same = path_key(item.source) == path_key(item.target)
    if record.mode == 'keep':
        if record.phase == 'undo_removing_output' and not item.target.exists() and engine._matches(item.source, item.expected_source):
            _step(engine, item, 'undone', 'undone', '生成输出已移除，撤销记录已恢复')
            return
    else:
        backup = engine._matches(record.backup, record.backup_fingerprint)
        restored = engine._matches(item.source, item.undo_fingerprint)
        output_path = record.undo_swap if same else item.target
        if backup and restored and record.phase == 'undo_removing_output' and not output_path.exists():
            with engine.platform.guard(item.source) as guard:
                guard.verify(item.undo_fingerprint)
                engine._complete_file_inverse(item, item.undo_fingerprint)
            _step(engine, item, 'undone', 'undone', '替换撤销记录已恢复；' + location)
            return
        # Undo failure before original restoration: restore the exact generated
        # subject from its swap into a vacant name, leaving backup/stage intact.
        if same and backup and not item.source.exists() and engine._matches(record.undo_swap, item.target_fingerprint):
            with engine.platform.guard(record.undo_swap, destructive=True) as generated:
                generated.verify(item.target_fingerprint)
                generated.rename(item.target)
            _step(engine, item, 'committed', 'conflict', '撤销中断，生成图片已归位；' + location)
            return
    _step(engine, item, record.phase, 'conflict', '撤销中断，所有副本保留，请核对；' + location)
