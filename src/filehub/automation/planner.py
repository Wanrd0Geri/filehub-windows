"""Read-only ordered plans. No codec decoding or filesystem publication."""
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import os

from ..conversion.models import ConversionPlan, ConversionSpec
from ..conversion.naming import allocate_conversion_target
from ..models import checked_path
from ..naming import render_pattern, validate_component
from ..rules import build_targets, discover_projects, parse_tag
from ..templates import TemplateLibrary
from .conditions import FileFacts, MatchExplanation, evaluate
from .models import Rule, aware_date


def path_key(path):
    return str(Path(os.path.abspath(path))).casefold()


def paths_overlap(first, second):
    a, b = path_key(first), path_key(second)
    return a == b or a.startswith(b.rstrip('\\/')+os.sep) or b.startswith(a.rstrip('\\/')+os.sep)


@dataclass
class PlanReservations:
    """One shared instance for a batch, seeded with ALL selected input paths.

    Reservations only commit when the complete plan is valid. Conservative
    reservations include intermediate outputs even when a later step moves one.
    """
    selected_sources: tuple[Path, ...] = ()
    targets: set[Path] = field(default_factory=set)

    def __post_init__(self):
        self.selected_sources = tuple(Path(os.path.abspath(path)) for path in self.selected_sources)
        self.targets = {Path(os.path.abspath(path)) for path in self.targets}


@dataclass(frozen=True)
class PlannedStep:
    kind: str
    source: Path
    target: Path
    source_fingerprint: object | None = None
    subject_version: int = 0
    action_index: int = 0
    conversion_spec: ConversionSpec | None = None
    conversion_plan: ConversionPlan | None = None
    generates_content: bool = False
    replaces_original: bool = False
    requires_backup: bool = False
    requires_conversion_validation: bool = False
    explanation: str = ''
    advances_subject: bool = True


@dataclass(frozen=True)
class RulePlan:
    original_path: Path
    original_fingerprint: object | None
    rule_id: str
    rule_revision: str
    ruleset_revision: str
    template_revision: str
    captured_at: datetime
    steps: tuple[PlannedStep, ...] = ()
    explanation: MatchExplanation | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self): return bool(self.steps) and not self.errors


def _existing_collision(target):
    if target.exists(): return True
    if target.parent.is_dir():
        return any(path.name.casefold() == target.name.casefold() for path in target.parent.iterdir())
    return False


def _names_in(folder, reservations, local):
    names = [path.name for path in folder.iterdir()] if folder.is_dir() else []
    names.extend(path.name for path in (*reservations.targets, *local) if path_key(path.parent) == path_key(folder))
    return names


def _tokens(current, facts):
    when = facts.created
    return {'original': current.name, 'stem': current.stem, 'ext': '' if facts.kind == 'folder' else current.suffix.casefold(),
            'date': when.strftime('%y%m%d') if when else '', 'date_long': when.strftime('%Y%m%d') if when else '',
            'period': ('AM' if when.hour < 12 else 'PM') if when else '', 'sequence': 1}


def plan_rule(rule: Rule, facts: FileFacts, service, occupied=None, *, ruleset_revision='',
              templates: TemplateLibrary | None = None, now=None, conversion_plans: Mapping | None = None) -> RulePlan:
    """Bind exact targets without creating folders, history, jobs or codec work.

    A runner must supply the FULL RuleSet revision, all selected input paths,
    one TemplateLibrary snapshot and one aware clock for the whole preview.
    conversion_plans is optional action-index→already-inspected ConversionPlan;
    absent plans remain explicitly pending independent conversion-worker checks.
    After every material action the runner captures the actual subject anew.
    """
    now = datetime.now(timezone.utc) if now is None else aware_date(now)
    reservations = occupied if occupied is not None else PlanReservations((facts.path,))
    if not isinstance(reservations, PlanReservations): raise ValueError('批次占用信息必须是 PlanReservations')
    original = Path(os.path.abspath(facts.path))
    steps, warnings, local = [], [], []
    template_revision = ''
    explanation = evaluate(rule.condition, facts, now)
    try:
        library = service.reload_templates() if templates is None else templates
        if not isinstance(library, TemplateLibrary): raise ValueError('缺少有效模板快照')
        template_revision = library.revision
        checked_path(original)
        state = checked_path(service.engine.state_dir)
        if paths_overlap(original, state): raise ValueError('不能操作应用状态目录')
        if facts.fingerprint is None: raise ValueError('缺少源指纹，请重新预览')
        if not original.exists(): raise ValueError('源不存在，请重新预览')
        if (facts.kind == 'folder') != original.is_dir(): raise ValueError('目录或文件类型与预览不一致')
        if sum(path_key(original) == path_key(other) for other in reservations.selected_sources) > 1:
            raise ValueError('同一个源被重复选择；替换例外不能覆盖其他输入')
        if any(paths_overlap(original, other) and path_key(original) != path_key(other) for other in reservations.selected_sources):
            raise ValueError('选择的源路径互相包含或重叠')
        configured = {path_key(path) for path in service.config.watch_roots}
        if {path_key(path) for path in rule.scope} - configured: raise ValueError('规则引用未配置的观察目录')
        if not explanation.matched: raise ValueError('样本未满足规则条件；不可用的信息也不会匹配')
        current, fingerprint, version = original, facts.fingerprint, 0

        def validate_target(target, *, same_source=False):
            target = checked_path(target)
            validate_component(target.name)
            if paths_overlap(target, state): raise ValueError('目标与应用状态目录重叠')
            own_same = same_source and path_key(target) == path_key(current)
            if path_key(target) == path_key(current) and not own_same: raise ValueError('源与目标相同，不能执行无变化操作')
            if paths_overlap(target, current) and not own_same: raise ValueError('源与目标互相包含或重叠')
            for selected in (*reservations.selected_sources, original):
                if paths_overlap(target, selected):
                    if own_same and path_key(selected) == path_key(current) == path_key(original): continue
                    raise ValueError('目标与选择的源路径重叠')
            if any(paths_overlap(target, prior) for prior in reservations.targets): raise ValueError('目标与本批次其他计划重叠')
            if any(paths_overlap(target, prior) and not (own_same and path_key(prior) == path_key(current)) for prior in local):
                raise ValueError('目标与前面的计划路径重叠')
            if _existing_collision(target) and not (own_same and path_key(current) == path_key(original)):
                raise ValueError('目标已存在，不能覆盖')
            return target

        def add(kind, target, index, *, conversion_spec=None, inspected=None, replacement=False, detail=''):
            nonlocal current, fingerprint, version
            target = validate_target(target, same_source=replacement)
            steps.append(PlannedStep(kind, current, target, fingerprint, version, index,
                conversion_spec, inspected, conversion_spec is not None, replacement, replacement,
                conversion_spec is not None and inspected is None, detail or f'{current} → {target}'))
            local.append(target)
            current, fingerprint, version = target, None, version+1

        for index, action in enumerate(rule.actions):
            options = action.options
            if action.kind == 'rename':
                pattern = options['pattern']
                values = _tokens(current, facts)
                target = current.parent/render_pattern(pattern, values)
                if '{sequence}' in pattern:
                    while _existing_collision(target) or any(path_key(target) == path_key(path) for path in (*reservations.targets, *local)):
                        values['sequence'] += 1
                        target = current.parent/render_pattern(pattern, values)
                add('move', target, index, detail='重命名当前对象')
            elif action.kind in {'move', 'copy', 'subfolder'}:
                folder = Path(options['destination']) if action.kind != 'subfolder' else current.parent/Path(options['path'])
                add('copy' if action.kind == 'copy' else 'move', folder/current.name, index,
                    detail='复制后以副本继续后续动作' if action.kind == 'copy' else '移动当前对象')
            elif action.kind == 'image_convert':
                if facts.kind == 'folder': raise ValueError('图片转换不支持目录')
                spec = action.conversion_spec
                replacement = options['mode'] == 'replace'
                folder = current.parent if replacement else Path(options['destination'])
                target = folder/(current.stem+spec.extension)
                own = replacement and path_key(target) == path_key(current)
                reserved = [path for path in reservations.selected_sources
                            if not (own and path_key(path) == path_key(current) == path_key(original))]
                reserved.extend(reservations.targets)
                reserved.extend(path for path in local if not (own and path_key(path) == path_key(current)))
                target = allocate_conversion_target(target, reserved=reserved, own_source=current if own else None)
                inspected = (conversion_plans or {}).get(index)
                if inspected is not None:
                    if not isinstance(inspected, ConversionPlan) or path_key(inspected.source) != path_key(current) or inspected.spec != spec:
                        raise ValueError('图片核验结果与当前转换计划不一致')
                    if fingerprint is None or inspected.source_fingerprint != fingerprint: raise ValueError('图片核验指纹与当前对象不一致')
                detail = '转换生成新内容；结果成为后续对象'
                if replacement: detail += '；替换原件，执行前必须建立内部可恢复备份'
                else: detail += '；保留原件'
                add('image_convert', target, index, conversion_spec=spec, inspected=inspected,
                    replacement=replacement, detail=detail)
                warnings.append('图片转换可能不保留元数据；执行前由独立转换工作线程核验输入与格式能力')
            else:
                if service.config.sync_root is None: raise ValueError('项目路由需要先选择同步根目录')
                if facts.created is None: raise ValueError('项目路由缺少源创建时间')
                root = checked_path(service.config.sync_root)
                spec = parse_tag(options['tag'], discover_projects(root), root, library)
                folder = spec.dest/facts.created.strftime('%y%m%d') if spec.mode == 'dated' and facts.kind != 'folder' else spec.dest
                names = _names_in(folder, reservations, local)
                if facts.kind == 'folder':
                    # build_targets probes is_dir on disk; the ordered subject may
                    # not exist yet, so preserve directory names explicitly here.
                    base, name, sequence = current.name, current.name, 2
                    while name.casefold() in {value.casefold() for value in names}:
                        name = f'{Path(base).stem} {sequence}{Path(base).suffix}'; sequence += 1
                    targets = [folder/validate_component(name)]
                else:
                    targets = build_targets(current, spec, facts.created, facts.video_width, names)
                    warnings.extend(targets.warnings)
                # Multi-target route copies the current subject to the second
                # target, then moves the same bound subject to the primary target.
                # Terminal expansion deliberately does not change copy's subject.
                if len(targets) == 2:
                    second = validate_target(targets[1])
                    steps.append(PlannedStep('copy', current, second, fingerprint, version, index,
                                             explanation='项目路由的第二个目标副本', advances_subject=False))
                    local.append(second)
                add('move', targets[0], index, detail='按项目模板归档当前对象')
        reservations.targets.update(local)
        errors = ()
    except (ValueError, OSError) as exc:
        # Keep tentative steps visible for explanation but never runnable.
        # Atomic reservation means another input may still use these names.
        errors = (str(exc),)
    return RulePlan(original, facts.fingerprint, rule.id, rule.revision, ruleset_revision,
                    template_revision, now, tuple(steps), explanation, errors, tuple(warnings))
