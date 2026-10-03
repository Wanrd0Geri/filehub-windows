"""Bounded external-rule acceptance, only in explicit UUID-owned self-test state."""
import json
from pathlib import Path
import sys

from .config import Config
from .service import FileHubService
from .scheduler import Scheduler
from datetime import datetime, timezone


def extend_report(fixture, report):
    work = Path(fixture) / 'release030'
    work.mkdir()
    source_dir = work / 'input'; source_dir.mkdir()
    output = work / 'output'; output.mkdir()
    source = source_dir / 'acceptance.txt'; source.write_bytes(b'external acceptance')
    owner = FileHubService(Config(watch_roots=(source_dir,), paused=False), work / 'state')
    checks = report['checks']
    details = {'work_dir': str(work), 'runtime_frozen': bool(getattr(sys, 'frozen', False))}
    report['release030'] = details

    def require(value, message):
        if not value:
            raise ValueError('0.3 acceptance: ' + message)

    try:
        pristine = owner.automation.preview([source])
        require(not pristine.plans and pristine.errors and not owner.catalog.load().packages, 'pristine no rule')
        require(Scheduler(owner).tick(datetime.now(timezone.utc)) == [] and source.read_bytes() == b'external acceptance', 'no legacy fallback')
        checks['external_pristine_no_legacy_mutation'] = True
        document = {'format': 'filehub.rules', 'version': 1, 'id': 'acceptance030', 'name': 'Owned acceptance',
            'bindings': {'input': {'label': 'Input'}, 'output': {'label': 'Output'}}, 'variables': {},
            'rules': [{'id': 'move-text', 'name': 'Move text', 'scope': [{'binding': 'input', 'relative': ''}],
                'condition': {'field': 'extension', 'operator': 'equals', 'value': '.txt'},
                'actions': [{'kind': 'move', 'options': {'destination': {'binding': 'output', 'relative': ''}}}]}]}
        raw = json.dumps(document).encode('utf-8')
        snapshot = owner.catalog.import_package(raw, expected_revision=owner.catalog.load().revision)
        require(not snapshot.enabled[document['id']], 'import disabled')
        details['imported_disabled'] = True
        snapshot = owner.catalog.bind(document['id'], {'input': source_dir, 'output': output}, expected_revision=snapshot.revision)
        snapshot = owner.catalog.set_enabled(document['id'], 'move-text', True, expected_revision=snapshot.revision)
        checks['external_import_bind_enable'] = True
        preview = owner.conversions.submit_rule_preview([source]).future.result(30)
        require(len(preview.plans) == 1 and not preview.errors and source.exists(), 'manual preview')
        checks['external_manual_preview'] = True
        outcomes = owner.conversions.submit_rule(preview).future.result(30)
        target = output / source.name
        require(len(outcomes) == 1 and outcomes[0].ok and not source.exists() and target.read_bytes() == b'external acceptance', 'real move')
        checks['external_real_move'] = True
        require(owner.undo(outcomes[0].batch_id).ok and not target.exists() and source.read_bytes() == b'external acceptance', 'undo')
        details['restored_bytes'] = source.read_text(encoding='utf-8')
        details['batch_id'] = outcomes[0].batch_id
        checks['external_move_undo'] = True
        before = owner.catalog.path.read_bytes()
        try:
            owner.catalog.replace_package(document['id'], b'{"format":"invalid"}', expected_revision=snapshot.revision)
        except ValueError:
            pass
        else:
            raise ValueError('0.3 acceptance: invalid replacement accepted')
        require(owner.catalog.path.read_bytes() == before, 'invalid replacement changed catalogue')
        details['invalid_replace_preserved_bytes'] = True
        checks['external_invalid_replace_preserves_catalogue'] = True
        unmatched = source_dir / 'unmatched.bin'; unmatched.write_bytes(b'no match')
        no_match = owner.conversions.submit_rule_preview([unmatched]).future.result(30)
        require(not no_match.plans and no_match.errors and unmatched.read_bytes() == b'no match' and not (output / unmatched.name).exists(), 'no-match fallback')
        checks['external_no_match_no_mutation'] = True
        if getattr(sys, 'frozen', False):
            help_root = Path(sys._MEIPASS) / 'help'
            expected = ['AI规则编写指南.md', 'filehub-rules-v1.schema.json'] + [
                'examples/' + name for name in ('01-move.json', '02-copy-rename-subfolder.json',
                '03-image-keep-ordered.json', '04-image-replace.json', '05-archive-compatibility.json')]
            require(all((help_root / name).is_file() for name in expected), 'static Help inventory')
            from .rulefiles.protocol import parse_package
            for name in expected[2:]:
                parse_package((help_root / name).read_bytes())
            require(set(owner.catalog.load().packages) == {'acceptance030'}, 'Help installed examples')
            details['help_files'] = expected
    finally:
        if not owner.close_conversions().wait(10):
            raise ValueError('0.3 acceptance: owned worker did not settle')
