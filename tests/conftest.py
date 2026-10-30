"""Shared setup: source paths, offscreen Qt and an isolated data directory."""
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / 'work' / 'studio'
for path in (str(STUDIO), str(ROOT), str(Path(__file__).resolve().parent)):
    if path not in sys.path:
        sys.path.insert(0, path)
# Qt windows render without a display; tests never show anything on screen.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@pytest.fixture(scope='session')
def qapp():
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuickControls2 import QQuickStyle
    QQuickStyle.setStyle('Basic')
    app = QGuiApplication.instance() or QGuiApplication([sys.argv[0]])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point the business layer at an empty data directory instead of work/studio/data."""
    import business
    data = tmp_path / 'data'
    data.mkdir()
    monkeypatch.setattr(business, 'DATA', data)
    return data


def wait_until(app, condition, timeout=3.0):
    """Run the Qt event loop until condition() is true or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    app.processEvents()
    return condition()
