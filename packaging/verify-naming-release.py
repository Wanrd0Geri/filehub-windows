"""Verify shipped naming bytecode and the portable runtime in isolated fixtures."""
from datetime import datetime, timezone
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader
import hashlib
import json
import os
import subprocess
import sys
import types
import uuid

root=Path(__file__).resolve().parents[1]
exe=root/'dist/FileHub/FileHub.exe'
installer=root/'dist/installer/FileHub-0.1.2-windows-x64-setup.exe'
archive=CArchiveReader(str(exe))
pyz=archive.open_embedded_archive(next(n for n,v in archive.toc.items() if v[-1]=='z'))
module=types.ModuleType('_packaged_filehub_rules')
sys.modules[module.__name__]=module
exec(pyz.extract('filehub.rules'),module.__dict__)

fixture=root/'sandbox'/('naming-012-'+uuid.uuid4().hex)
project=fixture/'sync/1_工作/项目/261003_LYX_临渊行'
project.mkdir(parents=True)
when=datetime(2026,10,3,15,tzinfo=timezone.utc)
projects=module.discover_projects(fixture/'sync')
results=[]
cases=[
 ('LYXPV打斗去雪-1',['PV_决战打斗_261003-5_480p.mp4'],
  'PV_打斗去雪-1_261003-1_1080p.mp4'),
 ('LYXPV打斗去雪',['PV_打斗去雪_261002-3_4K.mp4',
  'PV_打斗去雪-1_261003-99_1080p.mp4'],
  'PV_打斗去雪_261003-4_1080p.mp4'),
]
for tag,occupied,expected in cases:
    spec=module.parse_tag(tag,projects,fixture/'sync')
    actual=module.build_targets(fixture/'input.mp4',spec,when,1920,occupied)[0].name
    assert actual==expected,(tag,actual,expected)
    results.append({'tag':tag,'occupied':occupied,'actual':actual,'expected':expected})

env={k:v for k,v in os.environ.items() if k.upper() not in {'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'}
     and not k.upper().startswith(('QT_','PYSIDE'))}
windows=Path(os.environ['SystemRoot'])
env['PATH']=str(windows/'System32')+os.pathsep+str(windows)
env['LOCALAPPDATA']=str(fixture/'localappdata')
run=subprocess.run([str(exe),'--self-test','--state-dir',str(fixture/'portable-selftest')],
                   cwd=fixture,env=env,capture_output=True,timeout=60,
                   creationflags=subprocess.CREATE_NO_WINDOW)
runtime=json.loads((fixture/'portable-selftest/self-test.json').read_text(encoding='utf-8'))
assert run.returncode==0 and runtime['ok'],(run.returncode,runtime)
assert Path(runtime['probe']['path']).is_relative_to(exe.parent)
def artifact(p):
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
report={'ok':True,'packaged_naming_cases':results,'portable_selftest':runtime,
        'exit_code':run.returncode,'stderr':run.stderr.decode('utf-8',errors='replace'),
        'artifacts':[artifact(exe),artifact(installer)],
        'scope':'Isolated fixtures only; existing installation and project videos were not changed.'}
destination=root/'docs/evidence/naming-012-release.json'
destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'ok':True,'packaged_naming_cases':results,'runtime_checks':runtime['checks'],
                  'artifacts':report['artifacts'],'report':str(destination)},ensure_ascii=False,indent=2))
