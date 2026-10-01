"""Acceptance-only source service using installed native ffprobe, no mocked media/time."""
from pathlib import Path
import json,sys,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from filehub.config import Config
from filehub.service import FileHubService
q=json.loads(Path('sandbox/task6-qa-session.json').read_text());r=Path(q['qa_root']);work=r/'native-rules';assert not work.exists();work.mkdir();sync=work/'sync';project=sync/'1_工作/项目/261001_LYX_临渊行';project.mkdir(parents=True)
for cat,name in [('角色','苏云'),('角色','苏云法相'),('场景','庠序')]: (project/'1_设定'/cat/name).mkdir(parents=True)
s=FileHubService(Config(sync_root=sync,ffprobe_path=str(Path(q['installed'])/'_internal/resources/ffprobe/ffprobe.exe')),work/'state')
records=[]
for i,tag in enumerate(['LYX020815+20','LYX020815+16+17','LYX020822','LYX苏云法相','LYX破败庠序','LYX角色新角色','LYXPV决战']):
 ext='.mp4' if i in (0,1,6) else '.png';p=work/('input-'+str(i)+ext)
 if ext=='.mp4':shutil.copyfile('resources/selftest/tiny-1920-yellow.mp4',p)
 else:
  from PySide6.QtGui import QImage,QColor
  im=QImage(16,16,QImage.Format_RGB32);im.fill(QColor('red'));assert im.save(str(p))
 preview=s.preview([p],tag);assert not preview.items[0].error,preview.items[0].error
 result=s.execute(preview);assert result.ok,result
 assert len(result.outcomes[0].targets)==(2 if i==0 else 1)
 restored=FileHubService(s.config,work/'state').undo(result.batch_id);assert restored.ok and p.exists()
 records.append({'tag':tag,'source_time':str(preview.items[0].source_time),'width':preview.items[0].video_width,'targets':[str(t) for t in result.outcomes[0].targets],'warnings':list(preview.items[0].warnings),'kinds':[x.kind for x in result.items],'batch':result.batch_id,'undo':restored.ok})
p=work/'invalid.mp4';shutil.copyfile('resources/selftest/tiny.mp4',p);before=p.read_bytes();a=s.preview([p],'bad-code');b=s.preview([p],'bad-code');assert a.items[0].error and a.items[0].notify and not b.items[0].notify and not s.execute(a).ok and p.read_bytes()==before
records.append({'invalid_unchanged':True,'notification_once':True})
(r/'native-rules-evidence.json').write_text(json.dumps({'classification':'Windows native source FileHubService, installed ffprobe and real media; no installed UI claim','cases':records},ensure_ascii=False,indent=2));print(json.dumps(records,ensure_ascii=False,indent=2))
