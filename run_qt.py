"""Qt Quick 启动入口。

    python run_qt.py

保留原 `run_studio.bat` 不动，便于随时对照。

打包（PyInstaller）后模块位于 ``sys._MEIPASS`` 根目录，QML 在
``qt_ui/qml``；源码运行时模块在 ``work/studio``，QML 与模块同目录。
下面按是否 frozen 解析两个路径，其他代码不感知差异。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, 'frozen', False))
if FROZEN:
    BASE = Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
    STUDIO = BASE
    QML_DIR = BASE / 'qt_ui' / 'qml'
else:
    BASE = Path(__file__).resolve().parent
    STUDIO = BASE / 'work' / 'studio'
    QML_DIR = STUDIO / 'qt_ui' / 'qml'

sys.path.insert(0, str(STUDIO))
os.chdir(STUDIO)


def main():
    # platform_win 必须在任何 GUI / 截图模块之前导入，建立物理像素感知。
    import platform_win  # noqa: F401

    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 所有控件都是自绘的（UiButton / UiCombo / UiSlider …），只需要
    # Controls 提供 Popup / ListView / ScrollBar 的骨架。用 Basic 风格：
    #   1) 允许自定义 ScrollBar 的 contentItem（原生风格会报
    #      "The current style does not support customization"）；
    #   2) 不加载平台主题，启动更快、跨机器表现一致。
    QQuickStyle.setStyle('Basic')

    qml_dir = QML_DIR
    app = QGuiApplication(sys.argv)
    app.setApplicationName('染色工坊')
    app.setOrganizationName('MinamiChiwa')

    from qt_ui.host import QtHost

    host = QtHost()

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir))
    ctx = engine.rootContext()
    # 注意：属性名必须是 uiState —— `state` 是 Qt Quick 的 Item 内置属性
    # （QML 状态机），用它会遮蔽注入对象，导致所有 themeColor() 调用返回
    # undefined、界面回退成默认白色。
    ctx.setContextProperty('uiState', host.state)
    ctx.setContextProperty('bridge', host.bridge)

    warnings = []
    engine.warnings.connect(lambda ws: warnings.extend(str(w.toString()) for w in ws))

    engine.load(QUrl.fromLocalFile(str(qml_dir / 'Main.qml')))
    if not engine.rootObjects():
        print('QML 加载失败', file=sys.stderr)
        for w in warnings[:10]:
            print('  ', w, file=sys.stderr)
        return 2

    window = engine.rootObjects()[0]
    host.attach_window(window)

    # 启动自检：确认注入的属性真的能被 QML 读到。
    # 属性名写错时 QML 不会报错，只会静默拿到 undefined，
    # 表现为「界面变成浅色、文字发白」——必须在这里拦住。
    problems = []
    if window.property('uiStateReady') is not True:
        problems.append('uiState 未注入或被遮蔽（检查 setContextProperty 的名字）')
    if warnings:
        problems.append(f'QML 告警 {len(warnings)} 条，首条：{warnings[0][:120]}')
    if problems:
        print('启动自检未通过：', file=sys.stderr)
        for p in problems:
            print('  -', p, file=sys.stderr)
        if window.property('uiStateReady') is not True:
            return 3

    host.state.apply(appSubtitle=f'瑪奇 Mobile  /  by 南千和  ·  v{host.state.appVersion}')

    host.start_services()
    app.aboutToQuit.connect(host.shutdown)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())