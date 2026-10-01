from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from filehub.models import Fingerprint,Operation
from filehub.operations import OperationEngine
q=json.loads(Path('sandbox/task6-qa-session.json').read_text());r=Path(q['qa_root']);p=r/'native-recycle-owned-tree';assert not p.exists();(p/'空目录').mkdir(parents=True);(p/'nested').mkdir();(p/'nested/file.txt').write_bytes(b'owned tree content')
e=OperationEngine(r/'native-recycle-state');result=e.execute([Operation('recycle',p,None,Fingerprint.capture(p))],'native whole tree recycle');assert result.ok and not p.exists()
record={'classification':'Windows native source OperationEngine recycle','origin':str(p),'batch':result.batch_id,'items':[{'state':i.state,'staging':str(i.staging),'recycle_identity':i.recycle_identity,'message':i.message} for i in result.items]}
(r/'native-recycle-evidence.json').write_text(json.dumps(record,ensure_ascii=False,indent=2));print(json.dumps(record,ensure_ascii=False,indent=2))
