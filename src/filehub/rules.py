"""Read-only route discovery and deterministic naming. No media or clock access."""
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
import os
import re
import stat
import unicodedata

VIDEO_EXT = {'.mp4', '.mov', '.m4v', '.mkv', '.webm', '.avi'}
IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.heic', '.gif', '.tif', '.tiff', '.bmp', '.avif', '.psd', '.exr'}
ASSET_CATEGORIES = ('角色', '场景', '道具')
GENERIC_KEEP_NAME = {'剧本': '2_剧本分镜', '甲方': '0_甲方', '参考': '_参考'}
BAD_CHARS = dict(zip('\\/:*?"<>|', '＼／：＊？＂＜＞｜'))
DATESEQ_RE = re.compile(r'(?<!\d)(2\d[01]\d[0-3]\d)-(\d{1,3})(?!\d)')

class RouteError(ValueError):
    """Invalid/ambiguous route, unsafe path/name, or missing video metadata."""

@dataclass(frozen=True)
class RouteSpec:
    mode: str
    dest: Path
    prefix: str = ''
    note: str = ''
    ep: int | None = None
    sc: int | None = None
    shots: tuple[tuple[int, str], ...] = ()

class TargetPaths(list[Path]):
    """List-compatible targets with immutable, user-visible warnings."""
    def __init__(self, paths, warnings=()):
        super().__init__(paths)
        self.warnings = tuple(warnings)

def _validate_component(name):
    if not name or name in ('.', '..') or name.endswith((' ', '.')):
        raise RouteError('名称不能为空、包含路径穿越或以空格/点结尾')
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)', name, re.I):
        raise RouteError('名称是 Windows 保留设备名')
    if len(name.encode('utf-16-le')) // 2 > 255:
        raise RouteError('名称超过 255 UTF-16 单元')
    if any(c in name for c in '\\/:*?"<>|'):
        raise RouteError('路径组件包含非法字符')

def safe_name(name: str) -> str:
    # Keep the source extension heuristic, but sanitize both portions.
    base, ext = os.path.splitext(name)
    if len(ext) > 10 or not re.fullmatch(r'\.[\w-]+', ext or '.'):
        base, ext = name, ''
    def clean(text):
        text = ''.join(unicodedata.normalize('NFKC', c) if 0x1D400 <= ord(c) <= 0x1D7FF else c for c in text)
        return ''.join(BAD_CHARS.get(c, c) for c in text if ord(c) <= 0xFFFF and unicodedata.category(c) not in ('Cc', 'Cf', 'Co', 'Cs'))
    result = (clean(base) if clean(base).strip() else '未命名') + clean(ext)
    _validate_component(result)
    return result

def _safe_path(path: Path):
    path = Path(path).absolute()
    for part in path.parts[1:]:
        _validate_component(part)
    for parent in (path, *path.parents):
        if parent.exists() or parent.is_symlink():
            st = parent.lstat()
            if parent.is_symlink() or getattr(st, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                raise RouteError('路径包含符号链接或 reparse point')
    if len(str(path).encode('utf-16-le')) // 2 >= 32767:
        raise RouteError('路径超过 Windows 长路径限制')
    return path

def discover_projects(sync_root: Path) -> dict[str, Path]:
    root = _safe_path(Path(sync_root))
    projects = {}
    if not root.is_dir(): return projects
    for area in sorted(root.iterdir()):
        if not re.match(r'^\d+_', area.name) or area.name in ('0_收件箱', '2_资料库'): continue
        proj_root = _safe_path(area / '项目')
        if not proj_root.is_dir(): continue
        for p in sorted(proj_root.iterdir()):
            m = re.fullmatch(r'\d{6}_([A-Za-z0-9]+)_(.+)', p.name)
            if m and p.is_dir():
                code = m[1].upper()
                if code in projects: raise RouteError(f'重复项目代码：{code}')
                projects[code] = _safe_path(p)
    return projects

def clean_note(text):
    return re.sub(r'[\s_]+', '-', text.strip(' -_'))

def parse_shots(text):
    return tuple((int(n), s.upper()) for n, s in re.findall(r'(\d{1,3})([A-Za-z]?)', text or ''))

def parse_tag(tag: str, projects: dict[str, Path], sync_root: Path) -> RouteSpec:
    root = _safe_path(Path(sync_root))
    normalized = {}
    for code,p in projects.items():
        key=code.upper()
        if key in normalized: raise RouteError(f'重复项目代码：{key}')
        normalized[key]=_safe_path(Path(p))
        if not normalized[key].is_relative_to(root):
            raise RouteError('项目目录不在同步根目录内')
    if tag.strip()=='通用测试': return RouteSpec('dated',root/'2_资料库'/'技术测试')
    body=None
    for code in sorted(normalized,key=len,reverse=True):
        if tag.strip().upper().startswith(code):
            body=tag.strip()[len(code):].strip(' -_')
            if body: break
    if not body: raise RouteError('标签开头不是项目代码或缺少目的地')
    proj=normalized[code]
    def shot(ep,sc,text,note):
        dest=proj/'3_制作'/f'E{ep:02d}'
        prefix=f'E{ep:02d}'
        if sc is not None: dest/=f'S{sc:02d}'; prefix+=f'S{sc:02d}'
        return RouteSpec('shot',dest,prefix,clean_note(note),ep,sc,parse_shots(text))
    m=re.fullmatch(r'(\d{2})(\d{2})(\d{2,3}[A-Za-z]?(?:\+\d{1,3}[A-Za-z]?)*)?[\s\-_]*(.*)',body)
    if m and not re.match(r'\d',m[4]): return shot(int(m[1]),int(m[2]),m[3],m[4])
    m=re.fullmatch(r'[Ee](\d{1,2})(?:[Ss](\d{1,3}))?[\s\-_]*(?:[Cc](\d{1,3}[A-Za-z]?(?:\+\d{1,3}[A-Za-z]?)*))?(.*)',body)
    if m and not re.match(r'\d',m[4]): return shot(int(m[1]),int(m[2]) if m[2] else None,m[3],m[4])
    make=_safe_path(proj/'3_制作')
    seqs=['PV','正片']
    if make.is_dir(): seqs += [p.name for p in make.iterdir() if p.is_dir() and not re.fullmatch(r'E\d+|[._].*',p.name)]
    for seq in sorted(set(seqs),key=len,reverse=True):
        if body.upper().startswith(seq.upper()):
            rest=body[len(seq):].strip(' -_')
            m=re.match(r'[Cc](\d{1,3}[A-Za-z]?(?:\+\d{1,3}[A-Za-z]?)*)(?!\d)',rest)
            return RouteSpec('shot',_safe_path(make/seq),seq,clean_note(rest[m.end():] if m else rest),shots=parse_shots(m[1]) if m else ())
    for cat in ASSET_CATEGORIES:
        if body.startswith(cat):
            rest=body[len(cat):].strip(' -_')
            if not rest: raise RouteError(f'{cat}后面要跟名字')
            parts=re.split(r'[\s\-_]',rest,maxsplit=1)
            name=safe_name(parts[0])
            return RouteSpec('asset',_safe_path(proj/'1_设定'/cat/name),name,clean_note(parts[1] if len(parts)>1 else ''))
    if body.startswith('成片'):
        m=re.search(r'[Ee](\d{1,2})',body)
        return RouteSpec('final',proj/'4_交付',f'E{int(m[1]):02d}_成片' if m else '成片')
    if body in GENERIC_KEEP_NAME: return RouteSpec('keep',proj/GENERIC_KEEP_NAME[body])
    if body=='测试': return RouteSpec('dated',proj/'_测试')
    names={}
    for cat in ASSET_CATEGORIES:
        folder=_safe_path(proj/'1_设定'/cat)
        if folder.is_dir():
            for p in folder.iterdir():
                if p.is_dir() and not p.name.startswith('.'): names[p.name]=cat
    for middle in (False,True):
        for name in sorted(names,key=len,reverse=True):
            if (body.startswith(name) if not middle else len(name)>=2 and name in body):
                note=body[len(name):] if not middle else body.replace(name,' ',1)
                return RouteSpec('asset',_safe_path(proj/'1_设定'/names[name]/name),name,clean_note(note))
    raise RouteError(f'{code}里没有「{body}」，新资产请写类别和名字')

def build_targets(source: Path, spec: RouteSpec, source_time: datetime, video_width: int | None, occupied_names) -> list[Path]:
    source=Path(source)
    dest=_safe_path(spec.dest)
    _safe_path(source)
    occupied={Path(n).name.casefold() for n in occupied_names}
    is_dir=source.is_dir()
    base=source.name; stem=source.stem; ext=source.suffix.lower()
    video=not is_dir and ext in VIDEO_EXT and spec.mode not in ('keep', 'dated')
    if video and (not isinstance(video_width,int) or isinstance(video_width,bool) or video_width<=0):
        raise RouteError('视频探测失败：缺少有效画面宽度')
    tier=('480p' if video_width<1200 else '720p' if video_width<1700 else '1080p' if video_width<3000 else '4K') if video else None
    def target(name):
        return _safe_path(dest/safe_name(name))
    if is_dir or spec.mode in ('keep','dated'):
        if spec.mode=='dated' and not is_dir: dest/=source_time.strftime('%y%m%d')
        name=base if is_dir else safe_name(base)
        _validate_component(name)
        n=2
        while name.casefold() in occupied:
            name=safe_name(f'{Path(base).stem} {n}{Path(base).suffix}'); n+=1
        return TargetPaths([target(name)])
    shots=spec.shots
    if not shots:
        m=re.fullmatch(r'[Cc]?(\d{1,3})([A-Za-z]?)',stem.strip()) or re.search(r'(?:^|_)C(\d{3})([A-Za-z]?)(?:_|$)',stem)
        if m: shots=((int(m[1]),m[2].upper()),)
    team=spec.mode=='shot' and spec.sc is not None and video
    warnings=()
    if team and not shots: raise RouteError('视频要写镜号，例如 E02S08C22，或把文件名改成镜号')
    if video and len(shots)>=3: warnings=('三镜及以上仅保留第一镜母文件，请通知制片',)
    selected=shots if video and len(shots)==2 else shots[:1]
    if not selected: selected=(None,)
    targets=[]
    for shot in selected:
        if team:
            head=f'{spec.ep:02d}_{spec.sc:02d}_{shot[0]:02d}{shot[1]}'
            pat=re.compile(rf'^{re.escape(head.casefold())}_(\d{{2,}})_')
            version=max([int(m[1]) for n in occupied if (m:=pat.match(n))]+[0])+1
            parts=[head,f'{version:02d}',source_time.strftime('%Y%m%d')+('AM' if source_time.hour<12 else 'PM')]
            if spec.note: parts.append(spec.note)
            parts.append(tier)
            name='_'.join(parts)+ext
        else:
            m=DATESEQ_RE.search(stem)
            date_text=m[1] if m else None
            if not date_text:
                dm=re.search(r'(?<!\d)(20\d\d)[-_.]?([01]\d)[-_.]?([0-3]\d)(?!\d)',stem)
                if dm:
                    try: date_text=date(int(dm[1]),int(dm[2]),int(dm[3])).strftime('%y%m%d')
                    except ValueError: pass
            date_text=date_text or source_time.strftime('%y%m%d')
            pat=re.compile(rf'^{re.escape(spec.prefix.casefold())}_(?:.*_)?{date_text}-(\d+)(?:[_.]|$)')
            seq=int(m[2]) if m else max([int(mm[1]) for n in occupied if (mm:=pat.match(n))]+[0])+1
            note=spec.note
            if not note and m and spec.mode in ('asset','shot'):
                before=stem[:m.start()].removesuffix('_')
                prefix=spec.prefix+'_'
                if before.startswith(prefix):
                    remainder=before[len(prefix):]
                    if spec.mode=='shot':
                        remainder=re.sub(r'^C\d{3}[A-Za-z]?(?:_|$)', '', remainder)
                    note=remainder
            parts=[spec.prefix]
            if spec.mode=='shot' and shot: parts.append(f'C{shot[0]:03d}{shot[1]}')
            if spec.mode in ('shot','asset') and note: parts.append(note)
            while True:
                name='_'.join(parts+[f'{date_text}-{seq}']+([tier] if tier else []))+ext
                if safe_name(name).casefold() not in occupied: break
                seq+=1
        path=target(name); occupied.add(path.name.casefold()); targets.append(path)
    return TargetPaths(targets,warnings)
