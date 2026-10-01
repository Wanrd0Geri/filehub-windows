from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest

from filehub.templates import ProjectTemplate, TemplateLibrary, TemplateStore
from filehub.naming import NAMING_TOKENS, validate_pattern, render_pattern
from filehub.rules import parse_tag, build_targets, discover_projects, RouteError
from filehub.config import Config
from filehub.service import FileHubService, PreviewBatch

TIME = datetime(2026, 9, 30, 15, tzinfo=timezone.utc)


def custom_library():
    default = TemplateLibrary().templates['default']
    template = replace(default, id='custom', name='自定义', production_dir='制作/镜头',
                       asset_root='资产', asset_categories={'怪物': '生物/怪物'},
                       final_dir='交付', keep_name_routes={'剧本': '文本/剧本'},
                       test_dir='测试', naming_patterns={'asset': '{prefix}_{date}_{sequence}{ext}',
                                                       'shot': '{prefix}_{shot}_{sequence}{ext}'})
    return TemplateLibrary().with_template(template).assign('lyx', 'custom')


def test_missing_store_lazy_default_and_immutable(tmp_path):
    state = tmp_path/'state'
    library = TemplateStore(state).load()
    assert not state.exists()
    assert library.for_project('LYX').production_dir == '3_制作'
    assert library.revision == TemplateLibrary().revision
    with pytest.raises(TypeError): library.templates['default'].asset_categories['怪物'] = '怪物'
    with pytest.raises(ValueError): library.with_template(replace(library.templates['default'], name='改默认'))
    copied = library.copy_template('default', 'copy', '副本')
    assert copied.templates['copy'].production_dir == '3_制作'


def test_custom_roundtrip_and_routing(tmp_path):
    root = tmp_path/'sync'
    project = root/'1_工作'/'项目'/'260930_LYX_测试'
    (project/'资产'/'生物'/'怪物'/'龙').mkdir(parents=True)
    store = TemplateStore(tmp_path/'state')
    saved = store.save(custom_library())
    loaded = TemplateStore(store.state_dir).load()
    assert loaded == saved
    assert loaded.for_project('LyX').id == 'custom'
    projects = discover_projects(root)
    assert parse_tag('LYXE02S08C22', projects, root, loaded).dest == project/'制作'/'镜头'/'E02'/'S08'
    assert parse_tag('LYX怪物龙', projects, root, loaded).dest == project/'资产'/'生物'/'怪物'/'龙'
    assert parse_tag('LYX龙', projects, root, loaded).mode == 'asset'
    assert parse_tag('LYX剧本', projects, root, loaded).dest == project/'文本'/'剧本'
    assert parse_tag('LYX成片E01', projects, root, loaded).dest == project/'交付'
    assert parse_tag('LYX测试', projects, root, loaded).dest == project/'测试'


@pytest.mark.parametrize('change', ['version', 'duplicate', 'assignment', 'unknown_field', 'default'])
def test_invalid_document_not_silently_reset(tmp_path, change):
    store = TemplateStore(tmp_path/'state')
    library = store.save(custom_library())
    doc = library.to_document()
    if change == 'version': doc['version'] = 2
    if change == 'duplicate': doc['templates'].append(doc['templates'][1])
    if change == 'assignment': doc['assignments']['BAD'] = 'missing'
    if change == 'unknown_field': doc['templates'][1]['surprise'] = 1
    if change == 'default': next(row for row in doc['templates'] if row['id'] == 'default')['production_dir'] = '别处'
    store.path.write_text(json.dumps(doc), encoding='utf-8')
    before = store.path.read_bytes()
    with pytest.raises(ValueError): store.load()
    assert store.path.read_bytes() == before


def test_assigned_delete_and_optimistic_save(tmp_path):
    store = TemplateStore(tmp_path/'state')
    saved = store.save(custom_library())
    with pytest.raises(ValueError): saved.delete_template('custom')
    with pytest.raises(ValueError): saved.delete_template('default')
    changed = store.save(saved.assign('LYX', 'default'), expected_revision=saved.revision)
    with pytest.raises(ValueError, match='重新'): store.save(saved, expected_revision=saved.revision)
    assert store.load() == changed
    store.save(changed.delete_template('custom'))


@pytest.mark.parametrize('bad', ['../escape', '/absolute', 'C:\\escape', 'safe/../escape', 'safe//x', 'CON', 'safe/NUL.png', 'bad\x00', 'folder.', 'folder '])
def test_unsafe_paths_preserve_saved_document(tmp_path, bad):
    store = TemplateStore(tmp_path/'state')
    saved = store.save(custom_library())
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.save(saved.with_template(replace(saved.templates['custom'], production_dir=bad)))
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('bad', ['{unknown}', '{stem.__class__}', '{sequence:02d}', '{stem[0]}', '../{stem}', 'CON{ext}', '{stem}/a', 'a|b', '{stem!r}', '{'])
def test_unsafe_patterns_rejected(bad):
    with pytest.raises(ValueError): validate_pattern(bad, NAMING_TOKENS)


def test_renderer_strict_single_component_and_optional_values():
    assert render_pattern('{stem}_{note}_{sequence}{ext}', {'stem': '源', 'sequence': 3, 'ext': '.PNG'}) == '源__3.PNG'
    assert render_pattern('{original}', {'original': 'A.PNG'}) == 'A.PNG'
    for stem in ['CON', 'con .png', 'CONIN$.txt', 'CONOUT$', '../x', 'a\x00', 'a.', 'a'*256]:
        with pytest.raises(ValueError): render_pattern('{stem}', {'stem': stem})


def test_custom_sequence_collision_and_directory_keep_name(tmp_path):
    library = custom_library()
    project = tmp_path/'project'; project.mkdir()
    spec = parse_tag('LYX怪物龙', {'LYX': project}, tmp_path, library)
    result = build_targets(tmp_path/'input.PNG', spec, TIME, None, ['龙_260930_1.PNG', '龙_260930_2.png'])
    assert result[0].name == '龙_260930_3.png'
    no_sequence = replace(spec, naming_pattern='{original}')
    with pytest.raises(RouteError, match='冲突'): build_targets(tmp_path/'input.PNG', no_sequence, TIME, None, ['input.PNG'])
    source = tmp_path/'😀素材'; source.mkdir()
    assert build_targets(source, spec, TIME, None, [])[0].name == '😀素材'


@pytest.mark.parametrize('tag,name', [('LYX020822', '02_08_22_01_20260930PM_1080p.mp4'), ('LYX成片E01', 'E01_成片_260930-1_1080p.mp4')])
def test_default_template_legacy_names(tmp_path, tag, name):
    spec = parse_tag(tag, {'LYX': tmp_path/'project'}, tmp_path, TemplateLibrary())
    assert build_targets(tmp_path/'input.mp4', spec, TIME, 1920, [])[0].name == name


def test_preview_external_template_edit_rejected_before_mutation(tmp_path):
    root = tmp_path/'sync'; project = root/'1_工作'/'项目'/'260930_LYX_测试'; project.mkdir(parents=True)
    service = FileHubService(Config(sync_root=root), tmp_path/'state', source_time=lambda p: TIME)
    source = tmp_path/'input.png'; source.write_bytes(b'image')
    preview = service.preview([source], 'LYX角色龙')
    assert preview.template_revision
    TemplateStore(service.engine.state_dir).save(custom_library())
    result = service.execute(preview)
    assert source.read_bytes() == b'image' and not result.items
    assert '重新预览' in result.outcomes[0].error
    assert not (project/'1_设定').exists()
    assert service.reload_templates().for_project('LYX').id == 'custom'


def test_normal_demo_and_old_positional_batch(tmp_path):
    normal = TemplateStore(tmp_path/'normal'); demo = TemplateStore(tmp_path/'demo')
    normal.save(custom_library())
    assert demo.load().for_project('LYX').id == 'default' and not demo.state_dir.exists()
    assert PreviewBatch('tag', ()).template_revision == ''


def test_atomic_replace_failure_keeps_previous(tmp_path, monkeypatch):
    import filehub.templates as module
    store = TemplateStore(tmp_path/'state'); original = store.save(TemplateLibrary())
    monkeypatch.setattr(module.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('disk failure')))
    with pytest.raises(OSError): store.save(custom_library())
    assert store.load() == original and not list(store.state_dir.glob('.templates-*'))


def test_category_longest_prefix_and_keep_route_exact(tmp_path):
    template = ProjectTemplate('custom', '自定义', asset_categories={'角色': '人', '角色设计': '设计'},
                               keep_name_routes={'剧本': '剧本', '剧本设计': '设计文档'})
    library = TemplateLibrary().with_template(template).assign('LYX', 'custom')
    spec = parse_tag('LYX角色设计苏云', {'LYX': tmp_path/'project'}, tmp_path, library)
    assert spec.dest == tmp_path/'project'/'1_设定'/'设计'/'苏云'
    assert parse_tag('LYX剧本设计', {'LYX': tmp_path/'project'}, tmp_path, library).dest == tmp_path/'project'/'设计文档'


@pytest.mark.parametrize('keyword', ['成片', 'PV', 'PV预告', '正片', 'E02', '0208', '测试', '角色'])
def test_keyword_conflicts_rejected(keyword):
    with pytest.raises(ValueError):
        ProjectTemplate('custom', '自定义', keep_name_routes={keyword: '文档'})


def test_ext_only_pattern_and_caller_token_whitelist():
    assert validate_pattern('{ext}', NAMING_TOKENS) == '{ext}'
    assert render_pattern('{ext}', {'ext': '.png'}) == '.png'
    with pytest.raises(ValueError): validate_pattern('{date}', {'stem', 'ext'})


def test_pattern_validation_save_is_atomic(tmp_path):
    store = TemplateStore(tmp_path/'state'); saved = store.save(custom_library())
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.save(saved.with_template(replace(saved.templates['custom'], naming_patterns={'asset': '{stem.__class__}'})))
    assert store.path.read_bytes() == before


def test_canonical_digest_and_assigned_delete_cannot_bypass_store(tmp_path):
    store = TemplateStore(tmp_path/'state'); saved = store.save(custom_library())
    doc = saved.to_document(); doc['templates'].reverse()
    assert TemplateLibrary.from_document(doc).revision == saved.revision
    replacement = saved.assign('LYX', None).delete_template('custom')
    with pytest.raises(ValueError, match='分配'): store.save(replacement)
    assert store.load() == saved


def test_custom_tokens_no_legacy_team_requirement(tmp_path):
    library = custom_library()
    template = replace(library.templates['custom'], naming_patterns={'shot': '{episode}_{scene}_{shot}_{date_long}{period}_{resolution}_{sequence}{ext}'})
    library = library.with_template(template)
    spec = parse_tag('LYXE02S08', {'LYX': tmp_path/'project'}, tmp_path, library)
    assert build_targets(tmp_path/'x.mp4', spec, TIME, 1920, [])[0].name == '2_8__20260930PM_1080p_1.mp4'
    with pytest.raises(RouteError, match='宽度'): build_targets(tmp_path/'x.mp4', spec, TIME, None, [])


def test_preview_reserves_custom_names_and_executes_snapshot(tmp_path):
    root = tmp_path/'sync'; project = root/'1_工作'/'项目'/'260930_LYX_测试'; project.mkdir(parents=True)
    service = FileHubService(Config(sync_root=root), tmp_path/'state', source_time=lambda p: TIME)
    service.templates.save(custom_library())
    assert service._route('LYX怪物龙')[0].dest == project/'资产'/'生物'/'怪物'/'龙'
    a, b = tmp_path/'a.PNG', tmp_path/'b.png'; a.write_bytes(b'one'); b.write_bytes(b'two')
    preview = service.preview([a, b], 'LYX怪物龙')
    assert [i.targets[0].name for i in preview.items] == ['龙_260930_1.png', '龙_260930_2.png']
    result = service.execute(preview)
    assert result.ok and not a.exists() and not b.exists()
    assert [o.targets for o in result.outcomes] == [i.targets for i in preview.items]


def test_legacy_positional_preview_rejected_with_custom_library(tmp_path):
    root = tmp_path/'sync'; project = root/'1_工作'/'项目'/'260930_LYX_测试'; project.mkdir(parents=True)
    service = FileHubService(Config(sync_root=root), tmp_path/'state', source_time=lambda p: TIME)
    source = tmp_path/'input.png'; source.write_bytes(b'image')
    preview = service.preview([source], 'LYX角色龙')
    service.templates.save(custom_library())
    result = service.execute(PreviewBatch(preview.tag, preview.items))
    assert source.exists() and not result.items and '重新预览' in result.outcomes[0].error


def test_malformed_json_blocks_save_without_reset(tmp_path):
    store = TemplateStore(tmp_path/'state'); store.save(TemplateLibrary())
    store.path.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError): store.load()
    with pytest.raises(ValueError): store.save(custom_library())
    assert store.path.read_text(encoding='utf-8') == '{broken'


def test_template_store_rechecks_reparse_parent_without_write(tmp_path, monkeypatch):
    from types import SimpleNamespace
    state = tmp_path/'state'; store = TemplateStore(state)
    state.mkdir()
    original = Path.lstat
    def lstat(path, *args, **kwargs):
        if path == state: return SimpleNamespace(st_file_attributes=0x400, st_mode=0o040755)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', lstat)
    with pytest.raises(ValueError): store.load()
    with pytest.raises(ValueError): store.save(custom_library())
    assert not store.path.exists() and not (state/'engine.lock').exists()


def test_store_rejects_reparse_lock_file(tmp_path, monkeypatch):
    from types import SimpleNamespace
    store = TemplateStore(tmp_path/'state'); store.save(TemplateLibrary())
    original = Path.lstat; before = store.path.read_bytes()
    def lstat(path, *args, **kwargs):
        if path == store.state_dir/'engine.lock': return SimpleNamespace(st_file_attributes=0x400, st_mode=0o100644)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', lstat)
    with pytest.raises(ValueError): store.load()
    with pytest.raises(ValueError): store.save(custom_library())
    assert store.path.read_bytes() == before
