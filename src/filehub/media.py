"""Bounded native ffprobe invocation. Binary licensing belongs to packaging."""
from pathlib import Path
import json
import subprocess
import sys

def probe_width(source: Path, executable='resources/ffprobe/ffprobe.exe', *, base_dir=None, timeout=15):
    binary=Path(executable)
    if not binary.is_absolute():
        base=Path(base_dir) if base_dir else Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
        binary=base/binary
    try:
        result=subprocess.run([str(binary),'-v','error','-select_streams','v:0','-show_entries','stream=width',
                               '-of','json',str(source)],shell=False,capture_output=True,text=True,
                              encoding='utf-8',timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise ValueError('媒体格式无效')
        width=json.loads(result.stdout)['streams'][0]['width']
        if not isinstance(width,int) or isinstance(width,bool) or width<=0:raise ValueError('宽度无效')
        return width
    except (OSError,ValueError,TypeError,KeyError,IndexError,subprocess.TimeoutExpired) as exc:
        raise ValueError(f'视频探测失败：{exc}') from exc
