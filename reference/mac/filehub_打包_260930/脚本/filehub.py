#!/usr/bin/python3
"""filehub：桌面/下载/收件箱的文件路由，由 Hazel 调用。

用法：
  filehub.py has-route FILE   有路由标签返回 0（给 Hazel 的「通过 shell 脚本」条件用）
  filehub.py route FILE       按路由标签移动并改名
  filehub.py sweep FILE       没有路由标签的文件移进 0_收件箱/<图片|视频|其他>/<日期>/
  filehub.py due FILE         Hazel 条件：现在该处理返回 0
  filehub.py handle FILE      Hazel 动作：路由 / 收进收件箱 / 过期进废纸篓
  filehub.py tick             一次处理桌面、下载、收件箱（手动或定时任务用）
  filehub.py undo LOGFILE     按日志倒序撤销移动（迁移用）

规则说明见同目录 README.md。
"""
import datetime as dt
import json
import os
import plistlib
import re
import hashlib
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.expanduser(os.environ.get("FILEHUB_ROOT", "~/同步空间"))
INBOX = os.path.join(ROOT, "0_收件箱")
LIBRARY = os.path.join(ROOT, "2_资料库")
LOG_DIR = os.path.expanduser(os.environ.get("FILEHUB_LOG_DIR", "~/Library/Logs/filehub"))
TRASH = os.path.expanduser(os.environ.get("FILEHUB_TRASH", "~/.Trash"))
WATCHED = [os.path.expanduser(p) for p in
           os.environ.get("FILEHUB_WATCH", "~/Desktop:~/Downloads").split(":")]
FFPROBE = "/opt/homebrew/bin/ffprobe"

TAG_XATTR = "com.apple.metadata:_kMDItemUserTags"

# Finder 自带的颜色/默认标签，不当作路由标签
PLAIN_TAGS = {
    "红色", "橙色", "黄色", "绿色", "蓝色", "紫色", "灰色",
    "Red", "Orange", "Yellow", "Green", "Blue", "Purple", "Gray",
    "重要", "工作", "家庭", "个人", "Important", "Work", "Home", "Personal",
}

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".gif", ".tif", ".tiff", ".bmp", ".avif", ".psd", ".exr"}

GENERIC_KEEP_NAME = {"剧本": "2_剧本分镜", "甲方": "0_甲方", "参考": "_参考"}
ASSET_CATEGORIES = ("角色", "场景", "道具")


class RouteError(Exception):
    pass


# ---------- 小工具 ----------

def load_config():
    path = os.environ.get("FILEHUB_CONFIG", os.path.join(HERE, "config.json"))
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def log(action, src, dst=""):
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(LOG_DIR, "filehub.log"), "a", encoding="utf-8") as f:
        f.write(f"{stamp}\t{action}\t{src}\t{dst}\n")


def notify(title, message):
    subprocess.run(
        ["/usr/bin/osascript", "-e", "on run argv",
         "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
         "-e", "end run", title, message],
        capture_output=True,
    )
    log("通知", f"{title}：{message}")


def read_plist_xattr(path, name):
    r = subprocess.run(["/usr/bin/xattr", "-px", name, path], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return plistlib.loads(bytes.fromhex("".join(r.stdout.split())))
    except Exception:
        return None


def read_tags(path):
    raw = read_plist_xattr(path, TAG_XATTR) or []
    return [t.split("\n")[0] for t in raw]


def remove_tag(path, tag):
    raw = read_plist_xattr(path, TAG_XATTR) or []
    kept = [t for t in raw if t.split("\n")[0] != tag]
    if kept:
        data = plistlib.dumps(kept, fmt=plistlib.FMT_BINARY).hex()
        subprocess.run(["/usr/bin/xattr", "-wx", TAG_XATTR, data, path], capture_output=True)
    else:
        subprocess.run(["/usr/bin/xattr", "-d", TAG_XATTR, path], capture_output=True)


def is_routing_tag(tag, projects=None):
    """路由标签 = 以项目代码开头，或「通用测试」。其余标签（颜色、自己的分类）一律不管。"""
    if tag.strip() == "通用测试":
        return True
    return split_code(tag, projects if projects is not None else active_projects())[0] is not None


def birth_date(path):
    st = os.stat(path)
    return dt.datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_mtime))


def date_from_name(stem):
    m = re.search(r"(?<!\d)(20\d\d)[-_.]?([01]\d)[-_.]?([0-3]\d)(?!\d)", stem)
    if m:
        try:
            return dt.date(int(m[1]), int(m[2]), int(m[3])).strftime("%y%m%d")
        except ValueError:
            pass
    return None


def video_tier(path):
    width = None
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30)
        width = int(r.stdout.strip().split(",")[0])
    except Exception:
        r = subprocess.run(["/usr/bin/mdls", "-raw", "-name", "kMDItemPixelWidth", path],
                           capture_output=True, text=True)
        if r.stdout.strip().isdigit():
            width = int(r.stdout.strip())
    if not width:
        return None
    if width < 1200:
        return "480p"
    if width < 1700:
        return "720p"
    if width < 3000:
        return "1080p"
    return "4K"


def unique_path(dest_dir, name):
    base, ext = os.path.splitext(name)
    candidate = os.path.join(dest_dir, name)
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(dest_dir, f"{base} {n}{ext}")
        n += 1
    return candidate


BAD_CHARS = {'\\': '＼', '/': '／', ':': '：', '*': '＊', '?': '？', '"': '＂', '<': '＜', '>': '＞', '|': '｜'}
MAX_NAME = 150  # 兜底，防止超长名


def safe_name(name):
    """百度网盘同步不了的文件名：特殊符号换全角，花体字母数字转普通，去掉 emoji，过长截断。"""
    import unicodedata
    base, ext = os.path.splitext(name)
    if len(ext) > 10 or not re.fullmatch(r"\.[\w-]+", ext or "."):
        base, ext = name, ""
    base = "".join(unicodedata.normalize("NFKC", c) if 0x1D400 <= ord(c) <= 0x1D7FF else c for c in base)  # 𝟖𝐊 → 8K
    base = "".join(BAD_CHARS.get(c, c) for c in base if ord(c) <= 0xFFFF and unicodedata.category(c) not in ("Cc", "Cf", "Co", "Cs"))
    if len(base) > MAX_NAME:
        base = base[:MAX_NAME].rstrip(" .-_")
    return (base if base.strip() else "未命名") + ext


def move(src, dest_dir, new_name=None, action="移动"):
    os.makedirs(dest_dir, exist_ok=True)
    name = new_name or os.path.basename(src)
    if dest_dir != TRASH and not os.path.isdir(src):
        name = safe_name(name)
    dst = unique_path(dest_dir, name)
    shutil.move(src, dst)
    log(action, src, dst)
    return dst


def to_trash(src):
    return move(src, TRASH, action="废纸篓")


# ---------- 项目 ----------

PROJECT_RE = re.compile(r"^(\d{6})_([A-Za-z0-9]+)_(.+)$")


def active_projects():
    """{代码: 路径}。区域 = 同步空间下以数字开头的文件夹（收件箱、资料库除外），项目在其 项目/ 下。"""
    projects = {}
    if not os.path.isdir(ROOT):
        return projects
    for area in sorted(os.listdir(ROOT)):
        area_path = os.path.join(ROOT, area)
        if not re.match(r"^\d+_", area) or area in ("0_收件箱", "2_资料库"):
            continue
        proj_root = os.path.join(area_path, "项目")
        if not os.path.isdir(proj_root):
            continue
        for name in sorted(os.listdir(proj_root)):
            m = PROJECT_RE.match(name)
            if m and os.path.isdir(os.path.join(proj_root, name)):
                projects[m[2].upper()] = os.path.join(proj_root, name)
    return projects


SEP = " -_"


def split_code(tag, projects):
    """标签开头是项目代码（不分大小写）→ (代码, 其余部分)，否则 (None, 标签)。"""
    t = tag.strip()
    for code in sorted(projects, key=len, reverse=True):
        if t.upper().startswith(code):
            rest = t[len(code):].strip(SEP)
            if rest:
                return code, rest
    return None, t


def asset_names(proj):
    """项目里已有的资产 {名字: 类别}。"""
    names = {}
    for cat in ASSET_CATEGORIES:
        folder = os.path.join(proj, "1_设定", cat)
        if os.path.isdir(folder):
            for n in os.listdir(folder):
                if not n.startswith(".") and os.path.isdir(os.path.join(folder, n)):
                    names[n] = cat
    return names


def clean_note(text):
    return re.sub(r"[\s_]+", "-", text.strip(SEP))


# ---------- 解析标签 ----------

def parse_shots(text):
    """「15A+20」→ [(15, "A"), (20, "")]；空 → []。"""
    return [(int(n), suf.upper()) for n, suf in re.findall(r"(\d{1,3})([A-Za-z]?)", text or "")]


def shot_spec(proj, ep, sc, shot_text, note):
    if sc is not None:
        rel, prefix = os.path.join("3_制作", f"E{ep:02d}", f"S{sc:02d}"), f"E{ep:02d}S{sc:02d}"
    else:
        rel, prefix = os.path.join("3_制作", f"E{ep:02d}"), f"E{ep:02d}"
    shots = parse_shots(shot_text)
    return dict(mode="shot", dest=os.path.join(proj, rel), prefix=prefix, ep=ep, sc=sc,
                shots=shots, shot=shots[0][0] if shots else None, note=clean_note(note))


def parse_tag(tag, projects):
    """标签 = 项目代码 + 目的地，例如 LYXE02S10C25、LYX苏云法相、LYX角色劫灰怪。
    返回 dict(dest=目标文件夹, prefix=命名前缀, note, shot, mode)。
    mode: shot（集场/PV/正片）、asset、final（成片）、keep（保留原名）、dated（保留原名，放日期子文件夹）"""
    if tag.strip() == "通用测试":
        return dict(mode="dated", dest=os.path.join(LIBRARY, "技术测试"))
    code, body = split_code(tag, projects)
    if not code:
        raise RouteError(f"标签「{tag}」开头不是项目代码（{'、'.join(sorted(projects))}）")
    proj = projects[code]

    # 集场镜紧凑写法：LYX020822（集 02 场 08 镜 22）、LYX020815A、LYX020815+20、LYX0208105
    m = re.fullmatch(r"(\d{2})(\d{2})(\d{2,3}[A-Za-z]?(?:\+\d{1,3}[A-Za-z]?)*)?[\s\-_]*(.*)", body)
    if m and not re.match(r"\d", m[4]):
        return shot_spec(proj, int(m[1]), int(m[2]), m[3], m[4])

    # 集、场、镜：E02S10C25 / E01C3 / E02S10，镜号可带 A/B 和 +（C15A、C15+20）
    m = re.fullmatch(r"[Ee](\d{1,2})(?:[Ss](\d{1,3}))?[\s\-_]*(?:[Cc](\d{1,3}[A-Za-z]?(?:\+\d{1,3}[A-Za-z]?)*))?(.*)", body)
    if m and (m[4] == "" or not re.match(r"\d", m[4])):
        return shot_spec(proj, int(m[1]), int(m[2]) if m[2] else None, m[3], m[4])

    # 不分集的段落：PV、正片，或 3_制作 下已有的其他文件夹；可跟镜号 PVC3
    seqs = ["PV", "正片"]
    make = os.path.join(proj, "3_制作")
    if os.path.isdir(make):
        seqs += [n for n in os.listdir(make) if not re.fullmatch(r"E\d+|[._].*", n)]
    for seq in sorted(set(seqs), key=len, reverse=True):
        if body.upper().startswith(seq.upper()):
            rest = body[len(seq):].strip(SEP)
            m = re.match(r"[Cc](\d{1,3})(?!\d)", rest)
            note = rest[m.end():] if m else rest
            return dict(mode="shot", dest=os.path.join(make, seq), prefix=seq,
                        shot=int(m[1]) if m else None, note=clean_note(note))

    # 新资产：角色劫灰怪、场景雪林、道具仙剑（名字后面用空格或 - 接备注）
    for cat in ASSET_CATEGORIES:
        if body.startswith(cat):
            rest = body[len(cat):].strip(SEP)
            if not rest:
                raise RouteError(f"「{cat}」后面要跟名字，例如「{code}{cat}劫灰怪」")
            parts = re.split(r"[\s\-_]", rest, maxsplit=1)
            name, note = parts[0], (parts[1] if len(parts) > 1 else "")
            return dict(mode="asset", dest=os.path.join(proj, "1_设定", cat, name), prefix=name,
                        note=clean_note(note))

    if body.startswith("成片"):
        m = re.search(r"[Ee](\d{1,2})", body)
        ep = f"E{int(m[1]):02d}" if m else None
        return dict(mode="final", dest=os.path.join(proj, "4_交付"), prefix=f"{ep}_成片" if ep else "成片")

    if body in GENERIC_KEEP_NAME:
        return dict(mode="keep", dest=os.path.join(proj, GENERIC_KEEP_NAME[body]))

    if body == "测试":
        return dict(mode="dated", dest=os.path.join(proj, "_测试"))

    # 已有资产：LYX苏云、LYX苏云法相（最长的资产名优先）
    names = asset_names(proj)
    for name in sorted(names, key=len, reverse=True):
        if body.startswith(name):
            return dict(mode="asset", dest=os.path.join(proj, "1_设定", names[name], name), prefix=name,
                        note=clean_note(body[len(name):]))

    # 资产名在中间：LYX破败庠序 → 庠序，备注「破败」
    for name in sorted(names, key=len, reverse=True):
        if len(name) >= 2 and name in body:
            note = body.replace(name, " ", 1)
            return dict(mode="asset", dest=os.path.join(proj, "1_设定", names[name], name), prefix=name,
                        note=clean_note(note))

    raise RouteError(f"{code} 里没有「{body}」。新资产写成「{code}场景{body}」（或 角色、道具）")


# ---------- 命名 ----------

DATESEQ_RE = re.compile(r"(?<!\d)(2\d[01]\d[0-3]\d)-(\d{1,3})(?!\d)")


def next_seq(dest, prefix, date):
    pat = re.compile(rf"^{re.escape(prefix)}_(?:.*_)?{date}-(\d+)(?:[_.]|$)")
    top = 0
    if os.path.isdir(dest):
        for n in os.listdir(dest):
            m = pat.match(n)
            if m:
                top = max(top, int(m[1]))
    return top + 1


def shot_str(shot):
    n, suf = shot
    return f"{n:02d}{suf}"


def team_name(path, spec, shot):
    """视频组规范：集_场_镜_版本_日期AM/PM[_备注]_分辨率，例如 02_08_22_01_20260926PM_1080p.mp4。"""
    ext = os.path.splitext(path)[1].lower()
    head = f"{spec['ep']:02d}_{spec['sc']:02d}_{shot_str(shot)}"
    ver = 0
    if os.path.isdir(spec["dest"]):
        pat = re.compile(rf"^{re.escape(head)}_(\d{{2,}})_")
        for n in os.listdir(spec["dest"]):
            m = pat.match(n)
            if m:
                ver = max(ver, int(m[1]))
    t = birth_date(path)  # 文件创建时间 = 即梦下载下来那一刻
    parts = [head, f"{ver + 1:02d}", t.strftime("%Y%m%d") + ("AM" if t.hour < 12 else "PM")]
    if spec.get("note"):
        parts.append(spec["note"])
    tier = video_tier(path)
    if tier:
        parts.append(tier)
    return "_".join(parts) + ext


def uses_team_name(path, spec):
    return (spec["mode"] == "shot" and spec.get("sc") is not None
            and os.path.splitext(path)[1].lower() in VIDEO_EXT)


def build_name(path, spec):
    base = os.path.basename(path)
    stem, ext = os.path.splitext(base)
    ext = ext.lower()

    shots = spec.get("shots") or []
    if not shots:
        m = re.fullmatch(r"[Cc]?(\d{1,3})([A-Za-z]?)", stem.strip()) or re.search(r"(?:^|_)C(\d{3})([A-Za-z]?)(?:_|$)", stem)
        if m:
            shots = [(int(m[1]), m[2].upper())]
    if uses_team_name(path, spec):
        if not shots:
            raise RouteError("视频要写镜号，例如「LYX020822」，或把文件名改成镜号")
        return team_name(path, spec, shots[0])
    shot = shots[0][0] if shots else None
    suffix = shots[0][1] if shots else ""

    m = DATESEQ_RE.search(stem)
    if m:  # 已经带日期-序号（例如超分后的同一条），沿用
        date, seq = m[1], int(m[2])
    else:
        date = date_from_name(stem) or birth_date(path).strftime("%y%m%d")
        seq = next_seq(spec["dest"], spec["prefix"], date)

    note = spec.get("note")
    if not note and m:  # 标签没写备注，文件名已是 PV_法天象地_260917-1 这种，就保留原备注
        old = re.match(rf"{re.escape(spec['prefix'])}_(?:C\d{{3}}_)?(.+?)_{m[0]}", stem)
        if old:
            note = old[1]

    parts = [spec["prefix"]]
    if spec["mode"] == "shot" and shot is not None:
        parts.append(f"C{shot:03d}{suffix}")
    if spec["mode"] in ("shot", "asset") and note:
        parts.append(note)  # 段落/备注在日期前：同一段落排在一起，段落内按日期先后
    parts.append(f"{date}-{seq}")
    if ext in VIDEO_EXT:
        tier = video_tier(path)
        if tier:
            parts.append(tier)
    return "_".join(parts) + ext


# ---------- 命令 ----------

def routing_tags(path):
    tags = read_tags(path)
    if not tags:
        return []
    projects = active_projects()
    return [t for t in tags if is_routing_tag(t, projects)]


def cmd_has_route(path):
    return 0 if os.path.exists(path) and routing_tags(path) else 1


def file_hash(path):
    m = hashlib.blake2b()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            m.update(chunk)
    return m.hexdigest()


def project_root(dest):
    """dest 所在的项目文件夹（…/项目/<项目>），找不到就用 dest 本身。"""
    d = dest
    while d.startswith(ROOT + os.sep):
        if os.path.basename(os.path.dirname(d)) == "项目":
            return d
        d = os.path.dirname(d)
    return dest


def find_same(path, root):
    """root 里和 path 内容完全一样的文件，没有返回 None。先比大小再比内容。"""
    if not os.path.isdir(root):
        return None
    size = os.path.getsize(path)
    digest = None
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in fs:
            q = os.path.join(d, f)
            if q == path or f.startswith(".") or os.path.islink(q):
                continue
            try:
                if os.path.getsize(q) != size:
                    continue
                digest = digest or file_hash(path)
                if file_hash(q) == digest:
                    return q
            except OSError:
                continue
    return None


def prune_empty(folder):
    """收件箱里东西被送走后，删掉留下的空文件夹（最多删到日期文件夹，图片/视频/其他 本身不动）。"""
    while folder.startswith(INBOX + os.sep) and os.path.dirname(folder) != INBOX:
        try:
            left = [x for x in os.listdir(folder) if x not in (".DS_Store", "Icon\r")]
        except OSError:
            return
        if left:
            return
        shutil.rmtree(folder, ignore_errors=True)
        log("清空文件夹", folder)
        folder = os.path.dirname(folder)


def in_project_area(path):
    """同步空间里、收件箱以外的地方（项目、资料库……）。"""
    return path.startswith(ROOT + os.sep) and not path.startswith(INBOX + os.sep)


def cmd_route(path):
    tags = routing_tags(path)
    if not tags:
        return 0
    if len(tags) > 1:
        notify("文件没有移动", f"{os.path.basename(path)} 有多个路由标签：{'、'.join(tags)}")
        return 0
    tag = tags[0]
    src_dir = os.path.dirname(path)
    try:
        spec = parse_tag(tag, active_projects())
        multi = len(spec.get("shots") or []) > 1
        same = None if os.path.isdir(path) or multi else find_same(path, project_root(spec["dest"]))
        if same:
            to_trash(path)
            notify("项目里已经有这个文件", f"{os.path.basename(path)} 和 {os.path.relpath(same, ROOT)} 一模一样，已移到废纸篓")
            prune_empty(src_dir)
            return 0
        if os.path.isdir(path):  # 文件夹整体移过去，不改名
            dst = move(path, spec["dest"], action=f"路由[{tag}]")
        elif spec["mode"] == "keep":
            dst = move(path, spec["dest"], action=f"路由[{tag}]")
        elif spec["mode"] == "dated":
            day = birth_date(path).strftime("%y%m%d")
            dst = move(path, os.path.join(spec["dest"], day), action=f"路由[{tag}]")
        else:
            dst = move(path, spec["dest"], build_name(path, spec), action=f"路由[{tag}]")
        remove_tag(dst, tag)
        if multi and uses_team_name(dst, spec):
            shots = spec["shots"]
            if len(shots) == 2:  # 规范：2 个镜头合在一条，复制一份按第二个镜号命名
                twin = unique_path(spec["dest"], team_name(dst, spec, shots[1]))
                shutil.copy2(dst, twin)
                log(f"合镜复制[{tag}]", dst, twin)
            else:  # 3 个及以上：只留母文件，交给剪辑截
                notify("合镜母文件", f"{os.path.basename(dst)} 包含 {'、'.join(shot_str(x) for x in shots)} 镜，记得告诉制片")
        prune_empty(src_dir)
    except RouteError as e:
        notify("文件没有移动", f"{os.path.basename(path)}：{e}")
    return 0


def kind_of(path):
    """收件箱分类：图片 / 视频 / 其他（文件夹一律算其他）。"""
    if os.path.isdir(path):
        return "其他"
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXT:
        return "视频"
    if ext in IMAGE_EXT:
        return "图片"
    return "其他"


def is_junk(name):
    return name.startswith("~$") or name.endswith(".baiduyun.uploading.cfg")


def cmd_sweep(path):
    name = os.path.basename(path)
    if not os.path.exists(path) or name.startswith(".") or name in ("Icon\r",):
        return 0
    if routing_tags(path):  # 等路由规则处理
        return 0
    if is_junk(name):
        to_trash(path)
        return 0
    # 日期文件夹 = 进收件箱那天，7 天后整个文件夹进废纸篓
    day = dt.datetime.now().strftime("%y%m%d")
    move(path, os.path.join(INBOX, kind_of(path), day), action="收件箱")
    return 0


def date_added(path):
    r = subprocess.run(["/usr/bin/mdls", "-raw", "-name", "kMDItemDateAdded", path],
                       capture_output=True, text=True)
    try:
        return dt.datetime.strptime(r.stdout.strip(), "%Y-%m-%d %H:%M:%S %z").astimezone().replace(tzinfo=None)
    except ValueError:
        return None


def idle_days(path):
    """多久没动：取创建、修改、放进这个文件夹三者中最晚的时间。"""
    st = os.stat(path)
    times = [dt.datetime.fromtimestamp(st.st_mtime), birth_date(path)]
    added = date_added(path)
    if added:
        times.append(added)
    return (dt.datetime.now() - max(times)).total_seconds() / 86400


def visible_items(folder):
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, n) for n in sorted(os.listdir(folder))
            if not n.startswith(".") and n != "Icon\r"]


def cmd_tick(_=None):
    """定时任务入口：桌面/下载打了标签的路由、闲置满 SWEEP_DAYS 天的进收件箱；
    收件箱里打了标签的路由、日期文件夹满 INBOX_DAYS 天的进废纸篓。"""
    cfg = load_config()
    sweep_days = cfg.get("sweep_days", 3)
    inbox_days = cfg.get("inbox_days", 7)
    for folder in WATCHED:
        for path in visible_items(folder):
            if routing_tags(path):
                cmd_route(path)
            elif idle_days(path) >= sweep_days:
                cmd_sweep(path)
    expired = 0
    for kind in visible_items(INBOX):
        for day in visible_items(kind):
            for path in visible_items(day):
                if routing_tags(path):
                    cmd_route(path)
            if os.path.isdir(day) and (dt.datetime.now() - birth_date(day)).days >= inbox_days:
                expired += len(visible_items(day))
                move(day, TRASH, f"收件箱_{os.path.basename(kind)}_{os.path.basename(day)}", action="废纸篓")
    if expired:
        notify("收件箱清理", f"{expired} 个放满 {inbox_days} 天的文件已移到废纸篓")
    return 0


def inbox_day_folder(path):
    """收件箱里的日期文件夹（0_收件箱/<类型>/<YYMMDD>）返回 True。"""
    parent = os.path.dirname(path)
    return (os.path.isdir(path) and os.path.dirname(parent) == INBOX
            and re.fullmatch(r"\d{6}", os.path.basename(path)) is not None)


def expired_day(path):
    days = load_config().get("inbox_days", 7)
    return inbox_day_folder(path) and (dt.datetime.now() - birth_date(path)).days >= days


NOTIFIED_XATTR = "com.gerry.filehub.notified"


def route_problem(path):
    """路由标签有问题就返回原因，没问题返回 None。"""
    tags = routing_tags(path)
    if len(tags) > 1:
        return f"有多个路由标签：{'、'.join(tags)}"
    try:
        spec = parse_tag(tags[0], active_projects())
        if not os.path.isdir(path) and uses_team_name(path, spec) and not spec.get("shots"):
            stem = os.path.splitext(os.path.basename(path))[0].strip()
            if not re.fullmatch(r"[Cc]?\d{1,3}[A-Za-z]?", stem):
                return "视频要写镜号，例如「LYX020822」，或把文件名改成镜号"
    except RouteError as e:
        return str(e)
    return None


def notify_once(path, key, title, message):
    """同一个文件、同一个标签只提醒一次（Hazel 每次扫文件夹都会问一遍）。"""
    got = subprocess.run(["/usr/bin/xattr", "-p", NOTIFIED_XATTR, path], capture_output=True, text=True).stdout.strip()
    if got == key:
        return
    notify(title, message)
    subprocess.run(["/usr/bin/xattr", "-w", NOTIFIED_XATTR, key, path], capture_output=True)


def cmd_due(path):
    """给 Hazel 的条件：现在该处理就返回 0。"""
    name = os.path.basename(path)
    if not os.path.exists(path) or name.startswith(".") or name == "Icon\r":
        return 1
    if routing_tags(path):
        problem = route_problem(path)
        if problem:  # 不通过：Hazel 不记成已处理，改对标签后下次扫到就会送走
            notify_once(path, "|".join(routing_tags(path)), "文件没有移动", f"{os.path.basename(path)}：{problem}")
            return 0 if bad_name(path) else 1
        return 0
    if in_project_area(path):  # 项目里：只改网盘不认的名字
        return 0 if bad_name(path) else 1
    if path.startswith(INBOX + os.sep):
        return 0 if expired_day(path) else 1
    if idle_days(path) >= load_config().get("sweep_days", 3):  # 锁文件也等 3 天，Word 开着文档时要用
        return 0
    return 1


def cmd_handle(path):
    """给 Hazel 的动作：有标签就路由；收件箱过期日期文件夹进废纸篓；其余收进收件箱。"""
    if bad_name(path):
        path = fix_name(path)
    if routing_tags(path):
        return cmd_route(path)
    if in_project_area(path):
        return 0
    if path.startswith(INBOX + os.sep):
        if expired_day(path):
            kind = os.path.basename(os.path.dirname(path))
            n = len(visible_items(path))
            move(path, TRASH, f"收件箱_{kind}_{os.path.basename(path)}", action="废纸篓")
            notify("收件箱清理", f"{kind}/{os.path.basename(path)} 的 {n} 个文件已放满 {load_config().get('inbox_days', 7)} 天，移到废纸篓")
        return 0
    if idle_days(path) < load_config().get("sweep_days", 3):  # Hazel 日期规则只负责叫醒，天数以这里为准
        return 0
    return cmd_sweep(path)


def clean_name(path):
    name = os.path.basename(path)
    return safe_name(name + ".d")[:-2] if os.path.isdir(path) else safe_name(name)


def bad_name(path):
    return clean_name(path) != os.path.basename(path)


def fix_name(path):
    return move(path, os.path.dirname(path), clean_name(path), action="改名[网盘]")


def cmd_fixnames(root):
    """把 root 下百度网盘同步不了的文件名、文件夹名一次性改掉（Hazel 平时逐个处理，这个用来补漏）。"""
    n = 0
    for d, dirs, fs in os.walk(root, topdown=False):  # 自底向上，先改里面再改文件夹本身
        if any(part.startswith(".") for part in os.path.relpath(d, root).split(os.sep) if part != "."):
            continue
        for f in fs:
            if f.startswith(".") or f == "Icon\r":
                continue
            new = safe_name(f)
            if new != f:
                move(os.path.join(d, f), d, new, action="改名[网盘]")
                n += 1
        for x in dirs:
            if x.startswith("."):
                continue
            new = safe_name(x + ".d")[:-2]  # 文件夹没有扩展名
            if new != x:
                move(os.path.join(d, x), d, new, action="改名[网盘]")
                n += 1
    if n:
        print(f"改名 {n} 个")
    return 0


def cmd_undo(logfile):
    with open(logfile, encoding="utf-8") as f:
        rows = [line.rstrip("\n").split("\t") for line in f if line.strip()]
    for row in reversed(rows):
        if len(row) < 4 or not row[3]:
            continue
        src, dst = row[2], row[3]
        if os.path.exists(dst) and not os.path.exists(src):
            os.makedirs(os.path.dirname(src), exist_ok=True)
            shutil.move(dst, src)
            print(f"还原 {dst} → {src}")
    # 撤销过的日志改名，避免再执行时追加进同一份、下次撤销混在一起
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.rename(logfile, f"{logfile}.已撤销-{stamp}")
    return 0


def main(argv):
    if len(argv) < 2 or (len(argv) < 3 and argv[1] != "tick"):
        print(__doc__)
        return 2
    cmd, target = argv[1], (argv[2] if len(argv) > 2 else None)
    return {
        "has-route": cmd_has_route,
        "route": cmd_route,
        "sweep": cmd_sweep,
        "undo": cmd_undo,
        "fixnames": cmd_fixnames,
        "tick": cmd_tick,
        "due": cmd_due,
        "handle": cmd_handle,
    }.get(cmd, lambda _: 2)(target)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
