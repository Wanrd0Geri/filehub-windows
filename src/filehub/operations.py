"""Conservative file transactions; every destructive step has durable intent.

Windows guards bind identity checks and destructive actions to one open handle.
Copies are exclusively created and held throughout verification/source removal.
Recovery only classifies known states; it never deletes an unconfirmed survivor.
"""
from pathlib import Path
from contextlib import ExitStack
import os
import uuid

from .journal import Journal
from .models import Fingerprint, Operation, checked_path
from .platform.windows import WindowsPlatform, process_lock
from .trees import TreeFingerprint, transfer_tree, undo_tree, prepare_move_inverse


class OperationEngine:
    def __init__(self, state_dir: Path, platform=None):
        self.state_dir = checked_path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.platform = platform if platform is not None else WindowsPlatform()
        self._lock = process_lock(self.state_dir)
        with self.locked():
            self.journal = Journal(self.state_dir / "journal.sqlite")

    def locked(self):
        """Reentrant across same-state instances, thread and process exclusive.

        Task 3 may allocate versions and call execute inside this context.
        """
        return self._lock.acquire()

    @staticmethod
    def overlaps(a, b):
        return a == b or a in b.parents or b in a.parents

    def _validate(self, operations):
        for op in operations:
            if op.kind not in {"move", "copy", "recycle"}:
                raise ValueError("未知操作类型")
            if (op.kind == "recycle") != (op.target is None):
                raise ValueError("目标路径与操作类型不匹配")
            checked_path(op.source)
            if self.overlaps(op.source, self.state_dir):
                raise ValueError("不能操作应用状态目录")
            if op.source.suffix.lower() in {".crdownload", ".download", ".part", ".partial", ".tmp"} or op.source.name.startswith("~$"):
                raise ValueError("下载临时文件或活动锁文件，已跳过")
            if op.source.is_dir() and not isinstance(op.expected_source,TreeFingerprint):
                raise ValueError("缺少目录树指纹；源保持不变")
            if op.expected_source is None:
                raise ValueError("缺少计划时的源指纹")
            if op.target:
                checked_path(op.target)
                if self.overlaps(op.target, self.state_dir):
                    raise ValueError("不能操作应用状态目录")
                if any(self.overlaps(op.target, other.source) for other in operations):
                    raise ValueError("源与目标路径重叠")
                if op.target.exists():
                    raise FileExistsError("目标已存在，不能覆盖")
        targets = [op.target for op in operations if op.target]
        if any(self.overlaps(a, b) for i, a in enumerate(targets) for b in targets[i + 1:]):
            raise ValueError("批次目标路径重复或重叠")

    def execute(self, operations, label: str, *, batch_id=None):
        operations = tuple(Operation(op.kind, Path(os.path.abspath(op.source)),
                                     Path(os.path.abspath(op.target)) if op.target else None,
                                     op.expected_source) for op in operations)
        with self.locked():
            # Validate kinds before SQL CHECK; all other preflight failures get a record.
            if any(op.kind not in {"move", "copy", "recycle"} for op in operations):
                raise ValueError("未知操作类型")
            if batch_id is None:
                batch_id = self.journal.create_batch(label, operations)
                new_items=self.journal.items(batch_id)
            else:
                ids=set(self.journal.append_operations(batch_id,operations))
                new_items=[i for i in self.journal.items(batch_id) if i.operation_id in ids]
            try:
                self._validate(operations)
            except (OSError, ValueError) as exc:
                for item in new_items:
                    self.journal.transition(item.operation_id, "failed", str(exc))
                return self.journal.batch(batch_id)
            for item in new_items:
                try:
                    if isinstance(item.expected_source,TreeFingerprint):
                        transfer_tree(self,item)
                    elif item.kind == "recycle":
                        self._recycle(item)
                    else:
                        self._transfer(item)
                except Exception as exc:
                    current = next(i for i in self.journal.items(batch_id) if i.operation_id == item.operation_id)
                    # Preserve durable progress. Partial copies and verified duplicates
                    # must never masquerade as committed operations.
                    ambiguous = current.state not in {"prepared", "failed"}
                    self.journal.transition(item.operation_id, "conflict" if ambiguous else "failed",
                                            f"操作停止：{exc}；请核对源/目标" if ambiguous else str(exc))
            return self.journal.batch(batch_id)

    def tree_child_items(self,item):
        with self.journal.connection() as db:
            ids={r[0] for r in db.execute('SELECT child FROM tree_children WHERE parent=?',(item.operation_id,))}
        return [i for i in self.journal.items(item.batch_id) if i.operation_id in ids]

    def execute_existing_child(self,operation_id,batch_id):
        item=next(i for i in self.journal.items(batch_id) if i.operation_id==operation_id)
        try:
            self._validate([Operation(item.kind,item.source,item.target,item.expected_source)])
            if item.kind=='recycle':self._recycle(item)
            else:self._transfer(item)
        except Exception as exc:
            self.journal.transition(item.operation_id,'conflict',f'目录条目保留：{exc}')

    def _copy(self, source_guard, target_guard, item):
        source_guard.stream.seek(0)
        while block := source_guard.stream.read(1024 * 1024):
            target_guard.stream.write(block)
            self.platform.checkpoint("copy_chunk", item)
        target_guard.flush()
        target_guard.copy_metadata_from(source_guard, lambda stage: self.platform.checkpoint(stage, item))
        source_fp = source_guard.fingerprint()
        target_fp = target_guard.fingerprint()
        if not source_fp.same_content(target_fp):
            raise ValueError("复制校验失败")
        return target_fp

    def _transfer(self, item):
        with self.platform.guard(item.source, destructive=item.kind == "move") as src:
            src.verify(item.expected_source)
            checked_path(item.target)
            item.target.parent.mkdir(parents=True, exist_ok=True)
            self.platform.checkpoint("before_target_create", item)
            staging = item.target.with_name(".filehub-" + uuid.uuid4().hex + ".tmp")
            self.journal.transition(item.operation_id, "copying", "暂存复制中；最终路径尚未发布", staging=staging)
            with self.platform.create_target(staging) as dst:
                self.platform.checkpoint("copy_started", item)
                target_fp = self._copy(src, dst, item)
                src.verify(item.expected_source)
                self.journal.transition(item.operation_id, "publishing", "暂存已验证，准备原子发布", target_fp=target_fp)
                self.platform.checkpoint("after_stage_verified", item)
                self.platform.checkpoint("before_publish", item)
                dst.verify(target_fp)
                dst.rename(item.target)
                self.platform.checkpoint("after_publish", item)
                # A DELETE handle requires DELETE-sharing ADS readers; those
                # cannot block stream unlink. Reacquire a strong non-DELETE
                # survivor guard before deleting anything from the source.
                dst.close()
                self.platform.checkpoint("before_survivor_guard", item)
                with self.platform.guard(item.target) as survivor:
                    survivor.verify(target_fp)
                    self.journal.transition(item.operation_id, "copied", "复制已验证；移动的源尚未移除", target_fp=target_fp)
                    self.platform.checkpoint("copy_verified", item)
                    if item.kind == "move":
                        src.verify(item.expected_source)
                        survivor.verify(target_fp)
                        self.journal.transition(item.operation_id, "removing_source", "准备移除已匹配源")
                        self.platform.checkpoint("before_source_remove", item)
                        src.verify(item.expected_source)
                        survivor.verify(target_fp)
                        src.remove()
                        # Close ALL source stream handles while its strong
                        # survivor is protected; main-handle close alone delays
                        # deletion when named-stream handles remain open.
                        src.close()
                    self.platform.checkpoint("source_removed" if item.kind == "move" else "copy_complete", item)
                    self.journal.transition(item.operation_id, "committed", "移动完成" if item.kind == "move" else "复制完成")

    def _restore_staged(self, item, staging):
        with self.platform.guard(staging, destructive=True) as guard:
            guard.verify(item.expected_source)
            guard.rename(item.source)

    def _recycle(self, item):
        staging = item.source.with_name(item.source.stem + ".filehub-" + uuid.uuid4().hex[:8] + item.source.suffix)
        self.journal.transition(item.operation_id, "staging_recycle", "回收前保留唯一名称", staging=staging)
        with self.platform.guard(item.source, destructive=True) as src:
            src.verify(item.expected_source)
            self.platform.checkpoint("before_recycle_stage", item)
            src.verify(item.expected_source)
            src.rename(staging)
        self.journal.transition(item.operation_id, "recycling", "准备送入回收站；中断时结果可能未知")
        self.platform.checkpoint("recycle_staged", item)
        try:
            result = self.platform.recycle(staging)
        except Exception as exc:
            if staging.exists():
                try:
                    self._restore_staged(item, staging)
                except Exception as restore_exc:
                    self.journal.transition(item.operation_id, "conflict", f"回收失败，暂存保留：{staging}；{restore_exc}")
                else:
                    self.journal.transition(item.operation_id, "failed", f"回收失败，源已还原：{exc}")
            else:
                self.journal.transition(item.operation_id, "recycle_unknown", f"回收结果未知：{exc}；请检查回收站名称 {staging.name}")
            return
        if result.status == "recycled" and not staging.exists():
            self.journal.transition(item.operation_id, "recycled", result.message + f"；回收名称：{staging.name}", recycle_identity=result.identity)
        elif staging.exists():
            try:
                self._restore_staged(item, staging)
            except Exception as exc:
                self.journal.transition(item.operation_id, "conflict", f"回收未完成，暂存保留：{staging}；{exc}")
            else:
                self.journal.transition(item.operation_id, "failed", "回收未完成，源已还原；" + result.message)
        else:
            self.journal.transition(item.operation_id, "recycle_unknown", "回收结果未知；请检查回收站：" + staging.name)

    def undo(self, batch_id: str):
        with self.locked(),ExitStack() as pinned:
            blocked=set()
            for root in self.journal.items(batch_id):
                with self.journal.connection() as db:
                    already_blocked=db.execute('SELECT 1 FROM tree_undo_blocks WHERE operation=?',(root.operation_id,)).fetchone()
                    owned_inverse=db.execute('SELECT 1 FROM tree_inverse_roots WHERE operation=?',(root.operation_id,)).fetchone()
                if already_blocked:
                    blocked.add(root.operation_id);blocked.update(c.operation_id for c in self.tree_child_items(root));continue
                if isinstance(root.expected_source,TreeFingerprint) and root.kind=='recycle' and root.state in {'recycled','manual_restore','recycle_unknown'}:
                    blocked.update(c.operation_id for c in self.tree_child_items(root))
                if isinstance(root.expected_source,TreeFingerprint) and (root.state=='committed' or owned_inverse and root.state=='conflict'):
                    try:
                        if root.kind=='move':prepare_move_inverse(self,root,pinned)
                        elif not self._matches(root.target,root.target_fingerprint):raise ValueError('目标目录树已变化')
                    except (OSError,ValueError) as exc:
                        blocked.add(root.operation_id)
                        blocked.update(c.operation_id for c in self.tree_child_items(root))
                        with self.journal.connection() as db:db.execute('INSERT OR REPLACE INTO tree_undo_blocks VALUES(?,?)',(root.operation_id,str(exc)))
                        self.journal.transition(root.operation_id,'conflict',f'{exc}；拒绝全部子项撤销')
            for item in reversed(self.journal.items(batch_id)):
                if item.operation_id in blocked:continue
                if item.state == "undone":
                    continue
                if item.state == "recycled":
                    # Native recycle supplies no trustworthy item identity. Do not
                    # claim generic send-to-trash is programmatically undoable.
                    if isinstance(item.expected_source,TreeFingerprint):
                        message=f'请从回收站手动还原整个目录 {item.staging.name} 到 {item.source}；包含原空目录结构；自动撤销不可用'
                    else:message=f"请从回收站手动还原 {item.staging.name} 到 {item.source}；自动撤销不可用"
                    self.journal.transition(item.operation_id, "manual_restore",message)
                    continue
                with self.journal.connection() as db:
                    owned_inverse=db.execute('SELECT 1 FROM tree_inverse_roots WHERE operation=?',(item.operation_id,)).fetchone()
                if item.state != "committed" and not (owned_inverse and item.state=='conflict'):
                    continue
                try:
                    if isinstance(item.expected_source,TreeFingerprint):
                        undo_tree(self,item)
                        continue
                    with self.platform.guard(item.target, destructive=True) as target:
                        target.verify(item.target_fingerprint)
                        if item.kind == "copy":
                            with self.platform.guard(item.source) as survivor:
                                # A prior move undo recreates a new file identity;
                                # content, not its original inode, establishes survival.
                                if not survivor.fingerprint().same_content(item.expected_source):
                                    raise ValueError("原内容没有另一份已验证副本；保留此副本")
                                self.journal.transition(item.operation_id, "undo_removing_copy", "另一份原内容已验证，准备移除副本")
                                self.platform.checkpoint("before_undo_remove", item)
                                target.verify(item.target_fingerprint)
                                if not survivor.fingerprint().same_content(item.expected_source):
                                    raise ValueError("保留副本：另一份内容变化")
                                target.remove()
                                target.close()
                                self.platform.checkpoint("undo_target_removed", item)
                                self.journal.transition(item.operation_id, "undone", "撤销完成")
                        else:
                            checked_path(item.source)
                            if item.source.exists():
                                raise FileExistsError("原位置已占用，不能覆盖")
                            item.source.parent.mkdir(parents=True, exist_ok=True)
                            staging = item.source.with_name(".filehub-undo-" + uuid.uuid4().hex + ".tmp")
                            self.journal.transition(item.operation_id, "undo_copying", "准备暂存恢复副本", staging=staging)
                            with self.platform.create_target(staging) as restored:
                                undo_fp = self._copy(target, restored, item)
                                target.verify(item.target_fingerprint)
                                self.journal.transition(item.operation_id, "undo_publishing", "暂存恢复副本已验证，准备原子发布", undo_fp=undo_fp)
                                self.platform.checkpoint("undo_after_stage_verified", item)
                                self.platform.checkpoint("undo_before_publish", item)
                                restored.verify(undo_fp)
                                restored.rename(item.source)
                                self.platform.checkpoint("undo_after_publish", item)
                                restored.close()
                                self.platform.checkpoint("before_undo_survivor_guard", item)
                                with self.platform.guard(item.source) as survivor:
                                    survivor.verify(undo_fp)
                                    self.journal.transition(item.operation_id, "undo_copied", "原位置已校验，目标尚未移除", undo_fp=undo_fp)
                                    self.platform.checkpoint("undo_copy_verified", item)
                                    survivor.verify(undo_fp)
                                    target.verify(item.target_fingerprint)
                                    self.journal.transition(item.operation_id, "undo_removing_target", "准备移除匹配目标")
                                    target.remove()
                                    target.close()
                                    self.platform.checkpoint("undo_target_removed", item)
                                    self.journal.transition(item.operation_id, "undone", "撤销完成")
                except Exception as exc:
                    self.journal.transition(item.operation_id, "conflict", f"撤销停止：{exc}；文件保持现状，请人工核对")
            return self.journal.batch(batch_id)

    def _matches(self, path, expected):
        if path is None or expected is None:
            return False
        try:
            if isinstance(expected,TreeFingerprint):return Fingerprint.capture(path)==expected
            with self.platform.guard(path) as guard:
                guard.verify(expected)
            return True
        except (OSError, ValueError):
            return False

    def recover(self) -> list:
        recovered = []
        stable = {"committed", "undone", "recycled", "manual_restore", "failed", "conflict", "recycle_unknown"}
        with self.locked():
            for batch in self.journal.history():
                for item in batch.items:
                    if item.state in stable:
                        continue
                    state, message = "conflict", "操作中断；文件保持现状，请人工核对源、目标或暂存文件"
                    if item.state == "prepared":
                        state, message = "failed", "操作未开始；源保持现状"
                    elif item.state in {"copied", "publishing"} and item.kind == "copy" and (
                        item.state == "copied" or item.staging is not None and not item.staging.exists()
                    ) and self._matches(item.target, item.target_fingerprint):
                        state, message = "committed", "已恢复完成的复制记录"
                    elif item.state == "removing_source" and not item.source.exists() and self._matches(item.target, item.target_fingerprint):
                        state, message = "committed", "已恢复完成的移动记录"
                    elif item.state == "undo_removing_copy" and not item.target.exists():
                        state, message = "undone", "副本已移除；撤销记录已恢复"
                    elif item.state == "undo_removing_target" and not item.target.exists() and self._matches(item.source, item.undo_fingerprint):
                        state, message = "undone", "移动撤销记录已恢复"
                    elif item.state in {"staging_recycle", "recycling"}:
                        if item.staging and item.staging.exists():
                            try:
                                self._restore_staged(item, item.staging)
                            except Exception as exc:
                                message += f"；暂存路径 {item.staging}：{exc}"
                            else:
                                state, message = "failed", "回收中断，暂存已还原到源；未继续删除"
                        elif self._matches(item.source, item.expected_source):
                            state, message = "failed", "回收未开始；源仍在"
                        else:
                            state, message = "recycle_unknown", f"回收结果未知，请检查回收站名称 {item.staging.name} 和原路径 {item.source}"
                    self.journal.transition(item.operation_id, state, message)
                    recovered.append(next(i for i in self.journal.items(item.batch_id) if i.operation_id == item.operation_id))
        return recovered

    def history(self) -> list:
        with self.locked():
            return self.journal.history()
