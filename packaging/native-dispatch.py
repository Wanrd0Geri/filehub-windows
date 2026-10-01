"""Native installed dispatch evidence; controlled lease only gates initial burst."""
from pathlib import Path
import ctypes,importlib.util,json,os,sqlite3,subprocess,sys,time,winreg
from ctypes import wintypes
spec=importlib.util.spec_from_file_location('env',Path(__file__).with_name('acceptance-env.py'));env=importlib.util.module_from_spec(spec);spec.loader.exec_module(env)
sys.path.insert(0,str(env.ROOT/'src'));from filehub.integration import InstanceLease
r=Path(env.QA['qa_root']);exe=Path(env.QA['installed'])/'FileHub.exe';u=ctypes.WinDLL('user32');u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)];u.GetWindowThreadProcessId.restype=wintypes.DWORD;u.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int];u.PostThreadMessageW.argtypes=[wintypes.DWORD,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM];u.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM];cb=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
def windows(pid):
 result=[]
 def visit(h,l):
  p=wintypes.DWORD();t=u.GetWindowThreadProcessId(h,ctypes.byref(p));s=ctypes.create_unicode_buffer(1024);u.GetWindowTextW(h,s,1024)
  if p.value==pid:result.append({'hwnd':h,'thread':t,'title':s.value,'visible':bool(u.IsWindowVisible(h))})
  return True
 u.EnumWindows(cb(visit),0);return result
def rows(state):
 with sqlite3.connect(state/'send.sqlite') as d:return d.execute('select id,paths,token from requests').fetchall()
def finish(mode,state,primary,expected):
 deadline=time.monotonic()+20;found=[]
 while time.monotonic()<deadline:
  found=[w for w in windows(primary.pid) if w['title']=='送进项目']
  if found and len(rows(state))==expected and all(x[2] for x in rows(state)):break
  time.sleep(.1)
 assert len(found)==1,(mode,windows(primary.pid));data=rows(state);assert len(data)==expected and len(set(x[2] for x in data))==1,data
 from PySide6.QtGui import QGuiApplication
 app=QGuiApplication.instance() or QGuiApplication([]);shot=r/(mode+'-dialog.png');assert app.primaryScreen().grabWindow(found[0]['hwnd']).save(str(shot))
 assert u.PostMessageW(found[0]['hwnd'],0x10,0,0)
 deadline=time.monotonic()+10
 while rows(state) and time.monotonic()<deadline:time.sleep(.1)
 assert not rows(state);assert u.PostThreadMessageW(found[0]['thread'],0x12,0,0)
 deadline=time.monotonic()+20
 while primary.poll() is None and time.monotonic()<deadline:time.sleep(.1)
 assert primary.poll()==0
 return {'dialog_count':len(found),'claimed_requests':len(data),'paths':[json.loads(x[1]) for x in data],'single_claim_token':True,'cancel_ack_remaining':0,'exit_code':primary.returncode,'screenshot':str(shot),'quit_method':'dialog WM_CLOSE cancellation, GUI thread WM_QUIT'}
mode=sys.argv[1];state=r/(mode+'-state');assert not state.exists();state.mkdir();files=r/(mode+'-files');files.mkdir();count=20 if mode=='aggregate' else 1;paths=[]
for i in range(count):p=files/('owned-'+str(i)+'.txt');p.write_text('owned '+str(i));paths.append(p)
record={'classification':'Native installed processes and dialog; aggregation initial timing gated by source InstanceLease' if mode=='aggregate' else 'Native Shell.Application single-file owned verb, not Explorer mouse selection'}
if mode=='aggregate':
 lease=InstanceLease(state);assert lease.try_acquire();children=[subprocess.Popen([str(exe),'--state-dir',str(state),'--send',str(p)],cwd=env.QA['cwd'],env=env.clean_environment()) for p in paths]
 deadline=time.monotonic()+30
 while any(p.poll() is None for p in children) and time.monotonic()<deadline:time.sleep(.1)
 assert all(p.poll()==0 for p in children);assert len(rows(state))==20;record['secondary_exits']=[p.returncode for p in children];record['durable_before_primary']=20;lease.close();primary=subprocess.Popen([str(exe),'--state-dir',str(state),'--background'],cwd=env.QA['cwd'],env=env.clean_environment())
else:
 primary=subprocess.Popen([str(exe),'--state-dir',str(state),'--background'],cwd=env.QA['cwd'],env=env.clean_environment());time.sleep(1)
 key='Software\\Classes\\*\\shell\\FileHub.Task6QA.d26ef8d9';command=f'"{exe}" --state-dir "{state}" --send "%1"';label='送进项目 Task6 QA d26ef8d9'
 try:
  winreg.OpenKey(winreg.HKEY_CURRENT_USER,key);raise AssertionError('QA key preexists')
 except FileNotFoundError:pass
 with winreg.CreateKey(winreg.HKEY_CURRENT_USER,key) as h:winreg.SetValueEx(h,'',0,winreg.REG_SZ,label)
 with winreg.CreateKey(winreg.HKEY_CURRENT_USER,key+'\\command') as h:winreg.SetValueEx(h,'',0,winreg.REG_SZ,command)
 script="$s=New-Object -ComObject Shell.Application; $f=$s.Namespace('"+str(files)+"').ParseName('"+paths[0].name+"'); $v=@($f.Verbs() | Where-Object {$_.Name -eq '"+label+"'}); if($v.Count -ne 1){throw 'Owned verb not unique'}; $v[0].DoIt(); $v[0].Name"
 try:
  out=subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,text=True,encoding='utf-8',errors='replace');assert out.returncode==0,out.stderr;record['shell_verb']=label;record['command']=command
 finally:
  winreg.DeleteKey(winreg.HKEY_CURRENT_USER,key+'\\command');winreg.DeleteKey(winreg.HKEY_CURRENT_USER,key)
record.update(finish(mode,state,primary,count));(r/(mode+'-dispatch-evidence.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2));print(json.dumps(record,ensure_ascii=False,indent=2))
