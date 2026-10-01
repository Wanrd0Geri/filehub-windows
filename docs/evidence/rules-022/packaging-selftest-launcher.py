from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,subprocess,time,hashlib
root=Path.cwd(); own=Path(sys.argv[1]); state=own/'portable-state'; state.mkdir(exist_ok=True)
env={k:v for k,v in os.environ.items() if not k.startswith(('QT_','PYSIDE','PYTHON')) and k not in ('VIRTUAL_ENV',)}
env['PATH']=str(Path(env['SYSTEMROOT'])/'System32')+';'+env['SYSTEMROOT']
startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
cmd=[str(root/'dist/FileHub/FileHub.exe'),'--self-test','--state-dir',str(state)]
t0=time.monotonic(); proc=subprocess.run(cmd,cwd=own,env=env,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
report=json.loads((state/'self-test.json').read_text(encoding='utf-8'))
report.update(execution_kind='Actual packaged FileHub.exe; source Python launches process only',acceptance_command=cmd,process_exit=proc.returncode,elapsed_seconds=round(time.monotonic()-t0,3),checked_utc=datetime.now(timezone.utc).isoformat(),environment={'PATH':env['PATH'],'developer_python_qt_overrides_cleared':True,'bounded_timeout_seconds':120,'owned_uuid_sandbox':str(own)},stderr=proc.stderr.decode('utf-8',errors='replace'))
ev=root/'docs/evidence/rules-022';(ev/'packaging-portable-selftest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert proc.returncode==0 and report['ok'],report
assert len(report['checks'])==23 and all(report['checks'].values()),report['checks']
assert report['release020']['runtime_frozen'] is True
files=[root/'dist/FileHub/FileHub.exe',*sorted((root/'dist/installer').glob('*.exe'))];records=[]
for p in files:records.append({'file':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest()})
expected={'0.2.1':'9268a5c324d311476bca00538321166d42b18f45bfb167442c45e70b7b544f07','0.2.0':'a36ac5a9f21e319d3a35c6aaf31a8a16dcad44254e997688a738659943053735'}
for version,sha in expected.items():assert next(x['sha256'] for x in records if f'FileHub-{version}-' in x['file'])==sha
(ev/'packaging-artifact-hashes.json').write_text(json.dumps({'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'artifacts':records,'historical_installers_preserved':True},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'selftest_exit':proc.returncode,'checks_passed':len(report['checks']),'runtime_frozen':True,'elapsed_seconds':report['elapsed_seconds'],'artifacts':records},indent=2))
