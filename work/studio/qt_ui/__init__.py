"""Qt Quick 界面层。"""
from pathlib import Path

# 源码运行时在 work/studio/qt_ui/qml；打包后 PyInstaller 把同一目录放在
# _MEIPASS/qt_ui/qml，__file__ 也随之落在 _MEIPASS/qt_ui，两种情况共用此路径。
QML_DIR = Path(__file__).resolve().parent / 'qml'
