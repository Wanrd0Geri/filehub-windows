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
        if self.sync_root is not None and not isinstance(self.sync_root,Path): raise ValueError('旧同步根目录类型无效')
        if not isinstance(self.watch_roots,(tuple,list)) or len(self.watch_roots)>100 or any(not isinstance(p,Path) for p in self.watch_roots): raise ValueError('观察目录必须是有界路径列表')
        if not isinstance(self.ffprobe_path,str) or not self.ffprobe_path or len(self.ffprobe_path)>32768: raise ValueError('探测程序路径无效')
        state=checked_path(state_dir)
        roots=[checked_path(p) for p in self.watch_roots]
        def overlap(a,b):return a==b or a in b.parents or b in a.parents
        for i,root in enumerate(roots):
            if root==Path(root.anchor):raise ValueError('不能监控磁盘根目录')
            if overlap(state,root):raise ValueError('状态目录不能与监控目录重叠')
            if any(overlap(root,r) for r in roots[:i]):raise ValueError('监控目录相互重叠')
        if not isinstance(self.theme,str) or self.theme not in {'dark','light','system'}:raise ValueError('未知主题')
        if any(not isinstance(v,int) or isinstance(v,bool) or v<0 for v in (self.sweep_days,self.inbox_days)):
            raise ValueError('缓冲天数必须是非负整数')

class ConfigStore:
    def __init__(self,state_dir):self.state_dir=checked_path(state_dir);self.path=self.state_dir/'config.json'
    def load(self):
        if not self.path.exists():return Config()
        checked_path(self.path)
        if self.path.stat().st_size>2_000_000: raise ValueError('配置文件过大')
        def pairs(rows):
            result={}
            for key,value in rows:
                if key in result: raise ValueError('配置字段重复')
                result[key]=value
            return result
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'),object_pairs_hook=pairs,
                parse_constant=lambda x: (_ for _ in ()).throw(ValueError('配置不接受非有限数字')))
        except (UnicodeError,RecursionError) as exc:raise ValueError('配置 JSON 无效或嵌套过深') from exc
        if not isinstance(data,dict) or set(data)-set(Config.__dataclass_fields__)-{'watch','ffprobe'}: raise ValueError('配置包含未知字段或类型')
        for external,internal in [('watch','watch_roots'),('ffprobe','ffprobe_path')]:
            if external in data:
                if internal in data and data[internal]!=data[external]:
                    raise ValueError(f'配置字段冲突：{external} / {internal}')
                data[internal]=data.pop(external)
        if data.get('sync_root') is not None and (not isinstance(data['sync_root'],str) or not data['sync_root']): raise ValueError('旧同步根目录类型无效')
        watch=data.get('watch_roots',())
        if not isinstance(watch,(tuple,list)) or any(not isinstance(p,str) or not p for p in watch): raise ValueError('观察目录类型无效')
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
