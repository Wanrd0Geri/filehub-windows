"""Explicit local settings; no automatically activated real directories."""
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import os
import tempfile
from .models import checked_path

@dataclass(frozen=True)
class Config:
    sync_root: Path | None = None
    watch_roots: tuple[Path, ...] = ()
    paused: bool = True
    global_jobs: bool = False
    sweep_days: int = 3
    inbox_days: int = 3
    theme: str = 'dark'
    ffprobe_path: str = 'resources/ffprobe/ffprobe.exe'

    def validate(self, state_dir):
        if not isinstance(self.paused,bool) or not isinstance(self.global_jobs,bool):
            raise ValueError('暂停和全局任务开关必须是布尔值')
        state=checked_path(state_dir)
        roots=[checked_path(p) for p in self.watch_roots]
        sync=checked_path(self.sync_root) if self.sync_root else None
        if sync and sync==Path(sync.anchor):raise ValueError('同步空间不能选择磁盘根目录')
        def overlap(a,b):return a==b or a in b.parents or b in a.parents
        if sync and overlap(state,sync):raise ValueError('状态目录不能与同步项目重叠')
        for i,root in enumerate(roots):
            if root==Path(root.anchor):raise ValueError('不能监控磁盘根目录')
            if overlap(state,root):raise ValueError('状态目录不能与监控目录重叠')
            if sync and overlap(root,sync):raise ValueError('监控目录不能与同步项目重叠')
            if any(overlap(root,r) for r in roots[:i]):raise ValueError('监控目录相互重叠')
        if self.theme not in {'dark','light','system'}:raise ValueError('未知主题')
        if any(not isinstance(v,int) or isinstance(v,bool) or v<0 for v in (self.sweep_days,self.inbox_days)):
            raise ValueError('缓冲天数必须是非负整数')

class ConfigStore:
    def __init__(self,state_dir):self.state_dir=checked_path(state_dir);self.path=self.state_dir/'config.json'
    def load(self):
        if not self.path.exists():return Config()
        data=json.loads(self.path.read_text(encoding='utf-8'))
        for external,internal in [('watch','watch_roots'),('ffprobe','ffprobe_path')]:
            if external in data:
                if internal in data and data[internal]!=data[external]:
                    raise ValueError(f'配置字段冲突：{external} / {internal}')
                data[internal]=data.pop(external)
        data['sync_root']=Path(data['sync_root']) if data.get('sync_root') else None
        data['watch_roots']=tuple(Path(p) for p in data.get('watch_roots',()))
        cfg=Config(**data);cfg.validate(self.state_dir);return cfg
    def save(self,config):
        config.validate(self.state_dir);self.state_dir.mkdir(parents=True,exist_ok=True)
        data=asdict(config);data['sync_root']=str(config.sync_root) if config.sync_root else None
        data.pop('watch_roots');data['watch']=[str(p) for p in config.watch_roots]
        data['ffprobe']=data.pop('ffprobe_path')
        fd,name=tempfile.mkstemp(prefix='.config-',dir=self.state_dir)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump(data,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
            os.replace(name,self.path)
        finally:
            if os.path.exists(name):os.unlink(name)
