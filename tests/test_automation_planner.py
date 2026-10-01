from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from filehub.automation.models import Action, Predicate, Rule
from filehub.automation.conditions import FileFacts
from filehub.automation.planner import PlanReservations, plan_rule
from filehub.models import Fingerprint
from filehub.templates import TemplateLibrary

NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def setup(tmp_path, name='a.png', kind='image'):
    source = tmp_path/name
    source.mkdir() if kind == 'folder' else source.write_bytes(b'original')
    fp = Fingerprint.capture(source)
    facts = FileFacts(source, fp, kind=kind, size_bytes=fp.size, created=NOW, modified=NOW)
    service = SimpleNamespace(engine=SimpleNamespace(state_dir=tmp_path/'state'),
        config=SimpleNamespace(sync_root=None, watch_roots=(tmp_path,)), reload_templates=lambda: TemplateLibrary())
    return source, facts, service


def make_rule(*actions):
    return Rule(condition=Predicate('name', 'glob', '*'), actions=actions)


def test_ordered_rename_copy_move_subject_and_readonly(tmp_path):
    source, facts, service = setup(tmp_path)
    r = make_rule(Action('rename', {'pattern': 'b{ext}'}),
                  Action('copy', {'destination': str(tmp_path/'copies')}),
                  Action('move', {'destination': str(tmp_path/'final')}))
    plan = plan_rule(r, facts, service, now=NOW, ruleset_revision='whole')
    assert not plan.errors
    assert [(s.kind, s.source, s.target) for s in plan.steps] == [
        ('move', source, tmp_path/'b.png'), ('copy', tmp_path/'b.png', tmp_path/'copies'/'b.png'),
        ('move', tmp_path/'copies'/'b.png', tmp_path/'final'/'b.png')]
    assert plan.steps[0].source_fingerprint == facts.fingerprint
    assert plan.steps[1].source_fingerprint is None
    assert plan.ruleset_revision == 'whole' and plan.template_revision == TemplateLibrary().revision
    assert source.read_bytes() == b'original'
    assert not (tmp_path/'copies').exists() and not (tmp_path/'final').exists()


def test_subfolder_relative_current_parent_and_folder_keep_name(tmp_path):
    source, facts, service = setup(tmp_path, '项目', 'folder')
    plan = plan_rule(make_rule(Action('subfolder', {'path': '归档/完成'})), facts, service, now=NOW)
    assert not plan.errors
    assert plan.steps[0].target == tmp_path/'归档'/'完成'/'项目'
    bad = plan_rule(make_rule(Action('move', {'destination': str(source/'inside')})), facts, service, now=NOW)
    assert bad.errors and not (source/'inside').exists()


@pytest.mark.parametrize('action', ['noop', 'exists', 'case_exists', 'state', 'selected'])
def test_reject_collisions_noop_state_selected_overlap(tmp_path, action):
    source, facts, service = setup(tmp_path)
    options = {'pattern': 'a{ext}' if action == 'noop' else 'b{ext}'}
    a = Action('rename', options)
    reservations = PlanReservations(selected_sources=(source, tmp_path/'b.png') if action == 'selected' else (source,))
    if action == 'exists': (tmp_path/'b.png').write_bytes(b'occupied')
    if action == 'case_exists': (tmp_path/'B.PNG').write_bytes(b'occupied')
    if action == 'state': a = Action('copy', {'destination': str(service.engine.state_dir)})
    plan = plan_rule(make_rule(a), facts, service, occupied=reservations, now=NOW)
    assert plan.errors and not plan.steps
    assert source.read_bytes() == b'original'


def test_batch_reservation_casefold_and_failure_does_not_consume_targets(tmp_path):
    source, facts, service = setup(tmp_path)
    other, other_facts, _ = setup(tmp_path, 'other.png')
    r = make_rule(Action('copy', {'destination': str(tmp_path/'out')}), Action('rename', {'pattern': 'done.PNG'}))
    reservation = PlanReservations(selected_sources=(source, other))
    first = plan_rule(r, facts, service, occupied=reservation, now=NOW)
    assert not first.errors
    second = plan_rule(r, other_facts, service, occupied=reservation, now=NOW)
    assert second.errors
    retry = plan_rule(make_rule(Action('copy', {'destination': str(tmp_path/'out')})), other_facts, service,
                      occupied=reservation, now=NOW)
    assert not retry.errors


@pytest.mark.parametrize('mode,format,name,target', [
    ('keep', 'webp', 'a.png', 'out/a.webp'), ('replace', 'png', 'a.png', 'a.png'),
    ('replace', 'jpeg', 'a.png', 'a.jpg'), ('replace', 'jpeg', 'A.JPG', 'A.jpg')])
def test_conversion_subject_replace_binding_and_unknown_fingerprint(tmp_path, mode, format, name, target):
    source, facts, service = setup(tmp_path, name)
    options = {'mode': mode, 'output_format': format}
    if mode == 'keep': options['destination'] = str(tmp_path/'out')
    r = make_rule(Action('image_convert', options), Action('rename', {'pattern': '{stem}_done{ext}'}))
    plan = plan_rule(r, facts, service, now=NOW)
    assert not plan.errors
    step = plan.steps[0]
    assert step.kind == 'image_convert' and step.target == tmp_path/target
    assert step.replaces_original is (mode == 'replace')
    assert step.requires_backup is (mode == 'replace')
    assert step.generates_content and step.source_fingerprint == facts.fingerprint
    assert plan.steps[1].source == tmp_path/target and plan.steps[1].source_fingerprint is None
    assert plan.steps[1].target.suffix == ('.webp' if format == 'webp' else '.jpg' if format == 'jpeg' else '.png')
    assert source.read_bytes() == b'original'


def test_replace_other_selected_source_and_keep_same_path_numbered(tmp_path):
    source, facts, service = setup(tmp_path)
    other = tmp_path/'a.jpg'
    reservations = PlanReservations(selected_sources=(source, other))
    replace = plan_rule(make_rule(Action('image_convert', {'mode': 'replace', 'output_format': 'jpeg'})),
                        facts, service, occupied=reservations, now=NOW)
    assert not replace.errors and replace.steps[0].target == tmp_path/'a-1.jpg'
    keep = plan_rule(make_rule(Action('image_convert', {'output_format': 'png', 'destination': str(tmp_path)})),
                     facts, service, now=NOW)
    assert not keep.errors and keep.steps[0].target == tmp_path/'a-1.png'


def test_project_route_requires_sync_only_for_project_action(tmp_path):
    _, facts, service = setup(tmp_path)
    basic = plan_rule(make_rule(Action('rename', {'pattern': 'done{ext}'})), facts, service, now=NOW)
    assert not basic.errors
    routed = plan_rule(make_rule(Action('project_route', {'tag': 'LYX参考'})), facts, service, now=NOW)
    assert routed.errors and '同步' in routed.errors[0]


@pytest.mark.parametrize('custom,folder', [(False, False), (True, False), (True, True)])
def test_project_route_template_terminal_with_virtual_subject(tmp_path, custom, folder):
    from dataclasses import replace
    source, facts, service = setup(tmp_path, '项目' if folder else 'a.png', 'folder' if folder else 'image')
    root = tmp_path/'sync'
    project = root/'1_工作'/'项目'/'261001_LYX_测试'
    project.mkdir(parents=True)
    service.config.sync_root = root
    library = TemplateLibrary()
    if custom:
        template = replace(library.templates['default'], id='custom', name='定制',
            asset_root='资产', naming_patterns={'asset': '{prefix}_{date}_{sequence}{ext}'})
        library = library.with_template(template).assign('LYX', 'custom')
    service.reload_templates = lambda: library
    r = make_rule(Action('rename', {'pattern': '新版{ext}'}), Action('project_route', {'tag': 'LYX角色龙'}))
    planned = plan_rule(r, facts, service, now=NOW, templates=library)
    assert not planned.errors
    expected_name = '新版' if folder else '龙_261001_1.png' if custom else '龙_261001-1.png'
    assert planned.steps[-1].source == source.parent/('新版' if folder else '新版.png')
    assert planned.steps[-1].target == project/('资产' if custom else '1_设定')/'角色'/'龙'/expected_name
    assert planned.template_revision == library.revision
    assert not planned.steps[-1].target.parent.exists()


def test_sequence_allocation_includes_batch_targets(tmp_path):
    source, facts, service = setup(tmp_path)
    other, other_facts, _ = setup(tmp_path, 'other.png')
    (tmp_path/'output_1.png').write_bytes(b'exists')
    reservations = PlanReservations((source, other))
    r = make_rule(Action('rename', {'pattern': 'output_{sequence}{ext}'}))
    assert plan_rule(r, facts, service, occupied=reservations, now=NOW).steps[0].target.name == 'output_2.png'
    assert plan_rule(r, other_facts, service, occupied=reservations, now=NOW).steps[0].target.name == 'output_3.png'


def test_replace_virtual_subject_and_unrelated_case_collision(tmp_path):
    _, facts, service = setup(tmp_path)
    r = make_rule(Action('rename', {'pattern': 'renamed{ext}'}),
        Action('image_convert', {'mode': 'replace', 'output_format': 'png'}),
        Action('copy', {'destination': str(tmp_path/'out')}))
    plan = plan_rule(r, facts, service, now=NOW)
    assert not plan.errors and plan.steps[1].source == plan.steps[1].target
    assert plan.steps[1].source_fingerprint is None and plan.steps[1].requires_backup
    (tmp_path/'A.JPG').write_bytes(b'other')
    bad = plan_rule(make_rule(Action('image_convert', {'mode': 'replace', 'output_format': 'jpeg'})), facts, service, now=NOW)
    assert not bad.errors and bad.steps[0].target == tmp_path/'a-1.jpg'
    assert (tmp_path/'A.JPG').read_bytes() == b'other'


def test_conversion_numbering_reserves_selected_and_batch_intermediate(tmp_path):
    source, facts, service = setup(tmp_path, 'a.jpg')
    other, other_facts, _ = setup(tmp_path, 'a.png')
    reservations = PlanReservations((source, other))
    r = make_rule(Action('image_convert', {'mode': 'replace', 'output_format': 'webp'}),
                  Action('image_convert', {'mode': 'replace', 'output_format': 'png'}))
    first = plan_rule(r, facts, service, occupied=reservations, now=NOW)
    assert not first.errors
    assert [s.target.name for s in first.steps] == ['a.webp', 'a-1.png']
    second = plan_rule(make_rule(Action('image_convert', {'mode': 'replace', 'output_format': 'webp'})),
                       other_facts, service, occupied=reservations, now=NOW)
    assert not second.errors and second.steps[0].target.name == 'a-1.webp'
    assert first.steps[1].source == first.steps[0].target


def test_failed_numbered_plan_does_not_leak_reservations(tmp_path):
    source, facts, service = setup(tmp_path)
    (tmp_path/'a.jpg').write_bytes(b'occupied')
    reservations = PlanReservations((source,))
    conversion = Action('image_convert', {'mode': 'replace', 'output_format': 'jpeg'})
    bad = plan_rule(make_rule(conversion, Action('rename', {'pattern': '{original}'})),
                    facts, service, occupied=reservations, now=NOW)
    assert bad.errors and not reservations.targets
    good = plan_rule(make_rule(conversion), facts, service, occupied=reservations, now=NOW)
    assert good.ok and good.steps[0].target == tmp_path/'a-1.jpg'


def test_injected_inspection_plan_binds_source_fingerprint_and_spec(tmp_path):
    from dataclasses import replace
    from filehub.conversion.models import ConversionPlan
    source, facts, service = setup(tmp_path)
    action = Action('image_convert', {'mode': 'replace', 'output_format': 'webp'})
    inspected = ConversionPlan(source, action.conversion_spec, facts.fingerprint, 'png', 1, 1, False, 'capabilities', ())
    good = plan_rule(make_rule(action), facts, service, now=NOW, conversion_plans={0: inspected})
    assert not good.errors and not good.steps[0].requires_conversion_validation
    assert good.steps[0].conversion_plan is inspected
    bad = plan_rule(make_rule(action), facts, service, now=NOW, conversion_plans={0: replace(inspected, source=tmp_path/'other')})
    assert bad.errors


def test_reparse_destination_parent_rejected_without_writes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import stat
    source, facts, service = setup(tmp_path)
    destination = tmp_path/'junction'
    lstat = Path.lstat
    def reparse(self, *args, **kwargs):
        if self == destination: return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return lstat(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', reparse)
    plan = plan_rule(make_rule(Action('copy', {'destination': str(destination)})), facts, service, now=NOW)
    assert plan.errors and not destination.exists()
    assert source.read_bytes() == b'original'


def test_folder_cannot_masquerade_as_file_conversion(tmp_path):
    source, facts, service = setup(tmp_path, 'folder', 'folder')
    disguised = FileFacts(source, facts.fingerprint, kind='image', created=NOW, modified=NOW)
    plan = plan_rule(make_rule(Action('image_convert', {'mode': 'replace', 'output_format': 'png'})), disguised, service, now=NOW)
    assert plan.errors


def test_terminal_project_route_multi_target_copy_does_not_advance_subject(tmp_path):
    from dataclasses import replace
    source, facts, service = setup(tmp_path, 'a.mp4', 'video')
    facts = replace(facts, video_width=1920)
    root = tmp_path/'sync'
    project = root/'1_工作'/'项目'/'261001_LYX_测试'
    project.mkdir(parents=True)
    service.config.sync_root = root
    plan = plan_rule(make_rule(Action('project_route', {'tag': 'LYXE02S08C22+23'})), facts, service, now=NOW)
    assert not plan.errors
    assert [step.kind for step in plan.steps] == ['copy', 'move']
    assert plan.steps[0].source == plan.steps[1].source == source
    assert not plan.steps[0].advances_subject and plan.steps[1].advances_subject
    assert plan.steps[0].target.name == '02_08_23_01_20261001PM_1080p.mp4'
    assert plan.steps[1].target.name == '02_08_22_01_20261001PM_1080p.mp4'


def test_replacement_does_not_bypass_duplicate_selected_input(tmp_path):
    source, facts, service = setup(tmp_path)
    reservations = PlanReservations((source, Path(str(source).upper())))
    r = make_rule(Action('image_convert', {'mode': 'replace', 'output_format': 'png'}))
    plan = plan_rule(r, facts, service, occupied=reservations, now=NOW)
    assert plan.errors and not reservations.targets
