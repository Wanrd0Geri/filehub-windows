"""Conservative observed-arrival clock. UI owns a 600-second awake-app timer.

Global jobs are explicit shared ownership: inbox expiry AND invalid-name cleanup
(including projects). Enable on one computer only. Normal names are untouched.
"""
from datetime import datetime
from pathlib import Path
import os
import re
import stat
import json
from .models import Fingerprint, Operation, checked_path
from .trees import TreeFingerprint
from .rules import IMAGE_EXT, VIDEO_EXT, safe_name

TICK_INTERVAL_SECONDS=600
TEMP_SUFFIXES={'.crdownload','.download','.part','.partial','.tmp'}


def visible(path):
    info=path.lstat()
    return not path.name.startswith('.') and '.filehub-' not in path.name and not getattr(info,'st_file_attributes',0)&(0x2|0x400) and not stat.S_ISLNK(info.st_mode)


def source_fingerprint(engine,path):
    fp=Fingerprint.capture(path)
    if isinstance(fp,TreeFingerprint):
        for name,expected in fp.entries:
            if Path(name).suffix.lower() in TEMP_SUFFIXES or Path(name).name.startswith('~$'):raise ValueError('目录仍含下载或 Office 活动文件')
            with engine.platform.guard(path/name) as guard:guard.verify(expected)
    else:
        with engine.platform.guard(path) as guard:guard.verify(fp)
    return fp


def sanitized_name(path):
    return safe_name(path.name+'.d')[:-2] if path.is_dir() else safe_name(path.name)


class Scheduler:
    def __init__(self,service):
        self.service=service;self.last_errors=()
        with service.engine.locked(),service.engine.journal.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS observations(path TEXT PRIMARY KEY,scope TEXT NOT NULL,identity TEXT NOT NULL,fingerprint TEXT NOT NULL,first_seen REAL NOT NULL,changed_at REAL NOT NULL)')

    def _ready(self,path,fp,now,scope,days):
        key=os.path.normcase(str(path));identity=json.dumps([fp.device,fp.file_id]);encoded=self.service.engine.journal.encode(fp)
        with self.service.engine.journal.connection() as db:
            row=db.execute('SELECT * FROM observations WHERE path=?',(key,)).fetchone()
            if not row or row['identity']!=identity or row['scope']!=scope:
                first=changed=now
            else:
                first=row['first_seen'];changed=now if row['fingerprint']!=encoded else row['changed_at']
            db.execute('INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?,?)',(key,scope,identity,encoded,first,changed))
        latest=max(first,changed,fp.creation_ns/1e9,fp.mtime_ns/1e9)
        if isinstance(fp,TreeFingerprint):
            latest=max([latest]+[max(f.creation_ns,f.mtime_ns)/1e9 for _,f in fp.entries]+[max(d.creation_ns,d.mtime_ns)/1e9 for d in fp.directories])
        return now-latest>=days*86400

    def tick(self,now):
        if not isinstance(now,datetime) or now.tzinfo is None:raise ValueError('tick 时间必须是带时区的 datetime')
        stamp=now.timestamp();s=self.service;e=s.engine;c=s.config;c.validate(e.state_dir)
        results=[];seen=set();errors=[]
        def observe(path,scope,days):
            key=os.path.normcase(str(path));seen.add(key)
            try:
                checked_path(path);fp=source_fingerprint(e,path)
                return fp if self._ready(path,fp,stamp,scope,days) else None
            except (OSError,ValueError) as exc:
                errors.append(f'{path}：{exc}')
                with e.journal.connection() as db:db.execute('UPDATE observations SET changed_at=? WHERE path=?',(stamp,key))
                return None
        with e.locked():
            if c.paused:
                with e.journal.connection() as db:db.execute('DELETE FROM observations')
                self.last_errors=();return []
            if c.sync_root is None:self.last_errors=('请先选择同步根目录',);return []
            checked_path(c.sync_root)
            for root in c.watch_roots:
                try:paths=sorted(checked_path(root).iterdir())
                except (OSError,ValueError) as exc:errors.append(str(exc));continue
                for path in paths:
                    try:
                        junk=path.name=='.baiduyun.uploading.cfg'
                        if (not visible(path) and not junk) or path.suffix.lower() in TEMP_SUFFIXES or path.name.startswith('~$'):continue
                        checked_path(path)
                    except (OSError,ValueError) as exc:
                        errors.append(f'{path}：{exc}');continue
                    fp=observe(path,'watch',c.sweep_days)
                    if fp is None:continue
                    if path.name.endswith('.baiduyun.uploading.cfg') and not path.is_dir():
                        results.append(e.execute([Operation('recycle',path,None,fp)],'后台稳定配置残留回收'));continue
                    category='其他' if isinstance(fp,TreeFingerprint) else '图片' if path.suffix.lower() in IMAGE_EXT else '视频' if path.suffix.lower() in VIDEO_EXT else '其他'
                    dest=checked_path(c.sync_root/'0_收件箱'/category/now.strftime('%y%m%d'))
                    try:name=sanitized_name(path)
                    except ValueError as exc:errors.append(str(exc));continue
                    candidate=dest/name;n=1
                    while candidate.exists():
                        p=Path(name);candidate=dest/(name+f'-{n}' if isinstance(fp,TreeFingerprint) else p.stem+f'-{n}'+p.suffix);n+=1
                    results.append(e.execute([Operation('move',path,candidate,fp)],'后台收件箱归档'))
            if c.global_jobs:
                results.extend(self._sanitize(errors))
                inbox=checked_path(c.sync_root/'0_收件箱')
                if inbox.is_dir():
                    for category in sorted(inbox.iterdir()):
                        try:
                            if not visible(category) or not checked_path(category).is_dir():continue
                            for day in sorted(category.iterdir()):
                                if not re.fullmatch(r'\d{6}',day.name) or not visible(day) or not checked_path(day).is_dir():continue
                                fp=observe(day,'inbox',c.inbox_days)
                                if fp is not None:results.append(e.execute([Operation('recycle',day,None,fp)],'共享收件箱过期目录回收'))
                        except (OSError,ValueError) as exc:errors.append(str(exc))
            with e.journal.connection() as db:
                for row in db.execute('SELECT path FROM observations').fetchall():
                    if row['path'] not in seen:db.execute('DELETE FROM observations WHERE path=?',(row['path'],))
        self.last_errors=tuple(errors);return results

    def _sanitize(self,errors):
        e=self.service.engine;results=[];root=self.service.config.sync_root
        # Bottom-up child names before parent names; one journal batch per rename
        # makes reverse history undo explicit and preserves prior path lineage.
        paths=[]
        def collect(folder):
            for p in sorted(checked_path(folder).iterdir()):
                if not visible(p):continue
                if p.is_dir():collect(p)
                paths.append(p)
        try:collect(root)
        except (OSError,ValueError) as exc:errors.append(str(exc))
        for path in paths:
            try:
                name=sanitized_name(path)
                if name==path.name:continue
                fp=source_fingerprint(e,path)
                results.append(e.execute([Operation('move',path,path.with_name(name),fp)],'全局不合规名称修正'))
            except (OSError,ValueError) as exc:errors.append(f'{path}：{exc}')
        return results
