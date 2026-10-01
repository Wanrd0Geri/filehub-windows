"""Actual installed GUI launch/screenshot/clean loop-exit evidence, not mouse QA."""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import importlib.util
import json
import os
import subprocess
import time

spec=importlib.util.spec_from_file_location("acceptance_env",Path(__file__).with_name("acceptance-env.py"))
env=importlib.util.module_from_spec(spec);spec.loader.exec_module(env)
parser=argparse.ArgumentParser();parser.add_argument("mode",choices=["normal","demo","background"]);parser.add_argument("--busy",action="store_true")
parser.add_argument("--close-to-tray",action="store_true")
args=parser.parse_args();exe=Path(env.QA["installed"])/"FileHub.exe"
command=[str(exe)]+([] if args.mode=="normal" else ["--demo"] if args.mode=="demo" else ["--background","--state-dir",env.QA["state"]])
process=subprocess.Popen(command,cwd=env.QA["cwd"],env=env.clean_environment())
user=ctypes.WinDLL("user32",use_last_error=True)
user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)];user.GetWindowThreadProcessId.restype=wintypes.DWORD
user.IsWindowVisible.argtypes=[wintypes.HWND];user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
user.PostThreadMessageW.argtypes=[wintypes.DWORD,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
user.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
windows=[]
def visit(hwnd,unused):
    pid=wintypes.DWORD();thread=user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    text=ctypes.create_unicode_buffer(1024);user.GetWindowTextW(hwnd,text,1024)
    if pid.value==process.pid:windows.append({"hwnd":hwnd,"thread":thread,"title":text.value,"visible":bool(user.IsWindowVisible(hwnd))})
    return True
deadline=time.monotonic()+20
while time.monotonic()<deadline:
    windows.clear();user.EnumWindows(callback_type(visit),0)
    primary=[w for w in windows if w["title"].startswith("FileHub")]
    if args.mode=="background":
        primary=[w for w in windows if w["title"]=="QTrayIconMessageWindow"]
    if primary:break
    if process.poll() is not None:raise RuntimeError(("Early process exit",process.returncode))
    time.sleep(.1)
if not primary:raise RuntimeError(("No owned main window",process.pid,windows))
window=primary[0]
record={"command":command,"pid":process.pid,"windows":list(windows),"mode":args.mode}
if args.mode!="background":
    os.environ["QT_QPA_PLATFORM"]="windows"
    from PySide6.QtGui import QGuiApplication
    app=QGuiApplication.instance() or QGuiApplication([])
    time.sleep(.4)
    shot=Path(env.QA["qa_root"])/("installed-"+args.mode+".png")
    assert app.primaryScreen().grabWindow(window["hwnd"]).save(str(shot))
    record["screenshot"]=str(shot)
else:assert not window["visible"]
module_script="(Get-Process -Id "+str(process.pid)+").Modules | Where-Object { $_.ModuleName -match '^(icu|Qt6|.*140)' } | Select-Object ModuleName,FileName | ConvertTo-Json"
modules=subprocess.run([str(Path(os.environ["SystemRoot"])/"System32/WindowsPowerShell/v1.0/powershell.exe"),"-NoProfile","-Command",module_script],capture_output=True,text=True,encoding="utf-8",errors="replace")
record["loaded_modules"]=modules.stdout
if args.close_to_tray:
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    assert user.PostMessageW(window["hwnd"],0x10,0,0)
    time.sleep(.5)
    assert process.poll() is None and not user.IsWindowVisible(window["hwnd"])
    record["close_to_tray"]={"process_alive":True,"main_hidden":True}
    reopen=subprocess.Popen(command,cwd=env.QA["cwd"],env=env.clean_environment())
    deadline=time.monotonic()+10
    while time.monotonic()<deadline and not user.IsWindowVisible(window["hwnd"]):time.sleep(.1)
    assert user.IsWindowVisible(window["hwnd"])
    while reopen.poll() is None and time.monotonic()<deadline:time.sleep(.1)
    assert reopen.poll()==0
    record["close_to_tray"]["secondary_reopen_exit"]=reopen.returncode
if args.busy:
    for action in ("upgrade","uninstall"):
        attempt=subprocess.run([str(env.ROOT/".venv/Scripts/python.exe"),str(Path(__file__).with_name("installer-action.py")),action,"--label","busy-"+action],capture_output=True,text=True,encoding="utf-8",errors="replace")
        result=json.loads((Path(env.QA["qa_root"])/("busy-"+action+"-result.json")).read_text(encoding="utf-8"))
        assert result["exit_code"]!=0 and exe.is_file(),result
        record["busy_"+action]=result
assert user.PostThreadMessageW(window["thread"],0x12,0,0)
deadline=time.monotonic()+20
while process.poll() is None and time.monotonic()<deadline:time.sleep(.1)
assert process.poll()==0,("Program left running, no forced kill",process.pid,process.poll())
record["exit_code"]=process.returncode;record["exit_method"]="Owned GUI thread WM_QUIT; run() finally waits coordinator, not tray mouse invocation"
(Path(env.QA["qa_root"])/("installed-"+args.mode+"-lifecycle.json")).write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(record,ensure_ascii=False,indent=2))
