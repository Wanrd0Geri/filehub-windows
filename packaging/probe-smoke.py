"""Development-only native probe evidence with a process-isolated environment."""
from pathlib import Path
import argparse
import json
import os
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--generator", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
output = root / "sandbox/task6-media-probes"
output.mkdir(parents=True, exist_ok=True)
probe = root / "third_party/ffprobe/bin/ffprobe.exe"
environment = {name: value for name, value in os.environ.items()
               if name.upper() not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
               and not name.upper().startswith(("QT_", "PYSIDE"))}
windows = Path(os.environ["SystemRoot"])
environment["PATH"] = str(windows / "System32") + os.pathsep + str(windows)
checks = []
for extension, codec, label in (
    ("mp4", "libx264", "H264 MP4"), ("mov", "mpeg4", "MPEG4 MOV"),
    ("m4v", "mpeg4", "MPEG4 M4V"), ("mkv", "libx264", "H264 MKV"),
    ("webm", "libvpx-vp9", "VP9 WEBM"), ("avi", "mpeg4", "MPEG4 AVI"),
):
    fixture = output / ("tiny." + extension)
    subprocess.run([str(args.generator), "-v", "error", "-f", "lavfi", "-i",
                    "color=c=yellow:s=64x48:r=2", "-t", "1", "-c:v", codec,
                    "-an", "-y", str(fixture)], check=True, capture_output=True)
    result = subprocess.run([str(probe), "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=width", "-of", "json", str(fixture)],
                            cwd=output, env=environment, capture_output=True, text=True, timeout=15)
    data = json.loads(result.stdout)
    width = data["streams"][0]["width"]
    if result.returncode != 0 or width != 64 or result.stderr:
        raise RuntimeError((label, result.returncode, result.stdout, result.stderr))
    checks.append({"fixture": str(fixture), "label": label, "width": width, "stderr": result.stderr})
invalid = output / "invalid.mp4"
invalid.write_bytes(b"not media")
bad = subprocess.run([str(probe), "-v", "error", "-show_streams", str(invalid)],
                     cwd=output, env=environment, capture_output=True, text=True, timeout=15)
assert bad.returncode != 0
report = {"ok": True, "probe": str(probe), "path": environment["PATH"],
          "cwd": str(output), "checks": checks,
          "invalid": {"exit_code": bad.returncode, "error": bad.stderr}}
(output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
