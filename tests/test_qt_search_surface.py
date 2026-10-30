"""Player-visible overlay contracts and stable resize layout, without a game."""
import json
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine

from conftest import wait_until


@pytest.fixture
def overlay(qapp, data_dir, monkeypatch):
    from qt_ui.host import QtHost
    from qt_ui.overlay import QtOverlay
    host = QtHost()
    calls = []
    host.request_native_retry = lambda: calls.append('retry')
    surface = QtOverlay(host, lambda: calls.append('stop'), settings_path=data_dir / 'settings.json')
    monkeypatch.setattr(surface, '_prepare_native', lambda: None)
    surface.begin([{'enabled': True}] * 3)
    yield surface, calls
    surface.dismiss()
    surface._position_timer.stop()
    surface._alpha_timer.stop()
    host.shutdown()


@pytest.mark.parametrize('payload', [
    {'effective_deadline': 165.0},
    {'budget': {'remaining_seconds': 65, 'at_monotonic': 100}},
    {'remaining': 65, 'at_monotonic': 100},
    {'session_deadline_monotonic': 165.0},
])
def test_timer_uses_observation_time_not_queue_time(overlay, monkeypatch, payload):
    surface, _ = overlay
    monkeypatch.setattr(time, 'monotonic', lambda: 105.0)
    surface.handle('native_progress', {'stage': 'search', **payload})
    assert surface.state.remaining == '01:00'
    surface.heartbeat()
    assert surface.state.remaining == '01:00'


def test_unknown_scan_time_is_not_game_countdown(overlay):
    surface, _ = overlay
    surface.handle('native_progress', {'stage': 'discovery', 'deadline_monotonic': time.monotonic() + 300})
    assert surface._deadline is None and surface.state.remaining == '--:--'


def test_retry_and_timer_correction_reach_overlay(overlay):
    surface, calls = overlay
    surface.handle('native_retry_available', {'enabled': True, 'effective_deadline': time.monotonic() + 65})
    assert surface.state.retryEnabled
    surface.requestRetry()
    assert calls == ['retry']
    surface.mark_retry_requested()
    assert not surface.state.retryEnabled
    surface.handle('native_retry_reset', {'status': 'searching'})
    surface.handle('native_timer', {'effective_deadline': time.monotonic() + 35})
    assert surface.state.remaining in ('00:34', '00:35')


@pytest.mark.parametrize('kind,result', [
    ('native_result', {'stop_reason': 'discovery_read_failure'}),
    ('screenshot_result', {'stop_reason': 'interrupted'}),
    ('single_verified', {'verified': True, 'outcome': 'matched'}),
])
def test_result_then_finished_keeps_factual_terminal_status(overlay, kind, result):
    surface, _ = overlay
    surface.handle(kind, result)
    title = surface.state.title
    surface.handle('native_progress', {'stage': 'discovery'})
    surface.handle('finished', {})
    assert surface.state.title == title
    assert surface.state.stopped and not surface.state.running
    assert not surface.state.retryEnabled and not surface._heartbeat_timer.isActive()
    assert title not in ('准备寻色', '等待染色界面')


def test_next_round_resets_warning_and_saves_drag_position(overlay, qapp):
    surface, _ = overlay
    surface.handle('native_result', {'stop_reason': 'discovery_read_failure'})
    surface.begin([{'enabled': True}] * 3)
    assert not surface.state.warn and not surface.state.stopped
    from qt_ui import window_fx
    assert wait_until(qapp, lambda: id(surface._window) not in window_fx._ANIMS)
    surface._window.setPosition(100, 130)
    assert wait_until(qapp, lambda: surface.settings_path.exists())
    assert wait_until(qapp, lambda: json.loads(surface.settings_path.read_text(encoding='utf-8')).get('overlay_position') == [100, 130])


def test_provisional_screenshot_result_keeps_retry_and_timer_live(overlay):
    surface,_=overlay
    surface.handle('screenshot_result',dict(stop_reason=None,outcome='compromise',verified=True))
    surface.handle('native_retry_available',dict(enabled=True,effective_deadline=time.monotonic()+25))
    assert not surface._terminal and surface.state.retryEnabled
    assert surface._heartbeat_timer.isActive()


@pytest.mark.parametrize('kind',['finished','palette_ended'])
def test_round_completion_hides_overlay_and_next_round_can_open(overlay,kind):
    surface,calls=overlay
    if kind=='finished':surface.handle('finished',{})
    else:surface.handle('native_result',dict(stop_reason='palette_ended'))
    assert not surface._window.isVisible() and surface._dismissed and calls==[]
    surface.begin([{'enabled':True}]*3)
    assert surface._window.isVisible() and not surface._dismissed


def test_header_close_works_after_terminal_result(overlay,qapp):
    from PySide6.QtCore import QPointF,Qt
    from PySide6.QtTest import QTest
    from qt_ui import window_fx
    surface,calls=overlay
    surface.handle('native_result',dict(stop_reason='discovery_read_failure'))
    assert wait_until(qapp,lambda:id(surface._window) not in window_fx._ANIMS)
    button=next(i for i in visual_items(surface._window.contentItem()) if i.objectName()=='overlayCloseButton')
    point=button.mapToScene(QPointF(button.width()/2,button.height()/2)).toPoint()
    QTest.mouseClick(surface._window,Qt.LeftButton,Qt.NoModifier,point)
    assert not surface._window.isVisible() and calls==[]


def test_native_overlay_is_interactive_without_activation(overlay, monkeypatch):
    import ctypes
    import overlay_native
    from qt_ui.overlay import QtOverlay
    surface, _ = overlay
    class Ancestor:
        def __call__(self, *args):
            return 123
    fake = SimpleNamespace(user32=SimpleNamespace(GetAncestor=Ancestor()))
    monkeypatch.setattr(ctypes, 'windll', fake)
    policies = []
    monkeypatch.setattr(overlay_native, 'configure_overlay', lambda hwnd, **kw: policies.append(kw) or {'hwnd': hwnd})
    monkeypatch.setattr(overlay_native, 'unregister_overlay', lambda hwnd: None)
    QtOverlay._prepare_native(surface)
    assert policies == [{'passive': False}]


def visual_items(item):
    for child in item.childItems():
        yield child
        yield from visual_items(child)


def test_overlay_mouse_buttons_dispatch_stop_and_retry(overlay, qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    from qt_ui import window_fx
    surface, calls = overlay
    assert wait_until(qapp, lambda: id(surface._window) not in window_fx._ANIMS)
    surface.handle('native_retry_available', {'enabled': True})
    QTest.qWait(40)  # Flush changed and the following scene-graph polish.
    def click(name):
        item = next(i for i in visual_items(surface._window.contentItem()) if i.objectName() == name)
        assert item.isVisible() and item.isEnabled()
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(surface._window, Qt.LeftButton, Qt.NoModifier, point)
        qapp.processEvents()
    click('overlayRetryButton')
    click('overlayStopButton')
    assert calls == ['retry', 'stop']


def test_opacity_slider_updates_window_label_and_saved_setting(overlay, qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    from qt_ui import window_fx
    from qt_ui.overlay import QtOverlay
    surface, _ = overlay
    window = surface._window
    assert wait_until(qapp, lambda: id(window) not in window_fx._ANIMS)
    items = list(visual_items(window.contentItem()))
    gear = next(i for i in items if i.objectName() == 'overlayOpacityButton')
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                     gear.mapToScene(QPointF(gear.width()/2, gear.height()/2)).toPoint())
    QTest.qWait(40)
    slider = next(i for i in items if i.objectName() == 'overlayOpacitySlider')
    assert slider.isVisible() and slider.property('stepSize') == .01
    for ratio, expected in ((0, .65), (.43, .80), (1, 1.0)):
        point = slider.mapToScene(QPointF(min(slider.width()-1, ratio*slider.width()), slider.height()/2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        qapp.processEvents()
        assert surface.alpha == pytest.approx(expected, abs=.001)
        assert window.opacity() == pytest.approx(expected, abs=.001)
        assert slider.property('value') == pytest.approx(expected, abs=.001)
        assert any(i.property('text') == f'{round(expected*100)}%' for i in items)
    assert wait_until(qapp, lambda: surface.settings_path.exists() and
                      json.loads(surface.settings_path.read_text(encoding='utf-8')).get('overlay_alpha') == 1)
    restored = QtOverlay(surface.host, lambda: None, settings_path=surface.settings_path)
    assert restored.alpha == 1
    # A manual adjustment during the entry fade must remain in effect.
    surface.begin([])
    surface.set_opacity(.73)
    QTest.qWait(400)
    assert window.opacity() == pytest.approx(.73)
    surface.set_opacity(float('nan'))
    assert surface.alpha == .73


def test_resize_preserves_cards_and_exposes_eight_edges(qapp, data_dir):
    from qt_ui import QML_DIR
    from qt_ui.host import QtHost
    host = QtHost()
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    for key, value in {'uiState': host.state, 'bridge': host.bridge, 'launchVisible': True}.items():
        engine.rootContext().setContextProperty(key, value)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / 'Main.qml')))
    window = engine.rootObjects()[0]
    def cards():
        return [i for i in visual_items(window.contentItem()) if i.objectName() in ('card0', 'card1', 'card2')]
    try:
        window.resize(1100, 740)
        qapp.processEvents()
        before = cards()
        assert len(before) == 3
        destroyed = []
        for card in before:
            card.destroyed.connect(lambda: destroyed.append(True))
        for width in (960, 560, 400, 1100):
            window.resize(width, 740)
            qapp.processEvents()
            assert set(map(id, cards())) == set(map(id, before))
        edges = [i for i in visual_items(window.contentItem()) if i.objectName().startswith('resizeEdge_')]
        assert len(edges) == 8 and all(i.width() > 0 and i.height() > 0 for i in edges)
        assert destroyed == [] and warnings == []
        # The offscreen plugin declines native resizing. The global-coordinate
        # fallback must settle without feeding the moving handle into itself.
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, QPoint(1097, 370))
        for _ in range(3):
            QTest.mouseMove(window, QPoint(1057, 370))
            qapp.processEvents()
            assert window.width() == 1060
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(1057, 370))
    finally:
        window.hide()
        host.shutdown()
