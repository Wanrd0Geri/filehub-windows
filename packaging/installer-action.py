"""Owned installer lifecycle driver (acceptance-only, not shipped)."""
from pathlib import Path
import argparse
import importlib.util
import json
import subprocess
import time

spec=importlib.util.spec_from_file_location("acceptance_env",Path(__file__).with_name("acceptance-env.py"))
env=importlib.util.module_from_spec(spec);spec.loader.exec_module(env)
parser=argparse.ArgumentParser();parser.add_argument("action",choices=["install","upgrade","uninstall"])
parser.add_argument("--tasks",default="");parser.add_argument("--label",default="")
args=parser.parse_args();label=args.label or args.action
log=Path(env.QA["qa_root"])/(label+".log")
if args.action=="uninstall":
    command=[str(Path(env.QA["installed"])/"unins000.exe"),"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/LOG="+str(log)]
else:
    command=[str(env.ROOT/"dist/installer/FileHub-0.1.0-windows-x64-setup.exe"),"/VERYSILENT","/SUPPRESSMSGBOXES",
             "/NORESTART","/CURRENTUSER","/DIR="+env.QA["installed"],"/GROUP="+env.QA["group"],
             "/TASKS="+args.tasks,"/LOG="+str(log)]
process=subprocess.Popen(command,cwd=env.QA["cwd"],env=env.clean_environment())
deadline=time.monotonic()+90
while process.poll() is None and time.monotonic()<deadline:time.sleep(.1)
record={"action":args.action,"command":command,"pid":process.pid,"exit_code":process.poll(),"log":str(log)}
(Path(env.QA["qa_root"])/(label+"-result.json")).write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(record,ensure_ascii=False,indent=2))
if process.poll() is None:raise SystemExit("Installer did not finish; left running without forced termination")
raise SystemExit(process.returncode)
