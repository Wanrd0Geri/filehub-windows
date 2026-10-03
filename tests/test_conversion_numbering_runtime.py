from rulefile_fixtures import install_rules
from threading import Event

import pytest
from PySide6.QtGui import QImage, QColor, QImageReader

from filehub.config import Config
from filehub.service import FileHubService
from filehub.conversion import ConversionSpec
from filehub.automation.models import Rule, RuleSet, Predicate, Action
from filehub.models import Fingerprint


@pytest.fixture
def owner(tmp_path):
    watch = tmp_path/'watch'; watch.mkdir()
    service = FileHubService(Config(watch_roots=(watch,), paused=False), tmp_path/'state')
    yield service, watch
    assert service.close_conversions().wait(10)


def image(path, format='PNG'):
    value = QImage(17, 11, QImage.Format.Format_RGB32); value.fill(QColor('#A53191'))
    assert value.save(str(path), format)
    return path


def rule_preview(service, paths, spec, mode='replace', destination=None):
    options = {'output_format': spec.output_format, 'mode': mode}
    if destination is not None: options['destination'] = str(destination)
    rule = Rule(enabled=True, condition=Predicate('name', 'glob', '*'), actions=(Action('image_convert', options),))
    install_rules(service,rule)
    return service.conversions.submit_rule_preview(paths, rule.id).future.result(30)


@pytest.mark.parametrize('rules', [False, True])
@pytest.mark.parametrize('mode,same', [('replace', False), ('replace', True), ('keep', True)])
def test_numbered_real_execute_backup_undo(owner, rules, mode, same):
    service, watch = owner
    source = image(watch/('图片-006.jpg' if same else '图片-006.png'), 'JPEG' if same else 'PNG')
    original = source.read_bytes(); before = Fingerprint.capture(source)
    occupied = watch/'图片-019.jpg'; image(occupied, 'JPEG'); occupied_bytes = occupied.read_bytes()
    if not same: image(watch/'图片-006.jpg', 'JPEG')
    spec = ConversionSpec(output_format='jpeg')
    if rules:
        preview = rule_preview(service, [source], spec, mode, watch if mode == 'keep' else None)
        assert not preview.errors
        target = preview.plans[0].steps[0].target
    else:
        preview = service.conversions.preview_images([source], spec, mode=mode, output_dir=watch if mode == 'keep' else None)
        assert not preview.items[0].error
        target = preview.items[0].target
    assert target == (source if same and mode == 'replace' else watch/'图片-020.jpg')
    outcomes = (service.conversions.submit_rule(preview) if rules else service.conversions.submit_images(preview)).future.result(30)
    assert len(outcomes) == 1 and outcomes[0].ok, outcomes
    assert bytes(QImageReader(str(target)).format()) == b'jpeg'
    assert occupied.read_bytes() == occupied_bytes
    if mode == 'replace':
        row = service.engine.journal.items(outcomes[0].batch_id)[0]
        backup = service.engine.journal.generated(row.operation_id)
        assert backup.mode == 'replace' and backup.backup.read_bytes() == original
        assert source == target or not source.exists()
    else: assert source.read_bytes() == original
    assert service.undo(outcomes[0].batch_id).ok
    assert source.read_bytes() == original and Fingerprint.capture(source).same_content(before)
    assert source == target or not target.exists()
    assert occupied.read_bytes() == occupied_bytes


@pytest.mark.parametrize('rules', [False, True])
def test_preview_number_is_frozen_against_late_occupancy(owner, rules):
    service, watch = owner
    source = image(watch/'a.png'); before = Fingerprint.capture(source)
    (watch/'a.jpg').write_bytes(b'existing')
    spec = ConversionSpec(output_format='jpeg')
    preview = rule_preview(service, [source], spec) if rules else service.conversions.preview_images([source], spec, mode='replace')
    target = preview.plans[0].steps[0].target if rules else preview.items[0].target
    assert target == watch/'a-1.jpg'
    target.write_bytes(b'late owner')
    outcomes = (service.conversions.submit_rule(preview) if rules else service.conversions.submit_images(preview)).future.result(30)
    assert not outcomes[0].ok and '重新预览' in outcomes[0].error
    assert target.read_bytes() == b'late owner' and not (watch/'a-2.jpg').exists()
    assert Fingerprint.capture(source) == before


def test_failed_standalone_inspection_does_not_reserve_output(owner):
    service, watch = owner
    bad = watch/'a.png'; bad.write_bytes(b'broken')
    good = image(watch/'a.webp', 'WEBP')
    preview = service.conversions.preview_images([bad, good], ConversionSpec(output_format='jpeg'), mode='replace')
    assert preview.items[0].error
    assert not preview.items[1].error and preview.items[1].target == watch/'a.jpg'


def test_standalone_selected_source_is_preserved_and_batch_allocations_unique(owner):
    service, watch = owner
    sources = [image(watch/'a.png'), image(watch/'a.jpg', 'JPEG'), image(watch/'a.webp', 'WEBP')]
    preview = service.conversions.preview_images(sources, ConversionSpec(output_format='jpeg'), mode='keep', output_dir=watch)
    assert not any(item.error for item in preview.items)
    assert [item.target.name for item in preview.items] == ['a-1.jpg', 'a-2.jpg', 'a-3.jpg']


def test_numbered_virtual_intermediate_same_format_replace_and_undo(owner):
    service, watch = owner
    source = image(watch/'a.png'); original = source.read_bytes()
    (watch/'a.jpg').write_bytes(b'foreign target')
    rule = Rule(enabled=True, condition=Predicate('name', 'glob', '*'), actions=(
        Action('image_convert', {'mode': 'replace', 'output_format': 'jpeg', 'quality': 95}),
        Action('image_convert', {'mode': 'replace', 'output_format': 'jpeg', 'quality': 20}),
        Action('image_convert', {'mode': 'replace', 'output_format': 'png'})))
    install_rules(service,rule)
    preview = service.conversions.submit_rule_preview([source], rule.id).future.result(30)
    assert not preview.errors
    assert [step.target.name for step in preview.plans[0].steps] == ['a-1.jpg', 'a-1.jpg', 'a-1.png']
    outcomes = service.conversions.submit_rule(preview).future.result(30)
    assert outcomes[0].ok, outcomes
    assert not source.exists() and bytes(QImageReader(str(watch/'a-1.png')).format()) == b'png'
    assert service.undo(outcomes[0].batch_id).ok
    assert source.read_bytes() == original and (watch/'a.jpg').read_bytes() == b'foreign target'
    assert not (watch/'a-1.jpg').exists() and not (watch/'a-1.png').exists()
