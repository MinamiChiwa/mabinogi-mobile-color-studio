"""Qt application lifecycle: QML integrity, closing safely, update confirmation, update dialog."""
import json
import sys

import pytest
from PySide6.QtGui import QGuiApplication

from conftest import wait_until


class FakeThread:
    def __init__(self):
        self.started = False

    def start(self):
        self.started = True


class FakeWindow:
    def __init__(self):
        self.shown = False

    def show(self):
        self.shown = True


class FakeRunner:
    def __init__(self):
        self.stops = []

    def request_stop(self, source):
        self.stops.append(source)


@pytest.fixture
def quits(monkeypatch):
    calls = []
    monkeypatch.setattr(QGuiApplication, 'quit', staticmethod(lambda: calls.append(True)))
    return calls


@pytest.fixture
def make_host(qapp, data_dir, monkeypatch):
    """Build a QtHost against an empty data directory, without global hotkeys."""
    from qt_ui.host import QtHost
    hosts = []

    def make(argv=('app',)):
        monkeypatch.setattr(sys, 'argv', list(argv))
        host = QtHost()
        host._hotkey_thread = FakeThread()
        hosts.append(host)
        return host

    yield make
    for host in hosts:
        host.shutdown()


def test_every_qml_file_compiles(qapp):
    from update_bootstrap import qml_health_check
    qml_health_check()


def test_main_window_loads_without_warnings(qapp, make_host):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from qt_ui import QML_DIR

    host = make_host()
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    engine.addImportPath(str(QML_DIR))
    engine.rootContext().setContextProperty('uiState', host.state)
    engine.rootContext().setContextProperty('bridge', host.bridge)
    engine.rootContext().setContextProperty('launchVisible', False)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / 'Main.qml')))
    qapp.processEvents()
    assert engine.rootObjects() and engine.rootObjects()[0].property('uiStateReady') is True
    assert warnings == []


def test_close_while_searching_stops_first_then_quits(qapp, make_host, quits):
    host = make_host()
    host.busy, host.runner = True, FakeRunner()

    host.close()
    assert host.runner.stops == ['window_close'] and quits == []

    host.busy = False  # the worker reports 'finished'
    assert wait_until(qapp, lambda: quits == [True])
    assert host._hotkeys_stop.is_set()


def test_close_when_idle_saves_profile_and_quits(qapp, make_host, quits, data_dir):
    host = make_host()
    host.cards[0].target.set('#123456')
    host.close()
    assert quits == [True]
    assert json.loads((data_dir / 'profile.json').read_text(encoding='utf-8'))['regions'][0]['target'] == '#123456'


def update_transaction(tmp_path, status):
    tx = tmp_path / 'tx'
    tx.mkdir()
    (tx / 'transaction.json').write_text(json.dumps({'token': 't', 'version': '0.5.0'}), encoding='utf-8')
    (tx / 'state.json').write_text(json.dumps({'status': status}), encoding='utf-8')
    return tx


def test_update_ready_waits_for_commit_before_enabling(qapp, make_host, tmp_path, monkeypatch, quits):
    import update_bootstrap
    tx = update_transaction(tmp_path, 'pending_health')
    ready = []
    monkeypatch.setattr(update_bootstrap, 'signal_ready', ready.append)
    monkeypatch.setattr(update_bootstrap, 'helper_alive', lambda _tx: True)
    host = make_host(('app', '--update-ready', str(tx)))
    host.window = FakeWindow()
    monkeypatch.setattr(host.updater, 'check', lambda *a, **k: None)

    host.start_services()
    assert wait_until(qapp, lambda: ready == [tx])
    assert host.update_health_pending and not host._hotkey_thread.started
    assert host.state.startEnabled is False

    (tx / 'state.json').write_text(json.dumps({'status': 'committed'}), encoding='utf-8')
    assert wait_until(qapp, lambda: host.window.shown)
    assert not host.update_health_pending and host._hotkey_thread.started
    assert host.state.startEnabled is True and quits == []


def test_update_ready_exits_when_helper_rolls_back(qapp, make_host, tmp_path, monkeypatch, quits):
    import update_bootstrap
    tx = update_transaction(tmp_path, 'pending_health')
    monkeypatch.setattr(update_bootstrap, 'signal_ready', lambda _tx: None)
    monkeypatch.setattr(update_bootstrap, 'helper_alive', lambda _tx: False)
    host = make_host(('app', '--update-ready', str(tx)))
    host.window = FakeWindow()

    host.start_services()
    assert wait_until(qapp, lambda: quits == [True])
    assert not host.window.shown


def test_installer_exit_request_closes_app(qapp, make_host, quits):
    host = make_host()
    host.update_ui.handle({'kind': 'exit_requested'})
    assert quits == [True]


def test_header_update_button_opens_full_update_dialog(qapp, make_host):
    host = make_host()
    host.bridge.headerAction('update')
    qapp.processEvents()
    window = host.update_ui._window
    assert window is not None
    actions = [row['key'] for row in host.update_ui.view['actions']]
    assert actions == ['check', 'download', 'install', 'cancel', 'ignore', 'later']
    window.close()
