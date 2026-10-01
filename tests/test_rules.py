from datetime import datetime, timezone
from pathlib import Path
import pytest
from filehub.rules import RouteError, build_targets, discover_projects, parse_tag, safe_name

TIME = datetime(2026, 9, 30, 15, tzinfo=timezone.utc)

@pytest.fixture
def project(tmp_path):
    p = tmp_path / '1_工作' / '项目' / '260930_LYX_临渊行'
    for cat, name in [('角色', '苏云'), ('角色', '苏云法相'), ('场景', '庠序')]:
        (p / '1_设定' / cat / name).mkdir(parents=True)
    (p / '3_制作' / '预告').mkdir(parents=True)
    return tmp_path, p

@pytest.mark.parametrize('tag,ext,expected', [
 ('LYX020822','.mp4','02_08_22_01_20260930PM_1080p.mp4'),
 ('LYX020822','.png','E02S08_C022_260930-1.png'),
 ('LYX020815A','.mp4','02_08_15A_01_20260930PM_1080p.mp4'),
 ('LYX0208105','.mp4','02_08_105_01_20260930PM_1080p.mp4'),
 ('LYXE02S08C22白模','.mp4','02_08_22_01_20260930PM_白模_1080p.mp4'),
 ('LYXE01C3','.mp4','E01_C003_260930-1_1080p.mp4'),
 ('LYXPV决战','.mp4','PV_决战_260930-1_1080p.mp4'),
 ('LYXPVC3','.png','PV_C003_260930-1.png'),
 ('LYX正片C20','.mp4','正片_C020_260930-1_1080p.mp4'),
 ('LYX苏云法相','.png','苏云法相_260930-1.png'),
 ('LYX苏云 白模','.png','苏云_白模_260930-1.png'),
 ('LYX破败庠序','.png','庠序_破败_260930-1.png'),
 ('LYX角色劫灰怪','.png','劫灰怪_260930-1.png'),
 ('LYX场景雪林','.png','雪林_260930-1.png'),
 ('LYX道具仙剑','.png','仙剑_260930-1.png'),
 ('LYX成片E01','.mp4','E01_成片_260930-1_1080p.mp4'),
 ('LYX预告C3','.png','预告_C003_260930-1.png'),
])
def test_examples(project, tag, ext, expected):
    root, p = project
    spec = parse_tag(tag, discover_projects(root), root)
    assert build_targets(Path('input'+ext), spec, TIME, 1920, [])[0].name == expected

@pytest.mark.parametrize('width,tier', [(1199,'480p'),(1200,'720p'),(1699,'720p'),(1700,'1080p'),(2999,'1080p'),(3000,'4K')])
def test_tiers(project,width,tier):
    root,p=project
    spec=parse_tag('LYX020822',discover_projects(root),root)
    assert build_targets(Path('x.mp4'),spec,TIME,width,[])[0].stem.endswith(tier)

@pytest.mark.parametrize('tag,count,warnings', [('LYX020815+20',2,0),('LYX020815+16+17',1,1)])
def test_merged(project,tag,count,warnings):
    root,p=project
    spec=parse_tag(tag,discover_projects(root),root)
    result=build_targets(Path('x.mp4'),spec,TIME,1920,[])
    assert len(result)==count
    assert len(result.warnings)==warnings
    assert len(build_targets(Path('x.png'),spec,TIME,None,[]))==1

def test_sequence_and_note(project):
    root,p=project
    spec=parse_tag('LYXPV',discover_projects(root),root)
    assert build_targets(Path('PV_C015A_旧备注_260922-2.PNG'),spec,TIME,None,[])[0].name=='PV_C015A_旧备注_260922-2.png'
    occupied=['OTHER_260930-99.png','PV_260929-9.png','PV_C003_260930-4.png']
    assert build_targets(Path('x.png'),spec,TIME,None,occupied)[0].name=='PV_260930-5.png'
    old='PV_C015A_旧备注_260922-2.png'
    assert build_targets(Path(old),spec,TIME,None,[old])[0].name=='PV_C015A_旧备注_260922-3.png'

def test_team_version_and_inference(project):
    root,p=project
    spec=parse_tag('LYXE02S08',discover_projects(root),root)
    assert build_targets(Path('C15A.mp4'),spec,TIME,1920,['02_08_15A_03_20260101AM_480p.mp4'])[0].name=='02_08_15A_04_20260930PM_1080p.mp4'
    with pytest.raises(RouteError): build_targets(Path('x.mp4'),spec,TIME,1920,[])
    with pytest.raises(RouteError): build_targets(Path('C15A.mp4'),spec,TIME,None,[])

@pytest.mark.parametrize('tag,folder',[('LYX剧本','2_剧本分镜'),('LYX甲方','0_甲方'),('LYX参考','_参考'),('LYX测试','_测试'),('通用测试','技术测试')])
def test_keep_dated(project,tag,folder):
    root,p=project
    spec=parse_tag(tag,discover_projects(root),root)
    target=build_targets(Path('original.PNG'),spec,TIME,None,['original.PNG'])[0]
    assert target.name=='original 2.PNG'
    assert folder in target.parts
    if spec.mode=='dated': assert target.parent.name=='260930'
    d=root/'original folder'; d.mkdir()
    assert build_targets(d,spec,TIME,None,[])[0].parent==spec.dest

def test_sanitation():
    assert safe_name('x|𝟖𝐊😀\u200b\ue001.png')=='x｜8K.png'
    assert safe_name('Ａ①.png')=='Ａ①.png'
    assert safe_name('a'*151+'.png')=='a'*151+'.png'
    for name in ['CON','con.png','x.','x ', 'a'*256, '..']:
        with pytest.raises(RouteError): safe_name(name)

def test_discovery_and_escape(project):
    root,p=project
    ignored=root/'2_资料库'/'项目'/'260930_X_忽略'; ignored.mkdir(parents=True)
    assert list(discover_projects(root))==['LYX']
    spec=parse_tag('LYX角色a/../../b',discover_projects(root),root)
    assert spec.dest.is_relative_to(p)
    assert '／' in spec.dest.name
    with pytest.raises(RouteError): parse_tag('LYX角色CON',discover_projects(root),root)
    dup=root/'3_别处'/'项目'/'260930_lyx_重复'; dup.mkdir(parents=True)
    with pytest.raises(RouteError): discover_projects(root)

def test_longest_code(project):
    root,p=project
    spec=parse_tag('LYXPV',{'LY':root/'short','LYX':p},root)
    assert spec.dest==p/'3_制作'/'PV'

def test_final_ignores_notes(project):
    root,p=project
    spec=parse_tag('LYX成片E01备注',discover_projects(root),root)
    assert build_targets(Path('E01_成片_旧_260922-2.mp4'),spec,TIME,3000,[])[0].name=='E01_成片_260922-2_4K.mp4'

def test_existing_shot_without_note(project):
    root,p=project
    spec=parse_tag('LYXPV',discover_projects(root),root)
    assert build_targets(Path('PV_C015A_260922-2.png'),spec,TIME,None,[])[0].name=='PV_C015A_260922-2.png'

def test_windows_reparse_rejected(project,monkeypatch):
    from types import SimpleNamespace
    root,p=project
    original=Path.lstat
    def lstat(path,*args,**kwargs):
        if path==p: return SimpleNamespace(st_file_attributes=0x400,st_mode=0o040755)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',lstat)
    with pytest.raises(RouteError): discover_projects(root)

def test_manual_traversal_spec(project):
    from filehub.rules import RouteSpec
    root,p=project
    with pytest.raises(RouteError): build_targets(Path('x.png'),RouteSpec('asset',p/'..'/'escape','x'),TIME,None,[])

@pytest.mark.parametrize('tag',['LYX剧本','LYX测试'])
def test_keep_video_needs_no_probe(project,tag):
    root,p=project
    spec=parse_tag(tag,discover_projects(root),root)
    assert build_targets(Path('Original.MP4'),spec,TIME,None,[])[0].name=='Original.MP4'

@pytest.mark.parametrize('tag',['BAD020822','LYX不存在','LYX角色','LYX'])
def test_invalid_tags(project,tag):
    root,p=project
    with pytest.raises(RouteError): parse_tag(tag,discover_projects(root),root)

def test_note_override_and_named_date(project):
    root,p=project
    spec=parse_tag('LYXPVC3新备注',discover_projects(root),root)
    assert build_targets(Path('PV_C003_旧备注_260922-2.PNG'),spec,TIME,None,[])[0].name=='PV_C003_新备注_260922-2.png'
    assert build_targets(Path('2026-09-21.png'),spec,TIME,None,[])[0].name=='PV_C003_新备注_260921-1.png'

def test_project_outside_sync_root(project):
    root,p=project
    with pytest.raises(RouteError): parse_tag('LYXPV',{'LYX':root.parent/'outside'},root)

@pytest.mark.parametrize('tag',['LYX剧本','LYX测试'])
def test_directory_unicode_unchanged(project,tag):
    root,p=project
    source=root/'😀𝟖𝐊素材'; source.mkdir()
    spec=parse_tag(tag,discover_projects(root),root)
    assert build_targets(source,spec,TIME,None,[])[0]==spec.dest/source.name
    assert build_targets(source,spec,TIME,None,[source.name])[0]==spec.dest/(source.name+' 2')

@pytest.mark.parametrize('tag',['LYXE01C3+4','LYXE01C3+4+5'])
def test_episodic_no_scene_not_team_merged(project,tag):
    root,p=project
    result=build_targets(Path('x.mp4'),parse_tag(tag,discover_projects(root),root),TIME,1920,[])
    assert len(result)==1
    assert result.warnings==()
    assert result[0].name=='E01_C003_260930-1_1080p.mp4'

@pytest.mark.parametrize('tag,note',[('LYXPVC3+4','+4'),('LYXPVC3A','A'),('LYX正片C20+30','+30')])
def test_sequence_single_numeric_shot(project,tag,note):
    root,p=project
    spec=parse_tag(tag,discover_projects(root),root)
    assert len(spec.shots)==1
    assert spec.shots[0][1]==''
    assert spec.note==note
    result=build_targets(Path('x.mp4'),spec,TIME,1920,[])
    assert len(result)==1 and result.warnings==()
