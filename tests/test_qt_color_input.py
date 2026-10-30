"""Colour edits stay connected to the model after typing and external picking."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

from conftest import wait_until


def items(parent):
    for child in parent.childItems():
        yield child
        yield from items(child)


def test_typed_hex_then_palette_eyedropper_and_profile_stay_synchronized(qapp,data_dir,monkeypatch):
    from qt_ui.host import QtHost
    from qt_ui import QML_DIR
    host=QtHost();engine=QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))
    for key,value in dict(uiState=host.state,bridge=host.bridge,launchVisible=False).items():
        engine.rootContext().setContextProperty(key,value)
    engine.load(QUrl.fromLocalFile(str(QML_DIR/'Main.qml')))
    window=engine.rootObjects()[0];window.show()
    try:
        qapp.processEvents()
        field=next(i for i in items(window.contentItem()) if i.objectName()=='targetField0')
        editor=next(i for i in items(field) if i.objectName()=='fieldEditor')
        editor.forceActiveFocus()
        QTest.keyClick(window,Qt.Key_A,Qt.ControlModifier)
        for character in '#123456':QTest.keyClick(window,character)
        assert host.cards[0].target.get()=='#123456'
        assert editor.property('text')=='#123456'
        assert host.bridge.openPicker(0)
        host.bridge.pickerColor(0,'#ABCDEF')
        qapp.processEvents()
        assert editor.property('text')=='#ABCDEF'
        host.close_inline_picker()
        monkeypatch.setattr(host,'pick_color',lambda callback:callback('#456789'))
        host.bridge.eyedropper(0)
        qapp.processEvents()
        assert editor.property('text')==host.cards[0].target.get()=='#456789'
        host.cards[0].target.set('#FEDCBA')
        qapp.processEvents()
        assert field.property('text')==editor.property('text')=='#FEDCBA'
        editor.forceActiveFocus()
        QTest.keyClick(window,Qt.Key_A,Qt.ControlModifier)
        for character in '#000000':QTest.keyClick(window,character)
        assert host.cards[0].target.get()=='#000000'
    finally:
        window.hide();host.shutdown()


@pytest.mark.parametrize('activation_ok',[True,False])
def test_eyedropper_hides_tool_and_activates_game_before_freezing_then_restores(qapp,monkeypatch,activation_ok):
    import window_target
    from qt_ui.eyedropper import QtEyedropper
    from PySide6.QtGui import QGuiApplication
    calls=[]
    class Window:
        visible=True
        def isVisible(self):return self.visible
        def hide(self):self.visible=False;calls.append('hide')
        def show(self):self.visible=True;calls.append('restore')
    window=Window();target=object()
    host=SimpleNamespace(server=SimpleNamespace(get=lambda:'tw'),selected_window=target,
        picking=True,busy=False,status=SimpleNamespace(configure=lambda **kw:calls.append('error')))
    monkeypatch.setattr(QGuiApplication,'topLevelWindows',staticmethod(lambda:[window]))
    monkeypatch.setattr(window_target,'resolve_target',lambda *a,**kw:target)
    monkeypatch.setattr(window_target,'activate_target_window',lambda t:calls.append('activate') or activation_ok)
    session=QtEyedropper(host,lambda value:calls.append(value))
    monkeypatch.setattr(session,'_capture',lambda:calls.append('capture'))
    session.start()
    if activation_ok:
        assert wait_until(qapp,lambda:'capture' in calls)
        assert calls[:3]==['hide','activate','capture'] and not window.visible
        session.cancel()
    assert wait_until(qapp,lambda:window.visible)
    assert not host.picking and calls.count('restore')==1
    if not activation_ok:assert 'capture' not in calls and 'error' in calls
