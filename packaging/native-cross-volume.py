"""Acceptance-only source engine, real Windows files and real C/F volumes."""
from pathlib import Path
import json,sys,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from filehub.models import Fingerprint,Operation
from filehub.operations import OperationEngine
q=json.loads(Path('sandbox/task6-qa-session.json').read_text());r=Path(q['qa_root']);c=Path('C:/FileHub-Task6-CrossVolume-'+uuid.uuid4().hex)
assert not c.exists();c.mkdir();(c/'OWNER.txt').write_text('FileHub Task6 native acceptance owned fixture')
s=c/'源.txt';s.write_bytes(b'cross-volume-original');Path(str(s)+':Zone.Identifier').write_bytes(b'[ZoneTransfer]\nZoneId=3\n')
t=r/'cross-volume-target.txt';assert not t.exists();before=Fingerprint.capture(s);e=OperationEngine(r/'cross-volume-state');forward=e.execute([Operation('move',s,t,before)],'native C to F')
assert forward.ok and not s.exists();after=Fingerprint.capture(t);assert before.device!=after.device and before.same_content(after) and before.creation_ns==after.creation_ns and before.mtime_ns==after.mtime_ns
undo=OperationEngine(r/'cross-volume-state').undo(forward.batch_id);assert undo.ok and s.exists() and not t.exists();restored=Fingerprint.capture(s);assert before.same_content(restored) and before.creation_ns==restored.creation_ns and before.mtime_ns==restored.mtime_ns
record={'classification':'Windows native source OperationEngine (not installed GUI)','C_owned_root':str(c),'source':str(s),'target':str(t),'before':before.to_dict(),'after':after.to_dict(),'restored':restored.to_dict(),'batch_id':forward.batch_id,'move_ok':forward.ok,'undo_ok':undo.ok,'fixtures_retained':True}
(r/'cross-volume-evidence.json').write_text(json.dumps(record,ensure_ascii=False,indent=2));print(json.dumps(record,ensure_ascii=False,indent=2))
