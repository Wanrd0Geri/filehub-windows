"""Real 0.2 acceptance, called only by the explicit UUID-owned self-test entry.

Uses the same service/executor/engine/codecs as the application. No normal user
state, registry, shell recycle or installation API is accessed here.
"""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys

from PySide6.QtGui import QImage, QImageReader, QColor
from .automation.models import Rule, RuleSet, Predicate, Action
from .config import Config
from .conversion import ConversionSpec, capabilities
from .models import Fingerprint
from .scheduler import Scheduler
from .service import FileHubService
from .templates import TemplateLibrary


def extend_report(fixture, report):
    """Create a fresh child of the existing self-test UUID and append evidence."""
    work = Path(fixture) / 'release020'
    work.mkdir()  # Must be new; never reuse a prior acceptance data directory.
    details = {'runtime_frozen': bool(getattr(sys, 'frozen', False)), 'images': [],
               'replacements': [], 'work_dir': str(work)}
    report['release020'] = details
    checks = report['checks']
    services = []

    def require(value, message):
        if not value:
            raise ValueError('0.2 acceptance: ' + message)

    def service(name, config=None):
        value = FileHubService(config or Config(), work / name / 'state')
        services.append(value)
        return value

    def image(path, width=12, height=8, *, transparent=False, format='PNG'):
        path.parent.mkdir(parents=True, exist_ok=True)
        value = QImage(width, height, QImage.Format.Format_ARGB32)
        value.fill(QColor(0, 0, 0, 0) if transparent else QColor('#f04422'))
        if not transparent:
            for y in range(height):
                for x in range(width):
                    value.setPixelColor(x, y, QColor((x * 19) % 256, (y * 29) % 256, 80))
        require(value.save(str(path), format, 95), 'fixture image encoder')
        return path

    def native(path, format, dimensions):
        reader = QImageReader(str(path))
        detected = bytes(reader.format()).decode('ascii').lower()
        value = reader.read()
        require(not value.isNull(), 'ordinary QImageReader: ' + reader.errorString())
        require(detected == format and (value.width(), value.height()) == dimensions,
                'native image format/dimensions')
        return value

    def convert(owner, source, spec, *, mode='keep', destination=None):
        preview = owner.conversions.submit_image_preview(
            [source], spec, mode=mode, output_dir=destination).future.result(30)
        require(len(preview.items) == 1 and not preview.items[0].error, 'standalone preview')
        outcomes = owner.conversions.submit_images(preview).future.result(30)
        require(len(outcomes) == 1 and outcomes[0].ok, 'standalone publication: ' + str(outcomes))
        target = preview.items[0].target
        plan = preview.items[0].conversion_plan
        decoded = native(target, spec.output_format, (plan.width, plan.height))
        details['images'].append({'source': str(source), 'target': str(target), 'mode': mode,
            'input_format': plan.input_format, 'output_format': spec.output_format,
            'width': decoded.width(), 'height': decoded.height(), 'bytes': target.stat().st_size,
            'sha256': Fingerprint.capture(target).sha256, 'batch_id': outcomes[0].batch_id})
        return target, outcomes[0], decoded

    try:
        cap = capabilities()
        details['qt_version'] = cap.qt_version
        details['capabilities'] = {'inputs': list(cap.inputs), 'outputs': list(cap.outputs), 'digest': cap.digest}
        require(set(cap.inputs) == {'jpeg', 'png', 'webp'} and set(cap.outputs) == {'jpeg', 'png', 'webp'},
                'required native image codecs')
        owner = service('images')
        source = image(work / 'images' / 'roundtrip.png')
        original = Fingerprint.capture(source)
        current = source
        roundtrips = []
        for index, format in enumerate(('jpeg', 'png', 'webp', 'jpeg')):
            current, outcome, decoded = convert(owner, current,
                ConversionSpec(output_format=format, lossless=format == 'webp'),
                destination=work / 'images' / ('roundtrip-' + str(index)))
            roundtrips.append(outcome)
        checks['image_jpeg_png_webp_roundtrip'] = True
        require(Fingerprint.capture(source) == original, 'keep changed original fingerprint')
        for outcome in reversed(roundtrips):
            require(owner.undo(outcome.batch_id).ok, 'keep roundtrip inverse')
        require(Fingerprint.capture(source) == original, 'keep inverse original fingerprint')
        checks['image_keep_original_and_undo'] = True

        alpha = image(work / 'images' / 'alpha.png', 1, 1, transparent=True)
        alpha_original = Fingerprint.capture(alpha)
        for format in ('png', 'webp'):
            target, outcome, decoded = convert(owner, alpha, ConversionSpec(output_format=format, lossless=True),
                destination=work / 'images' / ('alpha-' + format))
            require(decoded.pixelColor(0, 0).alpha() == 0, 'native transparency')
            if format == 'webp':
                require(target.stat().st_size == 42, 'tiny lossless WebP expected 42 bytes')
                details['tiny_webp'] = {'path': str(target), 'bytes': target.stat().st_size,
                    'native_alpha': decoded.pixelColor(0, 0).alpha(), 'native_reader': 'QImageReader(path)'}
                checks['image_tiny42_webp_native_decode'] = True
            require(owner.undo(outcome.batch_id).ok, 'transparent keep inverse')
        require(Fingerprint.capture(alpha) == alpha_original, 'transparency changed original')
        checks['image_transparency_png_webp'] = True
        details['jpeg_backgrounds'] = []
        for color in ('#FFFFFF', '#000000', '#2468AC'):
            target, outcome, decoded = convert(owner, alpha, ConversionSpec(output_format='jpeg', quality=100, background=color),
                destination=work / 'images' / ('background-' + color[1:]))
            actual = decoded.pixelColor(0, 0)
            expected = QColor(color)
            require(all(abs(a - b) <= 3 for a, b in zip(actual.getRgb()[:3], expected.getRgb()[:3])), 'JPEG background')
            details['jpeg_backgrounds'].append({'requested': color, 'decoded_rgb': list(actual.getRgb()[:3])})
            require(owner.undo(outcome.batch_id).ok, 'background inverse')
        checks['image_jpeg_backgrounds'] = True

        for same_path in (False, True):
            name = 'same-path' if same_path else 'cross-extension'
            original_path = image(work / 'images' / (name + ('.jpg' if same_path else '.png')),
                                  format='JPEG' if same_path else 'PNG')
            original_bytes = original_path.read_bytes()
            stream = Path(str(original_path) + ':FileHubSelfTest')
            stream.write_bytes(b'owned acceptance named stream')
            before = Fingerprint.capture(original_path)
            target, outcome, decoded = convert(owner, original_path,
                ConversionSpec(output_format='jpeg', quality=25), mode='replace')
            require(target == original_path if same_path else not original_path.exists(), 'true replacement source/path')
            require(target.read_bytes() != original_bytes, 'replacement did not encode new content')
            row = owner.engine.journal.items(outcome.batch_id)[0]
            backup = owner.engine.journal.generated(row.operation_id)
            require(backup.mode == 'replace' and backup.phase == 'committed' and backup.backup is not None,
                    'durable replacement backup record')
            require(backup.backup.is_relative_to(owner.engine.state_dir / 'conversion-backups'), 'private backup containment')
            require(backup.backup.read_bytes() == original_bytes and Fingerprint.capture(backup.backup) == backup.backup_fingerprint,
                    'full guarded backup verification')
            require(backup.backup_fingerprint.streams == before.streams, 'named streams backed up')
            require(owner.undo(outcome.batch_id).ok, 'replacement inverse')
            restored = Fingerprint.capture(original_path)
            require(original_path.read_bytes() == original_bytes and stream.read_bytes() == b'owned acceptance named stream',
                    'replacement restored original bytes/ADS')
            require(restored.creation_ns == before.creation_ns and restored.mtime_ns == before.mtime_ns,
                    'replacement restored original times')
            require(same_path or not target.exists(), 'cross-extension inverse removed generated output')
            details['replacements'].append({'source': str(original_path), 'target': str(target),
                'same_path': same_path, 'backup': str(backup.backup), 'batch_id': outcome.batch_id,
                'restored_bytes_ads_times': True})
            checks['image_' + ('same_path' if same_path else 'cross_extension') + '_replace_backup_undo'] = True

        collision_source = image(work / 'images' / 'numbered-006.png')
        collision_original = collision_source.read_bytes()
        collision_before = Fingerprint.capture(collision_source)
        occupied = [image(work / 'images' / name, format='JPEG')
                    for name in ('numbered-006.jpg', 'numbered-019.jpg')]
        occupied_bytes = [path.read_bytes() for path in occupied]
        target, outcome, decoded = convert(owner, collision_source,
            ConversionSpec(output_format='jpeg', quality=25), mode='replace')
        require(target.name == 'numbered-020.jpg' and not collision_source.exists(), 'collision family max replacement')
        require(all(path.read_bytes() == raw for path, raw in zip(occupied, occupied_bytes)), 'occupied JPEG preservation')
        row = owner.engine.journal.items(outcome.batch_id)[0]
        backup = owner.engine.journal.generated(row.operation_id)
        require(backup.mode == 'replace' and backup.backup is not None
                and backup.backup.read_bytes() == collision_original, 'numbered replacement verified backup')
        require(owner.undo(outcome.batch_id).ok and not target.exists()
                and collision_source.read_bytes() == collision_original
                and Fingerprint.capture(collision_source).same_content(collision_before), 'numbered replacement inverse')
        require(all(path.read_bytes() == raw for path, raw in zip(occupied, occupied_bytes)), 'inverse occupied JPEG preservation')
        checks['image_collision_max_number_replace_backup_undo'] = True
        preview = owner.conversions.submit_image_preview([collision_source],
            ConversionSpec(output_format='jpeg'), mode='replace').future.result(30)
        require(not preview.items[0].error and preview.items[0].target == target, 'bound collision preview')
        race_bytes = image(target, format='JPEG').read_bytes()
        outcomes = owner.conversions.submit_images(preview).future.result(30)
        require(len(outcomes) == 1 and not outcomes[0].ok and '重新预览' in outcomes[0].error,
                'late occupancy requires re-preview')
        require(target.read_bytes() == race_bytes and not target.with_name('numbered-021.jpg').exists()
                and Fingerprint.capture(collision_source).same_content(collision_before), 'late occupancy freezes exact target')
        details['collision_numbering'] = {'target': str(target), 'occupied_preserved': True,
            'backup_verified': True, 'undone': True, 'late_occupancy_rejected': True}
        checks['image_collision_preview_late_occupancy_rejected'] = True

        watch = work / 'generic' / 'watch'; watch.mkdir(parents=True)
        generic = service('generic', Config(watch_roots=(watch,), paused=False))
        text = watch / 'fresh.txt'; text.write_bytes(b'newly observed, no sync root')
        destination = work / 'generic' / 'copied'
        rule = Rule(name='无同步根普通规则', enabled=True, condition=Predicate('extension', 'equals', '.txt'),
                    actions=(Action('copy', {'destination': str(destination)}),))
        generic.rules.save(RuleSet((rule,)))
        now = datetime.now(timezone.utc)
        outcomes = Scheduler(generic).tick(now)
        require(generic.config.sync_root is None and generic.config.sweep_days == 3 and len(outcomes) == 1 and outcomes[0].ok,
                'fresh generic rule without sync before legacy three-day gate')
        require(text.exists() and (destination / text.name).read_bytes() == text.read_bytes(), 'generic copied subject')
        reopened = service('generic', generic.config)
        require(Scheduler(reopened).tick(now) == [], 'durable restart suppression')
        require(reopened.undo(outcomes[0].batch_id).ok and not (destination / text.name).exists(), 'generic inverse')
        details['generic_rule'] = {'sync_root': None, 'legacy_sweep_days': 3, 'first_tick_succeeded': True,
                                  'restart_suppressed': True, 'batch_id': outcomes[0].batch_id}
        checks['generic_rule_no_sync_before_legacy_gate'] = True

        chain = service('chain')
        chain_source = image(work / 'chain' / 'input.png')
        chain_before = Fingerprint.capture(chain_source)
        copied = work / 'chain' / 'copied'; moved = work / 'chain' / 'moved'
        rule = Rule(name='复制转换移动', enabled=True, condition=Predicate('extension', 'equals', '.png'),
                    actions=(Action('copy', {'destination': str(copied)}),
                             Action('image_convert', {'output_format': 'webp', 'mode': 'replace', 'lossless': True}),
                             Action('move', {'destination': str(moved)})))
        chain.rules.save(RuleSet((rule,)))
        preview = chain.conversions.submit_rule_preview([chain_source], rule.id).future.result(30)
        outcomes = chain.conversions.submit_rule(preview).future.result(30)
        require(len(outcomes) == 1 and outcomes[0].ok, 'ordered image rule: ' + str(outcomes))
        native(moved / 'input.webp', 'webp', (12, 8))
        batch = outcomes[0].batch_id
        kinds = [row.kind for row in chain.engine.journal.items(batch)]
        require(kinds == ['copy', 'convert', 'move'] and any(row.batch_id == batch and row.ok for row in chain.history()),
                'ordered rule journal/history')
        require(Fingerprint.capture(chain_source) == chain_before and not (copied / 'input.png').exists(), 'copy generated subject')
        require(chain.undo(batch).ok and Fingerprint.capture(chain_source) == chain_before
                and not (moved / 'input.webp').exists() and not (copied / 'input.png').exists(), 'ordered chain inverse')
        details['rule_chain'] = {'batch_id': batch, 'journal_kinds': kinds, 'restored_original': True}
        checks['ordered_copy_convert_move_history_undo'] = True

        imported_watch = work / 'import' / 'watch'; imported_watch.mkdir(parents=True)
        imported_source = imported_watch / 'stay.txt'; imported_source.write_bytes(b'disabled imported rule')
        imported = service('import', Config(watch_roots=(imported_watch,), paused=False))
        definition = Rule(name='导入应关闭', enabled=True, condition=Predicate('extension', 'equals', '.txt'),
                          actions=(Action('rename', {'pattern': 'changed{ext}'}),))
        saved = imported.rules.import_document(RuleSet((definition,)).to_document())
        reopened = service('import', imported.config)
        persisted = reopened.rules.load().rules
        require(len(persisted) == 1 and not persisted[0].enabled and persisted[0].id != definition.id,
                'import must allocate fresh disabled persisted rule')
        require(Scheduler(reopened).tick(now) == [] and imported_source.read_bytes() == b'disabled imported rule'
                and not (imported_watch / 'changed.txt').exists(), 'disabled import mutated source')
        details['imported_rule'] = {'original_id': definition.id, 'imported_id': saved.rules[0].id,
                                    'persisted_enabled': persisted[0].enabled, 'source_unchanged': True}
        checks['imported_rule_disabled_persisted'] = True

        sync = work / 'template' / 'sync'
        project = sync / '1_工作' / '项目' / '261001_TST_模板验收'; project.mkdir(parents=True)
        template = service('template', Config(sync_root=sync))
        library = TemplateLibrary()
        custom = replace(library.templates['default'], id='acceptance', name='验收模板',
                         keep_name_routes={'参考': '验收/参考'})
        saved = template.templates.save(library.with_template(custom).assign('TST', custom.id))
        reopened = service('template', template.config)
        require(reopened.reload_templates().revision == saved.revision, 'template assignment persistence')
        source = image(work / 'template' / 'source.png')
        before = Fingerprint.capture(source)
        preview = reopened.preview([source], 'TST参考')
        target = project / '验收' / '参考' / source.name
        require(preview.items[0].targets == (target,), 'persisted custom template route')
        result = reopened.execute(preview)
        require(result.ok and target.exists() and not source.exists(), 'template routed archive')
        require(reopened.undo(result.batch_id).ok and not target.exists() and source.read_bytes()
                and Fingerprint.capture(source).sha256 == before.sha256, 'template archive inverse')
        details['template'] = {'target': str(target), 'persisted': True, 'undone': True,
                               'revision': saved.revision, 'batch_id': result.batch_id}
        checks['template_route_persisted_undo'] = True
    finally:
        for owner in reversed(services):
            if not owner.close_conversions().wait(10):
                raise ValueError('0.2 acceptance: owned conversion worker did not settle')
