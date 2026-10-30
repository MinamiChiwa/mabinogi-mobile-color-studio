# Qt 界面说明

界面层位于 `work/studio/qt_ui/`，入口是 `work/studio/app.py`。寻色、判色、方案读写和事件分发在 `work/studio/business.py`；界面层只做展示与生命周期，不复制业务判断。

## 启动顺序

`app.py` 被直接运行（源码或 ColorStudio.exe）时依次：

1. `update_bootstrap.dispatch()`：处理 `--update-health-check`，以及中断更新的恢复。必须在导入 Qt、OpenCV 等会被更新替换的依赖之前执行。
2. `--screenshot-preflight` / `--native-preflight`：预检模式，执行后直接退出。
3. 创建 `QGuiApplication`（Basic 风格、`setQuitOnLastWindowClosed(False)`），构造 `QtHost`，注入 `uiState`、`bridge`、`launchVisible` 后加载 `Main.qml`。
4. `host.start_services()`：启动事件轮询；正常启动时开启热键并在打包运行时静默检查更新。

上下文属性不能命名为 `state`：那是 QML `Item` 的内置属性，会遮蔽注入对象，界面会静默退回默认样式。`Main.qml` 的 `uiStateReady` 用于启动时拦住这类问题。

## 生命周期约定

- **关闭**：标题栏关闭、任务栏关闭、Alt+F4 都经过 `Main.qml` 的 `onClosing` → `bridge.requestClose()` → `QtHost.close()`。正在寻色时先 `stop(source='window_close')`，每 250ms 重试直到工作线程结束，再保存设置、停止热键并退出。不要在别处直接调用 `QGuiApplication.quit()`。
- **更新后首次启动**（`--update-ready <事务目录>`）：窗口保持隐藏，开始按钮禁用；`signal_ready()` 通知更新助手，随后每 100ms 读取事务状态。`committed` 后迁移策略默认值、启动热键并显示窗口；助手已退出却未提交（已回滚）时直接关闭。
- **安装更新**：更新器发出 `exit_requested` 时走同一个 `close()`。

## 目录

```
work/studio/app.py            入口：更新引导、预检模式、QML 装配
work/studio/business.py       业务方法（QtHost 的基类）
work/studio/qt_ui/
├── __init__.py               QML_DIR（源码与打包后相同的相对位置）
├── host.py                   QtHost / QtCard：业务方法的界面投影、计时器、启动与关闭
├── core.py                   UiState（主题、文案、卡片字段）与变量/控件适配器
├── bridge.py                 QML → Python 的唯一动作通道（全部 @Slot）
├── dialogs.py                教程/支持、寻色记录、方案、窗口选择、色板查看器
├── overlay.py                寻色浮窗
├── eyedropper.py             屏幕吸管
├── picker.py                 目标色面板数据（色域 / 常用色 / HSL）
├── update.py                 软件更新对话框
├── window_fx.py              弹窗出现动画、定位与边界夹取
├── i18n_qt.py                界面短标签的补充词表，叠加在 i18n.py 之上
└── qml/                      QML 组件（Main、RegionCard、Overlay、UpdateDialog、Ui* 控件等）
```

## 三层结构

1. **QML 视图**：只做布局与动画。文字一律 `Loc.t('简体中文原文')`，颜色一律 `uiState.themeColor('token', uiState.appearance)`。
2. **状态投影**（`core.UiState`）：把界面需要的数据压成属性；`state.card(index, **changes)` 写单张卡。同一轮事件循环内的多次 `changed` 合并成一次发射，不要改回逐次 emit，否则长时间运行会越来越卡。
3. **宿主**（`host.QtHost(business.Business, QObject)`）：提供业务方法读写的 `self.status`、`self.start`、`self.cards` 等适配器，以及 `after()` / `after_cancel()`。`after()` 的 QTimer 用完必须 `deleteLater()`；`tick` 只启动一次、自行续期。

动作方向只有一条：QML 调 `bridge.xxx()` → `QtHost` → 业务方法 → `UiState` 发射 → QML 绑定重算。

## 浮窗、吸管与目标色面板

- **寻色浮窗**（`overlay.py` + `Overlay.qml`）：`QtOverlay.handle()` 只处理要显示的事件，结果判定在 `Business.handle_event`。候选方案点击前必须已有 `batch_id` / `default_candidate_id`。截图排除、不抢焦点、置顶由 `overlay_native` 注册。出场动画的终点透明度读用户设置。
- **吸管**（`eyedropper.py` + `Eyedropper.qml`）：冻结整块虚拟桌面，经 `QQuickImageProvider` 交给 QML；取色用 `GetCursorPos` 的物理坐标映射到冻结图，保证缩放下命中单个物理像素。`confirm/cancel` 把窗口关闭和引擎释放排到下一轮事件循环，在 JS 栈里同步析构引擎会崩溃；这些方法必须带 `@Slot`。
- **HSL 滑杆**（`InlineColorPicker.qml` + `picker.py`）：`Repeater.model` 只能是静态 key 列表，否则拖动时委托重建、拖不动；三条滑杆始终可拖，中性色只影响提示文案。

## 打包

`work/studio/build_release.py` 以 `app.py` 为入口，`qt_ui/qml` 作为数据目录随包分发，排除 tkinter / customtkinter。PyInstaller 的 QML 钩子会带上全部 Qt 模块（WebEngine 约 200 MB），构建后由 `qt_bundle.prune()` 删除未使用的模块，再用 `qt_bundle.check_dependencies()` 确认保留的 Qt 二进制所需 DLL 都在包内，缺失即构建失败；PySide6 部分由约 395 MB 降到约 78 MB。界面若新增 QML import（例如 `QtQuick.Dialogs`），需同步调整 `qt_bundle.UNUSED`。打包后 `qt_ui/__file__` 位于 `_MEIPASS/qt_ui`，`QML_DIR` 无需区分源码与打包。更新健康检查（`update_bootstrap.qml_health_check`）会在无窗口状态下编译全部 QML，损坏的界面文件会让更新回滚，而不是提交后打不开。

Qt for Python 以 LGPL-3.0 使用，DLL 未修改、可替换；构建时写入 `THIRD_PARTY/PySide6/NOTICE.txt`。
