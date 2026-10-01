"""Current-user integration adapters and durable process-independent send queue.

Static Explorer verbs may invoke one process per selected item. Every process
persists its request before exiting; primary GUI combines settled requests and
acknowledges only after its dialog has accepted ownership. Unacked claims retry.
"""
from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import json
import msvcrt
import os
import sqlite3
import time
import uuid
import winreg
from .models import checked_path
from .platform.windows import process_lock

OWNER='FileHub.Windows.v1'
MENU_KEYS=tuple('Software\\Classes\\'+kind+'\\shell\\FileHub.Send' for kind in ('*','Directory'))
RUN_KEY='Software\\Microsoft\\Windows\\CurrentVersion\\Run'

class HKCURegistry:
    def exists(self,key):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key):return True
        except FileNotFoundError:return False
    def get(self,key,name):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as handle:return winreg.QueryValueEx(handle,name)[0]
        except FileNotFoundError:return None
    def set(self,key,name,value):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,key,0,winreg.KEY_SET_VALUE) as handle:winreg.SetValueEx(handle,name,0,winreg.REG_SZ,value)
    def delete_value(self,key,name):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key,0,winreg.KEY_SET_VALUE) as handle:winreg.DeleteValue(handle,name)
        except FileNotFoundError:pass
    def delete_key_if_empty(self,key):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as handle:
                if winreg.QueryInfoKey(handle)[:2]!=(0,0):return
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER,key)
        except FileNotFoundError:pass


def executable_path(exe):
    exe=Path(exe)
    if not exe.is_absolute() or '"' in str(exe):raise ValueError('可执行路径必须是完整路径')
    return str(exe)


def install_context_menu(exe,*,registry=None):
    exe=executable_path(exe);r=registry if registry is not None else HKCURegistry()
    for key in MENU_KEYS:
        if r.exists(key) and r.get(key,'FileHubOwner')!=OWNER:raise ValueError('右键项已被其他程序占用')
        command=r.get(key+'\\command','')
        if command is not None and r.get(key,'FileHubOwner')!=OWNER:raise ValueError('命令项已有其他所有者')
        if r.get(key,'FileHubOwner')==OWNER and command is not None and command!=r.get(key,'FileHubCommand'):raise ValueError('右键命令被其他程序修改，拒绝覆盖')
    for key in MENU_KEYS:
        r.set(key,'FileHubOwner',OWNER);r.set(key,'','送进项目…')
        command=f'"{exe}" --send "%1"'
        r.set(key,'MultiSelectModel','Player')
        r.set(key,'FileHubCommand',command)
        r.set(key+'\\command','',command)


def remove_context_menu(*,registry=None):
    r=registry if registry is not None else HKCURegistry()
    for key in MENU_KEYS:
        if r.get(key,'FileHubOwner')!=OWNER:continue
        if r.get(key+'\\command','')==r.get(key,'FileHubCommand'):r.delete_value(key+'\\command','')
        r.delete_key_if_empty(key+'\\command')
        for name,value in (('','送进项目…'),('MultiSelectModel','Player'),('FileHubOwner',OWNER)):
            if r.get(key,name)==value:r.delete_value(key,name)
        r.delete_value(key,'FileHubCommand')
        r.delete_key_if_empty(key)


def set_autostart(exe,enabled,*,registry=None):
    if not isinstance(enabled,bool):raise ValueError('自启动开关必须是布尔值')
    value=f'"{executable_path(exe)}" --background';r=registry if registry is not None else HKCURegistry();old=r.get(RUN_KEY,'FileHub')
    if enabled:
        if old is not None and old!=value:raise ValueError('同名自启动项不是此安装所有，拒绝覆盖')
        r.set(RUN_KEY,'FileHub',value)
    elif old==value:r.delete_value(RUN_KEY,'FileHub')


def _known_folder(guid):
    class GUID(ctypes.Structure):_fields_=[('data',ctypes.c_ubyte*16)]
    shell=ctypes.WinDLL('shell32');ole=ctypes.WinDLL('ole32')
    shell.SHGetKnownFolderPath.argtypes=[ctypes.POINTER(GUID),wintypes.DWORD,wintypes.HANDLE,ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype=ctypes.c_long
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
    value=GUID.from_buffer_copy(uuid.UUID(guid).bytes_le);ptr=ctypes.c_void_p()
    result=shell.SHGetKnownFolderPath(ctypes.byref(value),0,None,ctypes.byref(ptr))
    if result<0:raise OSError(f'KnownFolder 查询失败：0x{result&0xffffffff:08x}')
    try:return Path(ctypes.wstring_at(ptr))
    finally:ole.CoTaskMemFree(ptr)


def known_folders(*,resolver=None):
    resolve=resolver or _known_folder
    return {'desktop':Path(resolve('B4BFCC3A-DB2C-424C-B029-7FE99A87C641')),
            'downloads':Path(resolve('374DE290-123F-4565-9164-39C4925E467B'))}


def parse_runtime_args(argv=None):
    parser=argparse.ArgumentParser(prog='FileHub')
    parser.add_argument('--send',nargs='+',default=[])
    parser.add_argument('--background',action='store_true')
    parser.add_argument('--state-dir',type=Path)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--demo',action='store_true')
    return parser.parse_args(argv)

@dataclass(frozen=True)
class SendBatch:
    token: str
    paths: tuple[Path,...]
    request_ids: tuple[str,...]

class SendQueue:
    def __init__(self,state_dir):
        self.state_dir=checked_path(state_dir);self.state_dir.mkdir(parents=True,exist_ok=True)
        self.path=self.state_dir/'send.sqlite';self._lock=process_lock(self.state_dir)
        with self._lock.acquire(),self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,paths TEXT NOT NULL,created REAL NOT NULL,token TEXT,expires REAL)')
    @contextmanager
    def _connect(self):
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row;db.execute('PRAGMA synchronous=FULL')
        try:
            with db:yield db
        finally:db.close()
    def enqueue(self,paths,*,now=None):
        paths=[str(Path(os.path.abspath(p))) for p in paths]
        if not paths:raise ValueError('没有选择要发送的路径')
        request=uuid.uuid4().hex;stamp=time.time() if now is None else now
        with self._lock.acquire(),self._connect() as db:db.execute('INSERT INTO requests VALUES(?,?,?,NULL,NULL)',(request,json.dumps(paths,ensure_ascii=False),stamp))
        return request
    def claim(self,*,now=None,settle_seconds=.3,lease_seconds=30):
        if settle_seconds<0 or lease_seconds<=0:raise ValueError('队列等待和租约必须有效')
        stamp=time.time() if now is None else now
        with self._lock.acquire(),self._connect() as db:
            db.execute('UPDATE requests SET token=NULL,expires=NULL WHERE token IS NOT NULL AND expires<=?',(stamp,))
            if db.execute('SELECT 1 FROM requests WHERE token IS NOT NULL').fetchone():return None
            rows=db.execute('SELECT * FROM requests WHERE token IS NULL ORDER BY created,rowid').fetchall()
            if not rows or stamp-max(r['created'] for r in rows)<settle_seconds:return None
            token=uuid.uuid4().hex;paths=[];seen=set()
            for row in rows:
                for p in json.loads(row['paths']):
                    key=os.path.normcase(p)
                    if key not in seen:paths.append(Path(p));seen.add(key)
                db.execute('UPDATE requests SET token=?,expires=? WHERE id=?',(token,stamp+lease_seconds,row['id']))
            return SendBatch(token,tuple(paths),tuple(r['id'] for r in rows))
    def ack(self,token):
        with self._lock.acquire(),self._connect() as db:
            if not db.execute('DELETE FROM requests WHERE token=?',(token,)).rowcount:raise ValueError('队列租约已失效，不能确认')
    def release(self,token):
        with self._lock.acquire(),self._connect() as db:db.execute('UPDATE requests SET token=NULL,expires=NULL WHERE token=?',(token,))
    def renew(self,token,*,now=None,lease_seconds=30):
        if lease_seconds<=0:raise ValueError('租约必须大于零')
        stamp=time.time() if now is None else now
        with self._lock.acquire(),self._connect() as db:
            if not db.execute('UPDATE requests SET expires=? WHERE token=? AND expires>?',(stamp+lease_seconds,token,stamp)).rowcount:raise ValueError('队列租约已失效')

class InstanceLease:
    def __init__(self,state_dir):
        self.state_dir=checked_path(state_dir);self.state_dir.mkdir(parents=True,exist_ok=True);self.file=None
    def try_acquire(self):
        if self.file is not None:return True
        stream=(self.state_dir/'instance.lock').open('a+b')
        if not stream.seek(0,2):stream.write(b'\0');stream.flush()
        stream.seek(0)
        try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:stream.close();return False
        self.file=stream;return True
    def close(self):
        if self.file is not None:
            try:self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            finally:self.file.close();self.file=None
