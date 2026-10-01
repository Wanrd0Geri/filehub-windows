"""Captured trees, never recursive deletion. File transfers use the original engine."""
from dataclasses import dataclass, asdict, replace
from contextlib import ExitStack
from pathlib import Path
import hashlib
import json
import os
import uuid
import re
from .models import Fingerprint, checked_path, Operation
from .platform.metadata import stream_names, set_times

@dataclass(frozen=True)
class DirectoryIdentity:
    name: str
    device: int
    file_id: int
    creation_ns: int
    mtime_ns: int

@dataclass(frozen=True)
class TreeFingerprint(Fingerprint):
    entries: tuple = ()  # relative path, Fingerprint
    directories: tuple[DirectoryIdentity,...] = ()

    @classmethod
    def capture(cls,path):
        path=checked_path(path);before=path.stat();entries=[];directories=[]
        def fail(error):raise error
        for folder,dirs,files in os.walk(path,followlinks=False,onerror=fail):
            p=checked_path(Path(folder));info=p.stat()
            if stream_names(p):raise ValueError('目录含命名流，拒绝可能丢失元数据的复制')
            directories.append(DirectoryIdentity(str(p.relative_to(path)),info.st_dev,info.st_ino,info.st_birthtime_ns,info.st_mtime_ns))
            for name in sorted(dirs):checked_path(p/name)
            for name in sorted(files):
                f=checked_path(p/name);entries.append((str(f.relative_to(path)),Fingerprint.capture(f)))
        entries.sort(key=lambda e:e[0]);directories.sort(key=lambda d:d.name)
        after=path.stat()
        if (before.st_dev,before.st_ino,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_mtime_ns):raise ValueError('目录正在变化')
        payload=json.dumps([(n,fp.to_dict()) for n,fp in entries],sort_keys=True)
        return cls(after.st_dev,after.st_ino,sum(f.size for _,f in entries),after.st_mtime_ns,hashlib.sha256(payload.encode()).hexdigest(),after.st_birthtime_ns,(),tuple(entries),tuple(directories))

    def to_dict(self):
        d=asdict(self);d['entries']=[[name,fp.to_dict()] for name,fp in self.entries];return d

    @classmethod
    def from_dict(cls,value):
        d=dict(value);d['streams']=();d['entries']=tuple((n,Fingerprint.from_dict(f)) for n,f in d['entries'])
        d['directories']=tuple(DirectoryIdentity(**i) for i in d['directories']);return cls(**d)

    def same_content(self,other):
        return isinstance(other,TreeFingerprint) and [(n,fp.size,fp.sha256,fp.streams) for n,fp in self.entries]==[(n,fp.size,fp.sha256,fp.streams) for n,fp in other.entries] and [d.name for d in self.directories]==[d.name for d in other.directories]


def directory_matches(path,d):
    path=checked_path(path);st=path.stat()
    if not path.is_dir() or (st.st_dev,st.st_ino)!=(d.device,d.file_id):raise ValueError('目录身份变化')


def inbox_ancestors(source,sync_root):
    if sync_root is None:return []
    inbox=checked_path(sync_root/'0_收件箱')
    source=checked_path(source)
    if not source.is_relative_to(inbox):return []
    parts=source.relative_to(inbox).parts
    if len(parts)<3 or not re.fullmatch(r'\d{6}',parts[1]):return []
    day=inbox/parts[0]/parts[1];result=[];path=source.parent
    while path==day or path.is_relative_to(day):
        info=checked_path(path).stat()
        result.append((path,DirectoryIdentity('.',info.st_dev,info.st_ino,info.st_birthtime_ns,info.st_mtime_ns)))
        if path==day:break
        path=path.parent
    return result


def prune_inbox_ancestors(ancestors,platform):
    for path,identity in ancestors:
        try:
            directory_matches(path,identity)
            with platform.directory_guard(path,destructive=True) as guard:
                directory_matches(path,identity);guard.remove()
        except (OSError,ValueError):break


def prune(root,directories,platform):
    errors=[]
    for d in sorted(directories,key=lambda d:len(Path(d.name).parts),reverse=True):
        p=root/d.name
        if not p.exists():continue
        try:
            directory_matches(p,d)
            with platform.directory_guard(p,destructive=True) as g:
                directory_matches(p,d)
                # Windows disposition itself refuses nonempty directories.
                g.remove()
        except (OSError,ValueError) as exc:errors.append(str(exc))
    return errors


def captured_predecessor(tree,relative,expected):
    """Only an output actually captured by the ancestor can gain inverse IDs."""
    entries=dict(tree.entries)
    if not isinstance(expected,TreeFingerprint):return entries.get(relative)==expected
    prefix=Path(relative);dirs={d.name:d for d in tree.directories}
    root=dirs.get(str(prefix))
    if root is None or (root.device,root.file_id,root.creation_ns,root.mtime_ns)!=(expected.device,expected.file_id,expected.creation_ns,expected.mtime_ns):return False
    originals={str(Path(n).relative_to(prefix)):fp for n,fp in tree.entries if Path(n).is_relative_to(prefix)}
    if originals!=dict(expected.entries):return False
    original_dirs={str(Path(n).relative_to(prefix)):d for n,d in dirs.items() if Path(n).is_relative_to(prefix)}
    if set(original_dirs)!={d.name for d in expected.directories}:return False
    for d in expected.directories:
        old=original_dirs[d.name]
        if (d.device,d.file_id,d.creation_ns,d.mtime_ns)!=(old.device,old.file_id,old.creation_ns,old.mtime_ns):return False
    return True


def prepare_move_inverse(engine,item,pinned):
    """Own/pin the original root before any child inverse; never merge users' roots."""
    children=engine.tree_child_items(item)
    with engine.journal.connection() as db:
        row=db.execute('SELECT directories FROM tree_inverse_roots WHERE operation=?',(item.operation_id,)).fetchone()
    undone=[c for c in children if c.state=='undone']
    if row is None:
        if item.source.exists():raise ValueError('原目录位置已占用；拒绝合并恢复')
        if not engine._matches(item.target,item.target_fingerprint):raise ValueError('目标目录树已变化')
        # Intent precedes creation; a crash before owned identities are recorded
        # leaves an unproven empty root and is handled conservatively.
        with engine.journal.connection() as db:db.execute('INSERT INTO tree_inverse_roots VALUES(?,?)',(item.operation_id,'[]'))
        checked_path(item.source);item.source.mkdir(parents=True,exist_ok=False)
        pinned.enter_context(engine.platform.directory_guard(item.source))
        for d in sorted(item.expected_source.directories,key=lambda d:len(Path(d.name).parts)):
            if d.name=='.':continue
            p=checked_path(item.source/d.name);p.mkdir(exist_ok=False)
            pinned.enter_context(engine.platform.directory_guard(p))
        fp=Fingerprint.capture(item.source)
        with engine.journal.connection() as db:
            db.execute('UPDATE tree_inverse_roots SET directories=? WHERE operation=?',(json.dumps([asdict(d) for d in fp.directories]),item.operation_id))
        return
    owned=tuple(DirectoryIdentity(**d) for d in json.loads(row['directories']))
    if not owned:raise ValueError('逆向原目录身份尚未确认；需要人工核对')
    actual=Fingerprint.capture(item.source)
    if {d.name:(d.device,d.file_id) for d in actual.directories}!={d.name:(d.device,d.file_id) for d in owned}:raise ValueError('逆向原目录被替换或增加目录')
    if dict(actual.entries)!={str(c.source.relative_to(item.source)):c.undo_fingerprint for c in undone}:raise ValueError('逆向原目录含外部新增、修改或替换条目')
    for d in owned:
        directory_matches(item.source/d.name,d);pinned.enter_context(engine.platform.directory_guard(item.source/d.name))
    if any(c.state not in {'committed','undone'} for c in children):raise ValueError('子项逆向状态有冲突，需要人工核对')
    remaining={str(c.target.relative_to(item.target)):c.target_fingerprint for c in children if c.state=='committed'}
    if item.target.exists():
        target=Fingerprint.capture(item.target)
        if dict(target.entries)!=remaining:raise ValueError('剩余目标条目变化')
        if {d.name:(d.device,d.file_id) for d in target.directories}!={d.name:(d.device,d.file_id) for d in item.target_fingerprint.directories}:raise ValueError('剩余目标目录被替换或增加目录')
    elif remaining:raise ValueError('剩余目标目录丢失')


def transfer_tree(engine,item):
    fp=item.expected_source
    if not isinstance(fp,TreeFingerprint):raise ValueError('缺少目录树指纹')
    if Fingerprint.capture(item.source)!=fp:raise ValueError('目录在预览后已变化')
    original=item
    recycling=item.kind=='recycle'
    if recycling:
        prefix=item.source.name
        if item.source.parent.parent.name=='0_收件箱':prefix='收件箱_'+item.source.parent.name+'_'+item.source.name
        staging=item.source.with_name(prefix+'.filehub-'+uuid.uuid4().hex[:8])
        engine.journal.transition(item.operation_id,'copying','捕获清单暂存；尚未回收',staging=staging)
        item=replace(item,kind='move',target=staging)
    else:engine.journal.transition(item.operation_id,'copying','按捕获清单处理目录；新增或变化条目保留')
    target_dirs=[]
    with ExitStack() as stack:
        for d in fp.directories:
            directory_matches(item.source/d.name,d)
            stack.enter_context(engine.platform.directory_guard(item.source/d.name))
        if item.target:
            checked_path(item.target);item.target.mkdir(parents=True,exist_ok=False)
            for d in fp.directories:
                p=item.target/d.name;p.mkdir(parents=True,exist_ok=True)
                stack.enter_context(engine.platform.directory_guard(p))
                target_dirs.append((p,d))
        for name,expected in fp.entries:
            engine.platform.checkpoint('tree_before_entry',item)
            for d in fp.directories:directory_matches(item.source/d.name,d)
            source=checked_path(item.source/name)
            child=Operation(item.kind,source,item.target/name if item.target else None,expected)
            ids=engine.journal.append_operations(item.batch_id,[child])
            with engine.journal.connection() as db:db.execute('INSERT INTO tree_children VALUES(?,?)',(item.operation_id,ids[0]))
            engine.execute_existing_child(ids[0],item.batch_id)
        for p,d in reversed(target_dirs):
            with engine.platform.directory_guard(p) as guard:set_times(guard.handle,d.creation_ns,d.mtime_ns)
    children=engine.tree_child_items(item)
    errors=[]
    if item.kind in {'move','recycle'}:errors=prune(item.source,fp.directories,engine.platform)
    if recycling:
        result=Fingerprint.capture(item.target)
        if errors or not all(c.ok for c in children) or not fp.same_content(result):
            engine.journal.transition(item.operation_id,'conflict','目录部分完成；原位置变化条目及暂存目录均保留',target_fp=result)
            return
        engine.journal.transition(item.operation_id,'recycling','已验证整个暂存树；准备一次回收',target_fp=result)
        engine.platform.checkpoint('tree_before_recycle',original)
        if Fingerprint.capture(item.target)!=result:raise ValueError('回收暂存树变化，保留')
        outcome=engine.platform.recycle(item.target)
        if outcome.status=='recycled' and not item.target.exists():
            engine.journal.transition(item.operation_id,'recycled',f'整个目录已回收；名称：{item.target.name}',recycle_identity=outcome.identity)
        else:
            state='conflict' if item.target.exists() else 'recycle_unknown'
            engine.journal.transition(item.operation_id,state,f'回收未确认；核对暂存目录或回收站名称 {item.target}；{outcome.message}')
    elif item.target:
        result=Fingerprint.capture(item.target)
        if not fp.same_content(result):errors.append('目标树含外部新增或变化条目')
        engine.journal.transition(item.operation_id,'committed' if not errors and all(c.ok for c in children) else 'conflict',
            '目录完成' if not errors and all(c.ok for c in children) else '目录部分完成；新增、变化或失败条目保留',target_fp=result)
    else:
        engine.journal.transition(item.operation_id,'recycled' if not errors and all(c.ok for c in children) else 'conflict','目录按捕获条目回收；逐项记录名称，需手动还原')


def undo_tree(engine,item):
    children=engine.tree_child_items(item)
    if not all(c.state=='undone' for c in children):raise ValueError('目录子项撤销未完成')
    if item.kind=='move':
        for d in item.expected_source.directories:
            p=checked_path(item.source/d.name);p.mkdir(parents=True,exist_ok=True)
        for d in reversed(item.expected_source.directories):
            with engine.platform.directory_guard(item.source/d.name) as g:set_times(g.handle,d.creation_ns,d.mtime_ns)
    errors=prune(item.target,item.target_fingerprint.directories,engine.platform)
    if errors:raise ValueError('目录仍有未捕获内容；保留')
    if item.kind=='move':
        # A verified directory restoration creates new Windows file identities.
        # Rebind earlier still-committed targets only when their full content and
        # both preserved times match this controlled restoration. No user edit
        # or external replacement is accepted as restoration lineage.
        restored_fp=Fingerprint.capture(item.source)
        # Bind every restored file to the precise new identity produced by its
        # own inverse operation, not merely equal bytes/times at this path.
        inverse={str(c.source):c.undo_fingerprint for c in children}
        for name,current in restored_fp.entries:
            if inverse.get(str(item.source/name))!=current:raise ValueError('恢复后条目被外部替换，停止指纹关联')
        engine.journal.transition(item.operation_id,'undo_copied','恢复树已捕获；准备记录逆向身份关联',undo_fp=restored_fp)
        with engine.journal.connection() as db:
            ordinals={r['id']:r['ordinal'] for r in db.execute('SELECT id,ordinal FROM operations WHERE batch_id=?',(item.batch_id,))}
        for batch in engine.journal.history():
            for prior in batch.items:
                if batch.batch_id==item.batch_id and ordinals[prior.operation_id]>=ordinals[item.operation_id]:continue
                if prior.state!='committed' or not prior.target or not prior.target.is_relative_to(item.source):continue
                expected=prior.target_fingerprint
                if expected is None:continue
                try:
                    relative=str(prior.target.relative_to(item.source))
                    if not captured_predecessor(item.expected_source,relative,expected):continue
                    restored=restored_fp if relative=='.' else dict(restored_fp.entries).get(relative)
                    if isinstance(expected,TreeFingerprint) and restored is None:
                        restored=Fingerprint.capture(prior.target)
                        known_dirs={d.name:d for d in restored_fp.directories}
                        for d in restored.directories:
                            known=known_dirs.get(str(Path(relative)/d.name))
                            if known is None or (d.device,d.file_id)!=(known.device,known.file_id):raise ValueError('子目录不是此恢复产生的目录')
                        for name,entry in restored.entries:
                            if inverse.get(str(prior.target/name))!=entry:raise ValueError('子目录内容不是此恢复产生的文件')
                    if restored is None:continue
                    with ExitStack() as stack:
                        if isinstance(restored,TreeFingerprint):
                            for d in restored.directories:stack.enter_context(engine.platform.directory_guard(prior.target/d.name))
                            for name,entry in restored.entries:
                                guard=stack.enter_context(engine.platform.guard(prior.target/name));guard.verify(entry)
                            if Fingerprint.capture(prior.target)!=restored:raise ValueError('恢复目录变化')
                        else:
                            guard=stack.enter_context(engine.platform.guard(prior.target));guard.verify(restored)
                        if restored.same_content(expected) and (restored.creation_ns,restored.mtime_ns)==(expected.creation_ns,expected.mtime_ns):
                            with engine.journal.connection() as db:
                                db.execute('INSERT INTO tree_lineage VALUES(?,?,?,?)',(prior.operation_id,item.operation_id,engine.journal.encode(expected),engine.journal.encode(restored)))
                                db.execute('UPDATE operations SET target_fp=? WHERE id=?',(engine.journal.encode(restored),prior.operation_id))
                except (OSError,ValueError):pass
    engine.journal.transition(item.operation_id,'undone','目录撤销完成')
