"""Durable observations, claims and exact identity ancestry; never replay jobs."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
import uuid
from dataclasses import asdict

from ..models import Fingerprint, checked_path
from .planner import path_key

# Only live jobs in this process are excluded from interrupted-job recovery.
ACTIVE_RUNS = set()
ACTIVE_STATES = {}


class AutomationLedger:
    def __init__(self, engine):
        self.engine=engine;self.path=engine.state_dir/'automation.sqlite'
        with engine.locked(), self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS observations(path TEXT PRIMARY KEY,scope TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,first_seen REAL NOT NULL,stable_since REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,claim_key TEXT UNIQUE NOT NULL,
                    original TEXT NOT NULL,fingerprint TEXT NOT NULL,rule_id TEXT NOT NULL,
                    revision TEXT NOT NULL,ruleset_revision TEXT NOT NULL,template_revision TEXT NOT NULL,
                    name TEXT NOT NULL,batch_id TEXT NOT NULL,status TEXT NOT NULL,
                    intended TEXT NOT NULL,visited TEXT NOT NULL,progress TEXT NOT NULL DEFAULT '[]',
                    message TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS provenance(path TEXT NOT NULL,fingerprint TEXT NOT NULL,
                    visited TEXT NOT NULL,PRIMARY KEY(path,fingerprint));
                CREATE TABLE IF NOT EXISTS blocked(path TEXT NOT NULL,run_id TEXT NOT NULL,
                    PRIMARY KEY(path,run_id));
            ''')

    @contextmanager
    def connection(self):
        checked_path(self.path);checked_path(self.engine.state_dir)
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:yield db
        finally:db.close()

    def encode(self,fp):return self.engine.journal.encode(fp)

    def observe(self,path,fp,now,scope):
        key=path_key(path);encoded=self.encode(fp)
        with self.engine.locked(),self.connection() as db:
            row=db.execute('SELECT * FROM observations WHERE path=?',(key,)).fetchone()
            same=row and row['scope']==path_key(scope)
            old=self.engine.journal.decode(row['fingerprint']) if same else None
            identity=same and (old.device,old.file_id)==(fp.device,fp.file_id)
            first=row['first_seen'] if identity else now.timestamp()
            stable=row['stable_since'] if identity and old==fp else now.timestamp()
            db.execute('INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?)',(key,path_key(scope),encoded,first,stable))
        return datetime.fromtimestamp(first,timezone.utc),datetime.fromtimestamp(stable,timezone.utc)

    def observed(self,path,fp):
        with self.engine.locked(),self.connection() as db:
            row=db.execute('SELECT * FROM observations WHERE path=?',(path_key(path),)).fetchone()
        if not row or row['fingerprint']!=self.encode(fp):return None,None
        return tuple(datetime.fromtimestamp(row[k],timezone.utc) for k in ('first_seen','stable_since'))

    def reset_observations(self):
        with self.engine.locked(),self.connection() as db:db.execute('DELETE FROM observations')

    def ancestry(self,path,fp,db=None):
        if db is None:
            with self.engine.locked(),self.connection() as connection:return self.ancestry(path,fp,connection)
        row=db.execute('SELECT visited FROM provenance WHERE path=? AND fingerprint=?',(path_key(path),self.encode(fp))).fetchone()
        return {tuple(pair) for pair in json.loads(row[0])} if row else set()

    def register(self,path,fp,visited,db=None):
        if fp is None:return
        if db is None:
            with self.engine.locked(),self.connection() as connection:return self.register(path,fp,visited,connection)
        lineage=self.ancestry(path,fp,db)|set(map(tuple,visited))
        db.execute('INSERT OR REPLACE INTO provenance VALUES(?,?,?)',(path_key(path),self.encode(fp),json.dumps(sorted(lineage))))

    def suppression(self,path,fp,rule):
        with self.engine.locked(),self.connection() as db:
            if db.execute('SELECT 1 FROM blocked WHERE path=?',(path_key(path),)).fetchone():return '先前中断的目标需要核对历史；不会自动重试'
            if (rule.id,rule.revision) in self.ancestry(path,fp,db):return '此规则版本已处理或已访问当前文件链；请核对历史'
        return ''

    def claim(self,plan,name):
        e=self.engine
        with e.locked(),self.connection() as db:
            visited=self.ancestry(plan.original_path,plan.original_fingerprint,db)
            if (plan.rule_id,plan.rule_revision) in visited:return None
            if db.execute('SELECT 1 FROM blocked WHERE path=?',(path_key(plan.original_path),)).fetchone():return None
            key=json.dumps([path_key(plan.original_path),self.encode(plan.original_fingerprint),plan.rule_id,plan.rule_revision])
            if db.execute('SELECT 1 FROM runs WHERE claim_key=?',(key,)).fetchone():return None
            batch=e.journal.create_batch(name,());run=uuid.uuid4().hex
            visited.add((plan.rule_id,plan.rule_revision))
            intended=[{'kind':s.kind,'source':str(s.source),'target':str(s.target),
                'source_fingerprint':self.encode(s.source_fingerprint),'spec':asdict(s.conversion_spec) if s.conversion_spec else None,
                'replaces_original':s.replaces_original,'advances_subject':s.advances_subject,'action_index':s.action_index} for s in plan.steps]
            db.execute('INSERT INTO runs(id,claim_key,original,fingerprint,rule_id,revision,ruleset_revision,template_revision,name,batch_id,status,intended,visited) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (run,key,str(plan.original_path),self.encode(plan.original_fingerprint),plan.rule_id,plan.rule_revision,plan.ruleset_revision,plan.template_revision,name,batch,'queued',json.dumps(intended),json.dumps(sorted(visited))))
            self.register(plan.original_path,plan.original_fingerprint,visited,db)
            ACTIVE_RUNS.add(run)
            ACTIVE_STATES[run]=path_key(e.state_dir)
            return run

    def get(self,run):
        with self.engine.locked(),self.connection() as db:return dict(db.execute('SELECT * FROM runs WHERE id=?',(run,)).fetchone())

    def update(self,run,status,message='',progress=None):
        with self.engine.locked(),self.connection() as db:
            if progress is None:db.execute('UPDATE runs SET status=?,message=? WHERE id=?',(status,message,run))
            else:db.execute('UPDATE runs SET status=?,message=?,progress=? WHERE id=?',(status,message,json.dumps(progress),run))
        if status not in ('queued','running'):
            ACTIVE_RUNS.discard(run);ACTIVE_STATES.pop(run,None)

    def release_unstarted(self,run,message):
        """Called only AFTER a queued future settles, with zero journal intents."""
        e=self.engine
        with e.locked(),self.connection() as db:
            row=db.execute('SELECT * FROM runs WHERE id=?',(run,)).fetchone()
            if row is None or row['status']!='queued' or e.journal.items(row['batch_id']):return False
            original=self.engine.journal.decode(row['fingerprint'])
            try:
                if Fingerprint.capture(row['original'])!=original:return False
            except (OSError,ValueError):return False
            visited=self.ancestry(row['original'],original,db)
            visited.discard((row['rule_id'],row['revision']))
            if visited:
                db.execute('UPDATE provenance SET visited=? WHERE path=? AND fingerprint=?',
                    (json.dumps(sorted(visited)),path_key(row['original']),row['fingerprint']))
            else:db.execute('DELETE FROM provenance WHERE path=? AND fingerprint=?',(path_key(row['original']),row['fingerprint']))
            db.execute("UPDATE runs SET status='canceled_before_start',claim_key=?,message=? WHERE id=?",('canceled:'+run,message,run))
            ACTIVE_RUNS.discard(run);ACTIVE_STATES.pop(run,None)
            return True

    def reconcile(self):
        """Bridge journal→ledger crash gaps and proven inverses without re-encoding."""
        e=self.engine
        with e.locked(),self.connection() as db:
            rows=db.execute('SELECT * FROM runs').fetchall()
            for row in rows:
                visited={tuple(p) for p in json.loads(row['visited'])}
                try:items=e.journal.items(row['batch_id'])
                except KeyError:items=[]
                for item in items:
                    proven=False
                    if item.target is not None and item.target_fingerprint is not None:
                        try:proven=Fingerprint.capture(item.target)==item.target_fingerprint
                        except (OSError,ValueError):pass
                    if proven and item.state in ('committed','undone'):
                        self.register(item.target,item.target_fingerprint,visited,db)
                    elif item.target is not None and item.state not in ('committed','undone','failed','prepared') and item.target.exists():
                        db.execute('INSERT OR IGNORE INTO blocked VALUES(?,?)',(path_key(item.target),row['id']))
                    # undo_fp is recorded only by a verified owned restoration.
                    if item.state=='undone' and item.undo_fingerprint is not None:self.register(item.source,item.undo_fingerprint,visited,db)
                if row['status'] in ('queued','running') and row['id'] not in ACTIVE_RUNS:
                    db.execute("UPDATE runs SET status='review_required',message='上次执行中断；请核对历史，禁止自动重放' WHERE id=?",(row['id'],))

    def history(self):
        with self.engine.locked(),self.connection() as db:return tuple(dict(r) for r in db.execute('SELECT * FROM runs ORDER BY rowid DESC'))
