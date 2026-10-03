"""Explicit-profile inbox and cleanup, reusing observation and engine safety."""
from pathlib import Path
import os
import re
from .models import Operation, checked_path
from .trees import TreeFingerprint
from .rules import IMAGE_EXT, VIDEO_EXT


class LegacyScheduler:
    def __init__(self,service,observer):
        self.service=service; self.observer=observer; self.last_errors=()

    def tick(self,now,context,permissions,*,matched=frozenset(),authority_revision=''):
        from .scheduler import source_fingerprint, visible, TEMP_SUFFIXES, sanitized_name
        if not permissions: self.last_errors=(); return []
        if not permissions<=frozenset({'manual_archive','unmatched_inbox','cleanup'}): raise ValueError('未知兼容权限')
        service=self.service;engine=service.engine;errors=[];seen=set();results=[];stamp=now.timestamp()
        def observe(path,scope,seconds):
            key=os.path.normcase(str(path));seen.add(key)
            try:
                checked_path(path);fp=source_fingerprint(engine,path)
                return fp if self.observer._ready(path,fp,stamp,scope+':'+context.package_id+':'+authority_revision,seconds/86400) else None
            except (OSError,ValueError) as exc:
                errors.append(f'{path}：{exc}')
                with engine.journal.connection() as db: db.execute('UPDATE observations SET changed_at=? WHERE path=?',(stamp,key))
                return None
        if permissions & {'unmatched_inbox','cleanup'}:
            for root in service.config.watch_roots:
                try: paths=sorted(checked_path(root).iterdir())
                except (OSError,ValueError) as exc: errors.append(str(exc));continue
                for path in paths:
                    if str(path).casefold() in matched: continue
                    disposable=path.name.casefold() in {name.casefold() for name in context.disposable_filenames}
                    try:
                        if (not visible(path) and not disposable) or path.suffix.lower() in TEMP_SUFFIXES or path.name.startswith('~$'):continue
                        checked_path(path)
                        if disposable and 'cleanup' not in permissions: continue
                        if not disposable and 'unmatched_inbox' not in permissions: continue
                        fp=observe(path,'watch',context.arrival_delay_seconds)
                        if fp is None: continue
                        if disposable and not path.is_dir():
                            results.append(engine.execute([Operation('recycle',path,None,fp)],'后台稳定配置残留回收'));continue
                        if 'unmatched_inbox' not in permissions: continue
                        category='other' if isinstance(fp,TreeFingerprint) else 'image' if path.suffix.lower() in IMAGE_EXT else 'video' if path.suffix.lower() in VIDEO_EXT else 'other'
                        folder=checked_path(context.inbox_root/context.categories[category]/now.strftime('%y%m%d'))
                        name=sanitized_name(path);candidate=folder/name;number=1
                        while candidate.exists() or (folder.is_dir() and any(p.name.casefold()==candidate.name.casefold() for p in folder.iterdir())):
                            p=Path(name);candidate=folder/(name+f'-{number}' if isinstance(fp,TreeFingerprint) else p.stem+f'-{number}'+p.suffix);number+=1
                        results.append(engine.execute([Operation('move',path,candidate,fp)],'后台收件箱归档'))
                    except (OSError,ValueError) as exc: errors.append(f'{path}：{exc}')
        if 'cleanup' in permissions:
            results.extend(self._sanitize(context,errors))
            try:
                inbox=checked_path(context.inbox_root)
                if inbox.is_dir():
                    for name in context.categories.values():
                        category=checked_path(inbox/name)
                        if not category.is_dir() or not visible(category): continue
                        for day in sorted(category.iterdir()):
                            if not re.fullmatch(r'\d{6}',day.name) or not visible(day) or not checked_path(day).is_dir(): continue
                            fp=observe(day,'inbox',context.expiry_delay_seconds)
                            if fp is not None: results.append(engine.execute([Operation('recycle',day,None,fp)],'共享收件箱过期目录回收'))
            except (OSError,ValueError) as exc: errors.append(str(exc))
        with engine.journal.connection() as db:
            for row in db.execute('SELECT path FROM observations').fetchall():
                if row['path'] not in seen: db.execute('DELETE FROM observations WHERE path=?',(row['path'],))
        self.last_errors=tuple(errors); return results

    def _sanitize(self,context,errors):
        from .scheduler import source_fingerprint, visible, sanitized_name
        engine=self.service.engine;results=[];paths=[];seen=set()
        def collect(folder):
            for path in sorted(checked_path(folder).iterdir()):
                if not visible(path) or str(path).casefold() in seen: continue
                seen.add(str(path).casefold())
                checked_path(path)
                if path.is_dir():collect(path)
                paths.append(path)
        for root in context.sanitization_roots:
            try:
                if checked_path(root).is_dir():collect(root)
            except (OSError,ValueError) as exc: errors.append(str(exc))
        for path in paths:
            try:
                name=sanitized_name(path)
                if name==path.name:continue
                fp=source_fingerprint(engine,path)
                results.append(engine.execute([Operation('move',path,path.with_name(name),fp)],'全局不合规名称修正'))
            except (OSError,ValueError) as exc: errors.append(f'{path}：{exc}')
        return results
