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
    def __init__(self,service,*,automatic_completion=None):
        self.service=service;self.last_errors=();self.automatic_completion=automatic_completion
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
        s=self.service;e=s.engine;c=s.config;c.validate(e.state_dir)
        snapshot=s.catalog.load();rules=snapshot.compiled
        results=[];errors=[];matched=set()
        runtime=s.automation if any(r.enabled for r in rules.rules) else None
        conversions=s.conversions if any(r.enabled and any(a.kind=='image_convert' for a in r.actions) for r in rules.rules) else None
        with e.locked():
            if c.paused:
                with e.journal.connection() as db:db.execute('DELETE FROM observations')
                if runtime:runtime.ledger.reset_observations()
                self.last_errors=();return []
            # A concurrent management change cannot lend an old snapshot authority.
            if s.catalog.load().revision!=snapshot.revision:
                self.last_errors=('规则文件在后台评估前已变化',);return []
            if runtime:
                runtime.ledger.reconcile()
                for root in c.watch_roots:
                    try:paths=sorted(checked_path(root).iterdir())
                    except (OSError,ValueError) as exc:errors.append(str(exc));continue
                    for path in paths:
                        try:
                            if not visible(path) or path.suffix.lower() in TEMP_SUFFIXES or path.name.startswith('~$'):continue
                            checked_path(path)
                            from .automation.conditions import first_match
                            fp=source_fingerprint(e,path)
                            facts=runtime.facts(path,now=now,watch_root=root)
                            match=first_match(rules,facts,now,watch_root=root,configured_watch_roots=c.watch_roots)
                            if match.rule is None:continue
                            matched.add(str(path).casefold())
                            if runtime.ledger.suppression(path,fp,match.rule):continue
                            preview=runtime.preview([path],now=now,automatic=True,watch_root=root)
                            if not preview.plans:errors.extend(preview.errors);continue
                            plan=preview.plans[0];run=runtime.claim(preview,plan)
                            if run is None:continue
                            if any(step.kind=='image_convert' for step in plan.steps) and plan.ok:
                                try:conversions.submit_rule(preview,automatic=True,claims={0:run},completion=self.automatic_completion)
                                except (OSError,ValueError) as exc:runtime.ledger.update(run,'failed',str(exc));errors.append(str(exc))
                            else:results.extend(runtime.execute(preview,automatic=True,claims={0:run}))
                        except (OSError,ValueError) as exc:
                            matched.add(str(path).casefold())  # Failed evaluation never lends fallback permission.
                            errors.append(f'{path}：{exc}')
            if snapshot.compatibility_selection is not None and snapshot.compatibility_permissions & {'unmatched_inbox','cleanup'}:
                from .legacy_scheduler import LegacyScheduler
                legacy=LegacyScheduler(s,self)
                context=s.archive_context(permission=None,snapshot=snapshot)
                results.extend(legacy.tick(now,context,snapshot.compatibility_permissions,matched=frozenset(matched),authority_revision=snapshot.revision))
                errors.extend(legacy.last_errors)
        self.last_errors=tuple(errors);return results
