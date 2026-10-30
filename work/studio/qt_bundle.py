"""Trim the PySide6 payload PyInstaller collects, then prove the rest still links.

PyInstaller's QML hook copies every Qt module and its DLLs (WebEngine alone is
about 200 MB). The app only imports QtQuick, QtQuick.Controls (Basic style),
QtQuick.Layouts and QtQuick.Window, so everything matched below is removed.
``check_dependencies`` then fails the build if any kept binary imports a DLL
that is no longer in the package.
"""
import fnmatch
import shutil
from pathlib import Path

# Relative to _internal/PySide6. Patterns without a slash match file names in
# the PySide6 root; patterns with a slash match paths (files or directories).
UNUSED = (
    'Qt6WebEngine*', 'QtWebEngine*', 'QtWebEngineProcess.exe', 'Qt6WebChannel*', 'Qt6WebSockets*', 'Qt6WebView*',
    'Qt6Pdf*', 'QtPdf*',
    'Qt63D*', 'Qt3D*', 'Qt6Quick3D*', 'QtQuick3D*',
    'Qt6Charts*', 'QtCharts*', 'Qt6Graphs*', 'QtGraphs*', 'Qt6DataVisualization*', 'QtDataVisualization*',
    'Qt6Multimedia*', 'QtMultimedia*', 'Qt6SpatialAudio*', 'QtSpatialAudio*',
    'Qt6Location*', 'QtLocation*', 'Qt6Positioning*', 'QtPositioning*',
    'Qt6TextToSpeech*', 'QtTextToSpeech*', 'Qt6Sensors*', 'QtSensors*',
    'Qt6Test*', 'QtTest*', 'Qt6QuickTest*',
    'Qt6RemoteObjects*', 'QtRemoteObjects*', 'Qt6Scxml*', 'QtScxml*', 'Qt6StateMachine*', 'QtStateMachine*',
    'Qt6VirtualKeyboard*', 'Qt6Core5Compat*', 'Qt6Labs*', 'Qt6QuickDialogs2*',
    'Qt6QuickTimeline*', 'Qt6QuickParticles*', 'Qt6ShaderTools*',
    'Qt6QuickControls2Fluent*', 'Qt6QuickControls2Imagine*', 'Qt6QuickControls2Material*',
    'Qt6QuickControls2Universal*', 'Qt6QuickControls2Fusion*', 'Qt6QuickControls2IOS*', 'Qt6QuickControls2MacOS*',
    'Qt6QuickControls2Windows*',
    'Qt6QmlDesignSupport*', 'Qt6QuickShapesDesignHelpers*', 'Qt6QmlLocalStorage*', 'Qt6Sql*', 'Qt6QmlXmlListModel*',
    'opengl32sw.dll', 'translations/',
    'plugins/qmltooling/', 'plugins/platforminputcontexts/', 'plugins/imageformats/qpdf.dll', 'plugins/sqldrivers/',
    'qml/QtWebChannel/', 'qml/QtWebSockets/', 'qml/QtQuick/Scene2D/', 'qml/QtQuick/Scene3D/',
    'qml/QtQuick/Shapes/DesignHelpers/', 'qml/QtQml/DesignSupport/', 'qml/QtQuick/LocalStorage/', 'qml/QtQml/XmlListModel/',
    'qml/QtWebEngine/', 'qml/QtWebView/', 'qml/QtQuick/Pdf/', 'qml/Qt3D/', 'qml/QtQuick3D/',
    'qml/QtCharts/', 'qml/QtGraphs/', 'qml/QtDataVisualization/', 'qml/QtMultimedia/',
    'qml/QtLocation/', 'qml/QtPositioning/', 'qml/QtTextToSpeech/', 'qml/QtSensors/', 'qml/QtTest/',
    'qml/QtRemoteObjects/', 'qml/QtScxml/', 'qml/QtQml/StateMachine/', 'qml/QtQuick/VirtualKeyboard/',
    'qml/Qt5Compat/', 'qml/Qt/labs/', 'qml/QtQuick/Dialogs/', 'qml/QtQuick/Timeline/', 'qml/QtQuick/Particles/',
    'qml/QtQuick/Controls/FluentWinUI3/', 'qml/QtQuick/Controls/Imagine/', 'qml/QtQuick/Controls/Material/',
    'qml/QtQuick/Controls/Universal/', 'qml/QtQuick/Controls/Fusion/', 'qml/QtQuick/Controls/iOS/',
    'qml/QtQuick/Controls/macOS/', 'qml/QtQuick/Controls/Windows/',
)


def prune(pyside):
    """Delete unused Qt modules under ``pyside``; return the number of bytes removed."""
    pyside = Path(pyside)
    removed = 0
    for pattern in UNUSED:
        if '/' in pattern:
            target = pyside / pattern.rstrip('/')
            matches = [target] if target.exists() else []
        else:
            matches = [p for p in pyside.iterdir() if fnmatch.fnmatch(p.name, pattern)]
        for path in matches:
            if path.is_dir():
                removed += sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                shutil.rmtree(path)
            else:
                removed += path.stat().st_size
                path.unlink()
    return removed


def check_dependencies(internal):
    """Raise if a kept Qt/PySide binary imports a Qt DLL that is not in the package."""
    import pefile
    internal = Path(internal)
    present = {p.name.casefold() for p in internal.rglob('*') if p.is_file()}
    missing = {}
    for binary in internal.rglob('*'):
        if binary.suffix.casefold() not in ('.dll', '.pyd') or not binary.is_file():
            continue
        pe = pefile.PE(str(binary), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
            name = entry.dll.decode().casefold()
            if name.startswith(('qt6', 'pyside6', 'shiboken6')) and name not in present:
                missing.setdefault(name, []).append(str(binary.relative_to(internal)))
        pe.close()
    if missing:
        raise RuntimeError('Pruned Qt package is missing DLLs: ' + repr(missing))
