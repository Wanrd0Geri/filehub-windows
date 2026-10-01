from pathlib import Path
import importlib.util
import json
import subprocess
import time
import argparse

spec=importlib.util.spec_from_file_location("acceptance_env",Path(__file__).with_name("acceptance-env.py"))
env=importlib.util.module_from_spec(spec);spec.loader.exec_module(env)
parser=argparse.ArgumentParser();parser.add_argument("--label",default="installed-selftest");parser.add_argument("--portable",action="store_true");args=parser.parse_args()
parent=Path(env.QA["qa_root"])/args.label
if args.portable:env.QA["installed"]=str(env.ROOT/"dist/FileHub")
command=[str(Path(env.QA["installed"])/"FileHub.exe"),"--self-test","--state-dir",str(parent)]
process=subprocess.Popen(command,cwd=env.QA["cwd"],env=env.clean_environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
deadline=time.monotonic()+60
while process.poll() is None and time.monotonic()<deadline:time.sleep(.1)
if process.poll() is None:raise SystemExit(f"Selftest did not finish; owned pid {process.pid} left running without forced termination")
stdout,stderr=process.communicate()
report=json.loads((parent/"self-test.json").read_text(encoding="utf-8"))
assert process.returncode==0 and report["ok"],(process.returncode,report)
assert Path(report["probe"]["path"]).is_relative_to(Path(env.QA["installed"]))
assert report["probe"]["width"]==64
assert [item["width"] for item in report["videos"]]==[1920,1920]
record={"command":command,"cwd":env.QA["cwd"],"child_path":env.clean_environment()["PATH"],
        "exit_code":process.returncode,"stdout_bytes":len(stdout),"stderr":stderr.decode("utf-8",errors="replace"),"report":report}
(Path(env.QA["qa_root"])/(args.label+"-evidence.json")).write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(record,ensure_ascii=False,indent=2))
