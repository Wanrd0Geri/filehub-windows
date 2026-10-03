"""Pure widgets: user edits and opaque intents, no runtime or filesystem work."""
from dataclasses import FrozenInstanceError

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QDateTime, QDate, QTime, QTimeZone, Qt
from PySide6.QtGui import QColor

from filehub.automation.models import Action, ConditionGroup, Predicate, Rule, RuleSet
from filehub.templates import TemplateLibrary
from filehub.ui.condition_editor import ConditionEditor
from filehub.ui.action_editor import ActionEditor
from filehub.ui.rules_page import RulesPage
from filehub.ui.templates_page import TemplatesPage
from filehub.ui.conversion_page import ConversionPage


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def rule(enabled=True):
    return Rule(name='图片转存', enabled=enabled, condition=Predicate('kind', 'equals', 'image'),
                actions=(Action('rename', {'pattern': '{stem}{ext}'}),))


def test_nested_condition_controls_roundtrip_and_limits(app):
    editor = ConditionEditor()
    leaf = Predicate('name', 'contains', '海报')
    tree = ConditionGroup('all', (Predicate('kind', 'equals', 'image'),
           ConditionGroup('any', (leaf, ConditionGroup('none', (Predicate('extension', 'equals', 'gif'),))))))
    editor.set_value(tree)
    assert editor.value() == tree
    editor.add_group((1, 1), 'all')
    with pytest.raises(ValueError, match='4'):
        editor.add_group((1, 1, 1), 'any')
    editor.remove_node((1, 1, 1))
    editor.node((1, 0)).text_value.setText('封面')
    assert editor.value().children[1].children[0].value == '封面'
    editor.node((0,)).kind_value.setCurrentIndex(editor.node((0,)).kind_value.findData('folder'))
    assert editor.value().children[0].value == 'folder'


@pytest.mark.parametrize('predicate', [Predicate('extension', 'glob', '*.png'),
    Predicate('size_bytes', 'ge', 1048576), Predicate('created', 'lt', '2026-10-01T00:00:00+00:00'),
    Predicate('modified', 'ge', '2026-09-01T00:00:00+08:00'),
    Predicate('first_seen_age_seconds', 'gt', 3600), Predicate('stable_age_seconds', 'le', 60)])
def test_condition_field_units_and_dates_preserve_values(app, predicate):
    editor = ConditionEditor(); editor.set_value(predicate)
    assert editor.value() == predicate


def test_date_calendar_preserves_loaded_timezone_precision_until_changed(app):
    editor = ConditionEditor()
    editor.set_value(Predicate('created', 'ge', '2026-10-01T13:15:17.123456+08:00'))
    assert editor.root.date_value.calendarPopup()
    assert editor.value().value == '2026-10-01T13:15:17.123456+08:00'
    editor.root.date_value.setDateTime(QDateTime(QDate(2026, 10, 2), QTime(5, 15, 17), QTimeZone.utc()))
    assert editor.value().value == '2026-10-02T05:15:17+00:00'


@pytest.mark.parametrize('number', [2**63 - 1, 0.000000123456789, 1.23456789012345])
def test_numeric_imports_are_not_silently_rounded_or_clamped(app, number):
    editor = ConditionEditor(); editor.set_value(Predicate('size_bytes', 'ge', number))
    assert editor.value().value == number
    editor.root.number_value.setText('2')
    editor.root.unit.setCurrentIndex(2)
    assert editor.value().value == 2097152


@pytest.mark.parametrize('invalid', ['NaN', 'Infinity', '1e1000000', '-1', '不是数字'])
def test_numeric_invalid_draft_is_reported_as_validation_error(app, invalid):
    editor = ConditionEditor(); editor.set_value(Predicate('size_bytes', 'ge', 1))
    editor.root.number_value.setText(invalid)
    with pytest.raises(ValueError): editor.value()


def test_actions_all_kinds_reorder_and_replacement(app):
    actions = (Action('rename', {'pattern': '{stem}_{sequence}{ext}'}),
        Action('move', {'destination': 'C:/输出'}), Action('copy', {'destination': 'D:/备份'}),
        Action('subfolder', {'path': '素材/图片'}),
        Action('image_convert', {'output_format': 'webp', 'mode': 'replace', 'quality': 75,
                                'lossless': True, 'background': '#123456'}),
        Action('project_route', {'tag': 'LYX角色龙'}))
    editor = ActionEditor(); editor.set_value(actions)
    assert editor.value() == actions
    editor.move_action(1, 1)
    assert [a.kind for a in editor.value()][:3] == ['rename', 'copy', 'move']
    editor.remove_action(3)
    assert len(editor.value()) == 5
    fields = editor.rows[3].conversion
    assert not fields.destination.isEnabled()
    assert fields.value()[1:] == ('replace', None)
    fields.mode.setCurrentIndex(0)
    with pytest.raises(ValueError): editor.value()
    fields.destination.setText('C:/输出')
    assert editor.value()[3].options['mode'] == 'keep'


def test_rules_readonly_selection_and_samples_invalidate_preview(app):
    page = RulesPage(); page.set_ruleset(RuleSet((rule(),)))
    previews = []; executes = []
    page.previewRequested.connect(previews.append)
    page.executeRequested.connect(executes.append)
    page.set_sample_paths(('C:/海报.png',))
    page.set_preview('可执行', object(), True)
    assert not executes
    page.preview_button.click()
    assert previews[0].rule_id is None
    assert previews[0].generation == page.generation
    token = object(); page.set_preview('可执行', token, True)
    page.execute_button.click(); assert executes == [token]
    page.set_sample_paths(('C:/海报.png',))
    assert not page.execute_button.isEnabled()


def test_rules_page_has_no_authoring_controls(app):
    page = RulesPage(); page.set_ruleset(RuleSet((rule(),)))
    for name in ('new_rule','duplicate_rule','delete_rule','saveRequested','value',
                 'name_edit','condition_editor','action_editor','scope_list','save_button'):
        assert not hasattr(page,name)
    assert page.summary.isReadOnly()


def test_rules_watch_context_does_not_edit_loaded_definition(app):
    from dataclasses import replace
    page = RulesPage(); page.set_watch_roots(('C:/观察甲', 'D:/观察乙'))
    saved = replace(rule(), scope=('E:/已移除观察',))
    snapshot=RuleSet((saved,));page.set_ruleset(snapshot)
    page.set_sample_paths(('C:/样本文件夹',))
    requests = []; page.previewRequested.connect(requests.append); page.preview_button.click()
    assert requests[0].paths==('C:/样本文件夹',)
    assert page._ruleset is snapshot and saved.scope==('E:\\已移除观察',)
    assert page._watch_roots==('C:/观察甲','D:/观察乙')


def test_readonly_scope_snapshot_order_and_case_are_not_rewritten(app):
    from dataclasses import replace
    page = RulesPage(); page.set_watch_roots(('C:/观察甲', 'D:/观察乙'))
    saved = replace(rule(), scope=('d:/观察乙', 'c:/观察甲'))
    snapshot=RuleSet((saved,));page.set_ruleset(snapshot)
    page.rule_choice.setCurrentIndex(1);page.set_watch_roots(('D:/另外观察',))
    assert page._ruleset is snapshot and snapshot.rules[0].scope==('d:\\观察乙', 'c:\\观察甲')


def test_conversion_pure_requests_tokens_cancel_and_commit_progress(app):
    page = ConversionPage(); previews = []; executes = []; cancels = []
    page.previewRequested.connect(previews.append); page.executeRequested.connect(executes.append)
    page.cancelRequested.connect(lambda: cancels.append(True))
    page.set_paths(('C:/很长的中文图片路径/海报.webp',))
    page.fields.mode.setCurrentIndex(1); page.fields.output_format.setCurrentIndex(1)
    page.preview_button.click()
    request = previews[0]
    assert request.mode == 'replace' and request.output_dir is None
    assert request.spec.output_format == 'png' and not executes
    with pytest.raises(FrozenInstanceError): request.mode = 'keep'
    token = object(); page.set_preview(({'source': request.paths[0], 'target': 'C:/很长的中文图片路径/海报.png',
        'status': 'ready', 'message': '原图备份后替换'},), token)
    page.execute_button.click(); assert executes == [token]
    page.execute_button.click(); assert executes == [token]
    page.set_busy(True); page.cancel_button.click()
    assert cancels == [True] and page.cancel_pending
    assert page.results.isEnabled()
    page.set_progress({'index': 0, 'phase': 'complete', 'percent': 100})
    assert '保存' in page.results.item(0, 2).text()
    page.set_progress({'index': 0, 'phase': 'committing', 'percent': 99})
    assert page.results.item(0, 2).text() == '正在保存/替换'
    page.set_progress({'index': 0, 'status': 'success', 'message': '已替换'})
    assert '完成' in page.results.item(0, 2).text()
    page.set_busy(False); page.fields.quality.setValue(80)
    assert not page.execute_button.isEnabled()


def test_conversion_edits_and_same_selection_invalidate_tokens(app):
    page = ConversionPage(); page.set_paths(('C:/a.png',)); page.fields.destination.setText('C:/输出')
    token = object(); page.set_preview([], token)
    previous = page.generation
    page.set_paths(('C:/a.png',))
    assert page.generation > previous and not page.execute_button.isEnabled()
    page.set_preview([], token); page.fields.background.setText('#000000')
    assert not page.execute_button.isEnabled()


def test_templates_copy_edit_assign_delete_and_failed_save(app):
    page = TemplatesPage(); page.set_library(TemplateLibrary()); page.set_projects({'LYX': '项目龙'})
    assert page.name_edit.isReadOnly()
    page.copy_template('自定义')
    identifier = page.selected_id
    page.directory_fields['production_dir'].setText('制作/镜头')
    page.categories.add_row('怪物', '生物/怪物')
    page.pattern_fields['asset'].setText('{stem}_{sequence}{ext}')
    page.assign_project('LYX', identifier)
    library = page.value()
    assert library.for_project('lyx').production_dir == '制作/镜头'
    assert library.for_project('lyx').asset_categories['怪物'] == '生物/怪物'
    page.delete_template()
    assert '解除分配' in page.error_label.text() and identifier in page.value().templates
    saves = []; page.saveRequested.connect(saves.append); page.save_button.click()
    page.show_error('保存失败'); assert page.dirty and saves[0].assignments['LYX'] == identifier
    page.set_library(saves[0])  # Controller acknowledgement establishes saved assignment guard.
    page.assign_project('LYX', None); page.delete_template()
    assert identifier in page.value().templates and '保存' in page.error_label.text()
    page.set_library(page.value()); page.delete_template()
    assert identifier not in page.value().templates


def test_constructors_and_values_do_not_call_stores_or_codec(app, monkeypatch):
    import filehub.automation.models as models
    import filehub.templates as templates
    import filehub.conversion as conversion
    def forbidden(*a, **k): raise AssertionError('widget attempted backend IO')
    monkeypatch.setattr(models.RuleStore, 'load', forbidden)
    monkeypatch.setattr(models.RuleStore, 'save', forbidden)
    monkeypatch.setattr(templates.TemplateStore, 'load', forbidden)
    monkeypatch.setattr(templates.TemplateStore, 'save', forbidden)
    monkeypatch.setattr(conversion, 'inspect', forbidden)
    monkeypatch.setattr(conversion, 'generate', forbidden)
    rules = RulesPage(); rules.set_ruleset(RuleSet((rule(),))); rules.set_sample_paths(('C:/a.png',));rules._preview()
    library = TemplatesPage(); library.set_library(TemplateLibrary()); library.value()
    images = ConversionPage(); images.set_paths(('C:/a.png',)); images.fields.mode.setCurrentIndex(1); images.value()


def test_new_action_fields_edits_and_validation_are_structured(app):
    editor = ActionEditor()
    for kind in ('rename', 'move', 'copy', 'subfolder', 'image_convert', 'project_route'): editor.add_action(kind)
    editor.rows[0].option.setText('{stem}_完成{ext}')
    editor.rows[1].option.setText('C:/归档'); editor.rows[2].option.setText('D:/副本')
    editor.rows[3].option.setText('素材/场景'); editor.rows[5].option.setText('LYX场景山')
    conversion = editor.rows[4].conversion
    conversion.output_format.setCurrentIndex(2); conversion.destination.setText('C:/转换')
    conversion.quality.setValue(67); conversion.lossless.setChecked(True)
    assert editor.value()[0].options['pattern'] == '{stem}_完成{ext}'
    assert editor.value()[4].options['quality'] == 67 and editor.value()[4].options['lossless']
    editor.move_action(5, -1)
    with pytest.raises(ValueError, match='最后'): editor.value()
    editor.move_action(4, 1)
    conversion.mode.setCurrentIndex(1)
    assert 'destination' not in editor.value()[4].options
    editor.rows[3].option.setText('../逃逸')
    with pytest.raises(ValueError): editor.value()


def test_image_background_picker_and_format_controls(app, monkeypatch):
    from filehub.ui.action_editor import ConversionFields, QColorDialog
    fields = ConversionFields(); fields.mode.setCurrentIndex(1)
    monkeypatch.setattr(QColorDialog, 'getColor', lambda *a, **k: QColor('#FAF0E6'))
    fields.color_button.click()
    assert fields.value()[0].background == '#FAF0E6' and fields.background.isEnabled()
    fields.background_choice.setCurrentIndex(1)
    assert fields.value()[0].background == '#000000'
    fields.output_format.setCurrentIndex(1)
    assert not fields.quality.isEnabled() and not fields.lossless.isEnabled()
    fields.output_format.setCurrentIndex(2); fields.lossless.setChecked(True)
    assert not fields.quality.isEnabled() and fields.value()[0].lossless


def test_rules_folder_picker_import_export_intents_and_busy(app, monkeypatch):
    from filehub.ui.rules_page import QFileDialog
    page = RulesPage(); page.set_ruleset(RuleSet((rule(),)))
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a, **k: 'C:/样本文件夹')
    page.folder_sample_button.click()
    previews = []; page.previewRequested.connect(previews.append); page.preview_button.click()
    assert previews[0].paths == ('C:/样本文件夹',)
    management = []
    page.managementRequested.connect(management.append)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **k: ('C:/规则.json', ''))
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **k: ('D:/导出.json', ''))
    page.manage_buttons[0].click(); page.manage_buttons[3].click()
    assert management == [('import',None,'C:/规则.json'),('export',None,'D:/导出.json')]
    page.set_busy(True)
    assert all(not button.isEnabled() for button in page.manage_buttons) and not page.preview_button.isEnabled()
    page.set_busy(False);page.show_error('目录册需要恢复')
    assert all(button.isEnabled() for button in page.manage_buttons)
    assert page.error_label.text()=='目录册需要恢复' and not page.execute_button.isEnabled()


def test_template_all_directory_mapping_fields_and_validation_preserve_draft(app):
    page = TemplatesPage(); page.copy_template('场景模板')
    for key, path in [('production_dir', '镜头'), ('asset_root', '设定'), ('final_dir', '交付'), ('test_dir', '测试')]:
        page.directory_fields[key].setText(path)
    page.keep_routes.add_row('客户', '来稿')
    page.pattern_fields['shot'].setText('{stem}_{shot}{ext}')
    page.pattern_fields['final'].setText('{stem}_{date_long}{ext}')
    page.example_button.click()
    assert '海报_22.png' in page.example_label.text() and '海报_20261001.png' in page.example_label.text()
    template = page.value().templates[page.selected_id]
    assert (template.production_dir, template.asset_root, template.final_dir, template.test_dir) == ('镜头', '设定', '交付', '测试')
    assert template.keep_name_routes['客户'] == '来稿'
    page.keep_routes.add_row('客户', '重复')
    saves = []; page.saveRequested.connect(saves.append); page.save_button.click()
    assert not saves and page.dirty and page.keep_routes.table.rowCount() == 5
    page.set_busy(True); assert not page.save_button.isEnabled()


def test_conversion_preview_errors_and_busy_cancel_apply_to_preview_jobs(app):
    page = ConversionPage(); page.set_paths(('C:/a.png', 'C:/b.png')); page.fields.mode.setCurrentIndex(1)
    cancels = []; page.cancelRequested.connect(lambda: cancels.append(1))
    page.set_preview([{'source': 'C:/a.png', 'target': 'C:/a.jpg', 'status': 'ready'},
                      {'source': 'C:/b.png', 'target': 'C:/b.jpg', 'status': 'error', 'message': '已有同名文件'}], None, False)
    assert not page.execute_button.isEnabled()
    page.set_busy(True); page.cancel_button.click(); page.cancel_button.click()
    assert cancels == [1] and not page.preview_button.isEnabled()
    page.set_progress({'index': 0, 'status': 'success', 'message': '已替换'})
    page.set_progress({'index': 1, 'status': 'canceled', 'message': '取消了剩余项目'})
    page.set_busy(False)
    assert page.results.item(0, 2).text() == '已完成' and page.results.item(1, 2).text() == '已取消'
    assert not page.cancel_pending and page.preview_button.isEnabled()


def test_request_snapshots_detach_mutable_input_and_reject_external_replace_dir():
    from filehub.ui.rule_requests import RulePreviewRequest, ConversionRequest
    from filehub.conversion.models import ConversionSpec
    paths = ['C:/a.png']
    rule_request = RulePreviewRequest('rule', paths, 'revision', 0)
    image_request = ConversionRequest(paths, ConversionSpec(), 'replace')
    paths.append('C:/b.png')
    assert rule_request.paths == ('C:/a.png',) and image_request.paths == ('C:/a.png',)
    with pytest.raises(ValueError): ConversionRequest(('C:/a.png',), ConversionSpec(), 'replace', 'C:/other')


def test_format_rows_hide_irrelevant_controls_without_rewriting_loaded_spec(app):
    from filehub.ui.action_editor import ConversionFields
    from filehub.conversion.models import ConversionSpec
    fields = ConversionFields()
    fields.set_value(ConversionSpec(output_format='png', quality=73, lossless=True, background='#ABCDEF'), 'replace')
    assert fields.quality.isHidden() and fields.lossless.isHidden()
    assert fields.background_choice.isHidden() and fields.background_box.isHidden()
    assert fields.value()[0].quality == 73 and fields.value()[0].background == '#ABCDEF' and fields.value()[0].lossless
    fields.output_format.setCurrentIndex(0)
    assert not fields.quality.isHidden() and fields.lossless.isHidden()
    assert not fields.background_choice.isHidden() and not fields.background_box.isHidden()
    fields.background_choice.setCurrentIndex(0)
    assert fields.background_box.isHidden()
    fields.output_format.setCurrentIndex(2)
    assert not fields.quality.isHidden() and not fields.lossless.isHidden()
    assert fields.background_choice.isHidden() and fields.background_box.isHidden()
