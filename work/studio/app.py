"""染色工坊入口：更新引导 → 预检模式 → Qt 界面。

源码运行：``run_studio.bat`` 或 ``python work/studio/app.py``；
打包后同一文件就是 ColorStudio.exe 的入口脚本。
"""
import sys
if __name__ == '__main__':
    # 必须先于 Qt / OpenCV 等可被更新替换的依赖：处理健康检查与中断更新的恢复。
    from update_bootstrap import dispatch
    _bootstrap_exit = dispatch()
    if _bootstrap_exit is not None:
        raise SystemExit(_bootstrap_exit)
import platform_win  # noqa: F401  截图与 GUI 之前建立物理像素感知
if __name__ == '__main__' and '--screenshot-preflight' in sys.argv:
    from screenshot_preflight import main as screenshot_preflight_main
    raise SystemExit(screenshot_preflight_main([arg for arg in sys.argv[1:] if arg != '--screenshot-preflight']))
if __name__ == '__main__' and '--native-preflight' in sys.argv:
    from native_preflight import main as native_preflight_main
    raise SystemExit(native_preflight_main([arg for arg in sys.argv[1:] if arg != '--native-preflight']))


def main():
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    # 控件全部自绘，Controls 只提供 Popup / ListView / ScrollBar 骨架；
    # Basic 风格允许自定义 contentItem，且不加载平台主题。
    QQuickStyle.setStyle('Basic')

    app = QGuiApplication(sys.argv)
    app.setApplicationName('染色工坊')
    app.setOrganizationName('MinamiChiwa')
    # 关闭由 QtHost.close() 收尾（先停寻色、保存设置），不能因窗口隐藏就退出。
    app.setQuitOnLastWindowClosed(False)

    from qt_ui import QML_DIR
    from qt_ui.host import QtHost

    host = QtHost()
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))
    ctx = engine.rootContext()
    # 不能叫 state：那是 QML Item 的内置属性，会遮蔽注入对象。
    ctx.setContextProperty('uiState', host.state)
    ctx.setContextProperty('bridge', host.bridge)
    # 更新健康确认期间窗口保持隐藏，提交后由 QtHost 显示。
    ctx.setContextProperty('launchVisible', not host.update_health_pending)

    warnings = []
    engine.warnings.connect(lambda ws: warnings.extend(str(w.toString()) for w in ws))
    engine.load(QUrl.fromLocalFile(str(QML_DIR / 'Main.qml')))
    if not engine.rootObjects():
        print('QML 加载失败', file=sys.stderr)
        for warning in warnings[:10]:
            print('  ', warning, file=sys.stderr)
        return 2
    window = engine.rootObjects()[0]
    if window.property('uiStateReady') is not True:
        print('uiState 未注入或被遮蔽（检查 setContextProperty 的名字）', file=sys.stderr)
        return 3
    for warning in warnings[:10]:
        print('QML 告警：', warning, file=sys.stderr)

    host.attach_window(window)
    host.start_services()
    app.aboutToQuit.connect(host.shutdown)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
