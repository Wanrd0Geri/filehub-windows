"""Regression contracts for the reported 0.2.0 conversion-page defects."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
from pathlib import Path
import pytest
from PySide6.QtCore import Qt, QMimeData, QPoint, QPointF, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionComboBox
from filehub.config import Config, ConfigStore
from filehub.service import FileHubService
from filehub.ui.conversion_page import ConversionPage
from filehub.ui.main_window import MainWindow
from filehub.ui.theme import apply_theme


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def settle(app, predicate=lambda: True):
    deadline = time.monotonic() + 10
    while not predicate() and time.monotonic() < deadline:
        app.processEvents(); time.sleep(.005)
    assert predicate()
    for _ in range(12): app.processEvents()


@pytest.fixture
def window(app, tmp_path):
    service = FileHubService(Config(), tmp_path/'state')
    w = MainWindow(service, ConfigStore(tmp_path/'state'))
    settle(app, lambda: not w.coordinator.pending)
    w.navigate(5); w.show(); settle(app)
    yield w
    w.automation.retire(lambda: None)
    settle(app, lambda: w.automation.settled and not w.coordinator.pending)
    w._close_settled = True; w.close(); w.coordinator.close()


def send_drop(app, widget, urls, *, require_move=True):
    mime = QMimeData(); mime.setUrls(urls)
    enter = QDragEnterEvent(QPoint(8, 8), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(widget, enter)
    move = QDragMoveEvent(QPoint(9, 9), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(widget, move)
    if enter.isAccepted() and require_move: assert move.isAccepted()
    drop = QDropEvent(QPointF(8, 8), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(widget, drop); settle(app)
    return enter.isAccepted(), drop.isAccepted()


@pytest.mark.parametrize('target', ['page', 'select', 'list', 'sources_viewport', 'results_viewport', 'destination', 'window'])
def test_image_drop_appends_once_without_preview_or_archive_routing(app, window, tmp_path, monkeypatch, target):
    # Wrong routing, duplicate invalidation, codec IO or auto-start must each fail.
    import filehub.conversion as conversion
    def forbidden(*args, **kwargs): raise AssertionError('drop invoked codec')
    monkeypatch.setattr(conversion, 'inspect', forbidden); monkeypatch.setattr(conversion, 'generate', forbidden)
    p = window.conversion_page
    first = tmp_path/'one.JPEG'; second = tmp_path/'two.png'; third = tmp_path/'three.webp'
    for path in (first, second, third): path.write_bytes(b'not decoded by drop')
    archive = tmp_path/'archive.txt'; window.set_paths([archive]); window.navigate(5)
    p.set_paths([first]); p.fields.destination.setText(str(tmp_path/'output'))
    p.set_preview([], object()); generation = p.generation
    changes = []; previews = []; executions = []
    p.changed.connect(lambda: changes.append(True)); p.previewRequested.connect(previews.append); p.executeRequested.connect(executions.append)
    targets = {'page': p, 'select': p.select_button, 'list': p.sources, 'sources_viewport': p.sources.viewport(),
               'results_viewport': p.results.viewport(), 'destination': p.fields.destination, 'window': window}
    assert send_drop(app, targets[target], [QUrl.fromLocalFile(str(second)), QUrl.fromLocalFile(str(third))]) == (True, True)
    assert p.paths == (str(first), str(second), str(third))
    assert p.generation == generation + 1 and changes == [True]
    assert p._token is None and not p.execute_button.isEnabled() and p.results.rowCount() == 0
    assert not previews and not executions
    assert window.pages.currentWidget() is p and window.paths == (archive,)
    assert p.fields.destination.text() == str(tmp_path/'output')


def test_image_drop_windows_path_duplicates_do_not_change_selection(app, window, tmp_path):
    p = window.conversion_page; path = tmp_path/'Photo.PNG'; path.write_bytes(b'fixture')
    p.set_paths([path]); generation = p.generation; changes = []; p.changed.connect(lambda: changes.append(True))
    assert send_drop(app, p.sources.viewport(), [QUrl.fromLocalFile(str(path).upper().replace('/', '\\')),
        QUrl.fromLocalFile(str(path))]) == (True, True)
    assert p.paths == (str(path),) and p.generation == generation and changes == []
    assert window.pages.currentWidget() is p and window.paths == ()


@pytest.mark.parametrize('kind,expected', [('unsupported', 'JPEG'), ('directory', '文件夹'), ('remote', '本地'), ('unc', '本地'), ('mixed', 'JPEG')])
def test_invalid_drop_rejects_whole_batch_and_preserves_preview(app, window, tmp_path, kind, expected):
    p = window.conversion_page; original = tmp_path/'original.png'; original.write_bytes(b'fixture')
    p.set_paths([original]); token = object(); p.set_preview([], token); generation = p.generation
    directory = tmp_path/'folder.png'; directory.mkdir()
    (tmp_path/'valid.png').write_bytes(b'fixture')
    bad = {'unsupported': QUrl.fromLocalFile(str(tmp_path/'video.mp4')), 'directory': QUrl.fromLocalFile(str(directory)),
           'remote': QUrl('https://example.com/photo.png'), 'unc': QUrl('file://server/share/photo.png'),
           'mixed': QUrl.fromLocalFile(str(tmp_path/'video.mp4'))}[kind]
    urls = [QUrl.fromLocalFile(str(tmp_path/'valid.png')), bad] if kind == 'mixed' else [bad]
    assert send_drop(app, p.fields.destination, urls) == (False, False)
    assert p.paths == (str(original),) and p._token is token and p.generation == generation
    assert p.fields.destination.text() == '' and expected in p.error_label.text()


@pytest.mark.parametrize('state', ['busy', 'retiring', 'quit'])
def test_busy_or_retired_page_rejects_drop_without_editing_destination(app, window, tmp_path, state):
    p = window.conversion_page; p.set_paths([tmp_path/'before.png']); generation = p.generation
    if state == 'busy': p.set_busy(True)
    elif state == 'retiring': window.automation.accepting = False
    else: window._quit_requested = True
    assert send_drop(app, p.fields.destination, [QUrl.fromLocalFile(str(tmp_path/'after.png'))]) == (False, False)
    assert p.paths == (str(tmp_path/'before.png'),) and p.generation == generation
    assert p.fields.destination.text() == '' and p.error_label.text()


def test_home_drop_keeps_archive_behavior(app, window, tmp_path):
    window.navigate(0); source = tmp_path/'archive.txt'
    assert send_drop(app, window, [QUrl.fromLocalFile(str(source))], require_move=False) == (True, True)
    assert window.pages.currentIndex() == 0 and window.paths == (source,)
    assert window.conversion_page.paths == ()


@pytest.mark.parametrize('actions,accepted', [(Qt.CopyAction | Qt.MoveAction, True), (Qt.MoveAction, False)])
def test_drop_never_reports_move_to_source(app, window, tmp_path, actions, accepted):
    p = window.conversion_page; source = tmp_path/'remain.png'; source.write_bytes(b'source survives')
    mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(source))])
    enter = QDragEnterEvent(QPoint(8, 8), actions, mime, Qt.LeftButton, Qt.ShiftModifier)
    assert enter.proposedAction() == Qt.MoveAction
    QApplication.sendEvent(p.sources.viewport(), enter)
    drop = QDropEvent(QPointF(8, 8), actions, mime, Qt.LeftButton, Qt.ShiftModifier)
    assert drop.proposedAction() == Qt.MoveAction
    QApplication.sendEvent(p.sources.viewport(), drop); settle(app)
    assert enter.isAccepted() is accepted and drop.isAccepted() is accepted
    if accepted:
        assert enter.dropAction() == Qt.CopyAction and drop.dropAction() == Qt.CopyAction
        assert p.paths == (str(source),)
    else: assert p.paths == () and p.error_label.text()
    assert source.read_bytes() == b'source survives'


@pytest.mark.parametrize('size', [(1080, 925), (800, 620)])
@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_three_sources_and_toggled_form_text_fit(app, window, size, theme):
    p = window.conversion_page; window.resize(*size); apply_theme(window, theme)
    p.set_paths(['C:/素材/一.jpg', 'C:/素材/二.png', 'C:/素材/三.webp'])
    p.fields.output_format.setCurrentIndex(1); settle(app)
    for mode in (0, 1, 0):
        p.fields.mode.setCurrentIndex(mode); settle(app)
        for combo in (p.fields.mode, p.fields.output_format):
            option = QStyleOptionComboBox(); combo.initStyleOption(option)
            edit = combo.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField, combo)
            assert edit.height() >= combo.fontMetrics().height(), (mode, edit.height(), combo.fontMetrics().height())
        assert p.fields.output_format.y() >= p.fields.mode.y() + p.fields.mode.height()
        viewport = p.sources.viewport().rect()
        assert all(viewport.contains(p.sources.visualItemRect(p.sources.item(i))) for i in range(3))
        assert all(p.sources.visualItemRect(p.sources.item(i)).height() - 5 >= p.sources.fontMetrics().height() for i in range(3))


@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_disabled_start_has_different_native_background_from_enabled(app, theme):
    p = ConversionPage(); apply_theme(p, theme); p.resize(850, 650); p.show(); settle(app)
    p.execute_button.clearFocus()
    disabled = p.execute_button.grab().toImage().pixelColor(16, p.execute_button.height()//2)
    assert not p.execute_button.isEnabled()
    p.set_preview([], object()); settle(app)
    enabled = p.execute_button.grab().toImage().pixelColor(16, p.execute_button.height()//2)
    assert p.execute_button.isEnabled() and disabled != enabled
    p.close()


def test_keep_missing_destination_is_actionable_and_replace_needs_none(app):
    p = ConversionPage(); p.set_paths(['C:/图片/a.png']); previews = []; p.previewRequested.connect(previews.append)
    p.preview_button.click()
    assert p.error_label.text() == '请选择输出文件夹' and previews == []
    p.fields.mode.setCurrentIndex(1); p.preview_button.click()
    assert len(previews) == 1 and previews[0].output_dir is None and not p.error_label.text()
