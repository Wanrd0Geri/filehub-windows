import subprocess
import sys
import os
from pathlib import Path
import pytest
from filehub.integration import SendQueue, InstanceLease, install_context_menu, remove_context_menu, set_autostart, known_folders, parse_runtime_args

class Registry:
    def __init__(self):self.data={}
    def exists(self,key):return key in self.data
    def get(self,key,name):return self.data.get(key,{}).get(name)
    def set(self,key,name,value):self.data.setdefault(key,{})[name]=value
    def delete_value(self,key,name):self.data.get(key,{}).pop(name,None)
    def delete_key_if_empty(self,key):
        if not self.data.get(key) and not any(k.startswith(key+'\\') for k in self.data):self.data.pop(key,None)


def test_queue_aggregate_dedup_unicode_spaces_and_ack(tmp_path):
    q=SendQueue(tmp_path/'state');a=tmp_path/'中文 file.txt';b=tmp_path/'second.txt'
    q.enqueue([a,a],now=10);q.enqueue([b,a],now=10.1)
    assert q.claim(now=10.2) is None
    batch=q.claim(now=10.5);assert batch.paths==(a,b) and len(batch.request_ids)==2
    assert q.claim(now=10.6) is None
    q.ack(batch.token);assert SendQueue(tmp_path/'state').claim(now=50) is None


def test_unacked_claim_retries_after_crash_lease(tmp_path):
    q=SendQueue(tmp_path/'state');q.enqueue([tmp_path/'a'],now=10)
    first=q.claim(now=11,lease_seconds=2)
    assert SendQueue(tmp_path/'state').claim(now=12) is None
    second=SendQueue(tmp_path/'state').claim(now=14)
    assert second.paths==first.paths and second.token!=first.token
    with pytest.raises(ValueError):q.ack(first.token)
    q.release(second.token);assert q.claim(now=15).paths==first.paths


def test_process_to_process_handoff(tmp_path):
    state=tmp_path/'state';q=SendQueue(state);a=tmp_path/'一 个.txt';b=tmp_path/'二.txt'
    code='from filehub.integration import SendQueue;from pathlib import Path;import sys;SendQueue(Path(sys.argv[1])).enqueue([Path(p) for p in sys.argv[2:]],now=10)'
    env={**os.environ,'PYTHONPATH':str(Path('src').absolute())}
    jobs=[subprocess.Popen([sys.executable,'-X','utf8','-c',code,str(state),str(p)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for p in (a,b,a)]
    for job in jobs:
        out,err=job.communicate(timeout=20);assert job.returncode==0,err.decode()
    batch=q.claim(now=11);assert set(batch.paths)=={a,b} and len(batch.request_ids)==3


def test_primary_lease_excludes_other_process_and_recovers(tmp_path):
    lease=InstanceLease(tmp_path/'state');assert lease.try_acquire()
    code='from filehub.integration import InstanceLease;from pathlib import Path;import sys;x=InstanceLease(Path(sys.argv[1]));print(x.try_acquire());x.close()'
    env={**os.environ,'PYTHONPATH':str(Path('src').absolute())}
    child=subprocess.run([sys.executable,'-c',code,str(tmp_path/'state')],capture_output=True,text=True,env=env,timeout=10)
    assert child.returncode==0 and child.stdout.strip()=='False'
    lease.close();next=InstanceLease(tmp_path/'state');assert next.try_acquire();next.close()


def test_registry_roundtrip_owned_keys_only(tmp_path):
    reg=Registry();exe=tmp_path/'中文 App'/'FileHub.exe'
    reg.set('Software\\Microsoft\\Windows\\CurrentVersion\\Run','Other','other.exe')
    install_context_menu(exe,registry=reg)
    commands=[v[''] for k,v in reg.data.items() if k.endswith('\\command')]
    assert len(commands)==2 and all(cmd==f'"{exe}" --send "%1"' for cmd in commands)
    assert any(v.get('')=='送进项目…' for v in reg.data.values())
    set_autostart(exe,True,registry=reg);set_autostart(exe,False,registry=reg)
    remove_context_menu(registry=reg)
    assert reg.data=={'Software\\Microsoft\\Windows\\CurrentVersion\\Run':{'Other':'other.exe'}}


def test_foreign_registry_entry_never_overwritten_or_removed(tmp_path):
    reg=Registry();key='Software\\Classes\\*\\shell\\FileHub.Send';reg.set(key,'','foreign')
    with pytest.raises(ValueError):install_context_menu(tmp_path/'app.exe',registry=reg)
    remove_context_menu(registry=reg);assert reg.get(key,'')=='foreign'
    run='Software\\Microsoft\\Windows\\CurrentVersion\\Run';reg.set(run,'FileHub','foreign.exe')
    with pytest.raises(ValueError):set_autostart(tmp_path/'app.exe',True,registry=reg)
    set_autostart(tmp_path/'app.exe',False,registry=reg);assert reg.get(run,'FileHub')=='foreign.exe'


def test_known_folders_redirected_proposals_only(tmp_path):
    seen=[]
    def resolve(guid):seen.append(guid);return tmp_path/('redirected-desktop' if len(seen)==1 else 'redirected-downloads')
    proposed=known_folders(resolver=resolve)
    assert proposed=={'desktop':tmp_path/'redirected-desktop','downloads':tmp_path/'redirected-downloads'}
    assert len(seen)==2 and not proposed['desktop'].exists()


def test_runtime_args_preserve_multiselect(tmp_path):
    args=parse_runtime_args(['--state-dir',str(tmp_path/'state'),'--background','--send',str(tmp_path/'一 个'),str(tmp_path/'two')])
    assert args.background and args.send==[str(tmp_path/'一 个'),str(tmp_path/'two')] and args.state_dir==tmp_path/'state'
    assert parse_runtime_args(['--self-test']).self_test

def test_queue_renew_keeps_claim_exclusive(tmp_path):
    q=SendQueue(tmp_path/'state');q.enqueue([tmp_path/'a'],now=1);b=q.claim(now=2,lease_seconds=2)
    q.renew(b.token,now=3,lease_seconds=20)
    assert q.claim(now=10) is None
    q.ack(b.token);assert q.claim(now=30) is None


def test_foreign_modified_command_value_survives_uninstall(tmp_path):
    reg=Registry();install_context_menu(tmp_path/'app.exe',registry=reg)
    command='Software\\Classes\\*\\shell\\FileHub.Send\\command';reg.set(command,'','foreign command')
    remove_context_menu(registry=reg)
    assert reg.get(command,'')=='foreign command'

def test_more_than_fifteen_selected_paths_aggregate(tmp_path):
    reg=Registry();install_context_menu(tmp_path/'app.exe',registry=reg)
    assert all(reg.get(key,'MultiSelectModel')=='Player' for key in ('Software\\Classes\\*\\shell\\FileHub.Send','Software\\Classes\\Directory\\shell\\FileHub.Send'))
    q=SendQueue(tmp_path/'state');paths=tuple(tmp_path/f'中文 file {n}.txt' for n in range(24))
    for p in paths:q.enqueue([p],now=10)
    batch=q.claim(now=11);assert batch.paths==paths and len(batch.request_ids)==24
    q.ack(batch.token)


@pytest.mark.parametrize("kind", ["*", "Directory"])
def test_menu_icon_registered_and_normal_remove_cleans_it(tmp_path, kind):
    reg=Registry();exe=tmp_path/'中文 App'/'FileHub.exe'
    install_context_menu(exe,registry=reg)
    key='Software\\Classes\\'+kind+'\\shell\\FileHub.Send'
    assert reg.get(key,'Icon')==f'"{exe}",0'
    remove_context_menu(registry=reg)
    assert not reg.exists(key)


@pytest.mark.parametrize("kind", ["*", "Directory"])
def test_foreign_modified_menu_icon_survives_remove(tmp_path, kind):
    reg=Registry();exe=tmp_path/'中文 App'/'FileHub.exe'
    install_context_menu(exe,registry=reg)
    key='Software\\Classes\\'+kind+'\\shell\\FileHub.Send'
    reg.set(key,'Icon','"C:/Foreign App/other.exe",7')
    remove_context_menu(registry=reg)
    assert reg.get(key,'Icon')=='"C:/Foreign App/other.exe",7'


@pytest.mark.parametrize("kind", ["*", "Directory"])
def test_foreign_modified_menu_icon_not_overwritten(tmp_path, kind):
    reg=Registry();exe=tmp_path/'中文 App'/'FileHub.exe'
    install_context_menu(exe,registry=reg)
    key='Software\\Classes\\'+kind+'\\shell\\FileHub.Send'
    reg.set(key,'Icon','"C:/Foreign App/other.exe",7')
    before={k:dict(v) for k,v in reg.data.items()}
    with pytest.raises(ValueError):install_context_menu(exe,registry=reg)
    assert reg.data==before
