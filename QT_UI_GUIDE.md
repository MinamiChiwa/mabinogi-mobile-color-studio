# QT_UI_GUIDE · 染色工坊 Qt Quick 界面说明

本文档是 Qt 版界面的**唯一**说明文档，面向接手维护的人：

- 想知道 `qt_ui/` 里每个文件负责什么；
- 想改主窗口、寻色浮窗、吸管或目标色面板，但不想先读一万行代码；
- 想在本地跑起来，或打一个 Qt 版安装包。

> 说明范围：只讲**界面层**（`work/studio/qt_ui/` 与 `run_qt.py`）。
> 寻色算法（`vision.py`、`color_matching.py`、`palette.py`、`engine.py`、
> `atlas_*`、`native_live/`）与业务规则（`business.py`）保持原作者实现，本文不涉及。

---

## 1. 运行

### 1.1 环境

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10/11 x64（界面层依赖 Win32 物理像素与置顶窗口，其他平台不适用） |
| Python | 3.13 / 3.14（本机验证于 3.14.14） |
| 依赖 | `pip install -r requirements.txt`（含 `PySide6==6.12.0`） |
| OCR | 截图寻色需要 Tesseract-OCR；纯界面调试可不装 |
| 显示缩放 | 任意（125% / 150% 已适配），入口固定在 `PassThrough` 策略 |

### 1.2 启动

```bat
run_qt.bat            :: 推荐，自动用 .venv\Scripts\python.exe，找不到则回退 python
python run_qt.py      :: 等价的手动入口
```

`run_studio.bat` 启动的是**原作者 Tk 版**（`work/studio/app.py`），仅用于对照，不属于 Qt 交付物。

### 1.3 启动自检

`run_qt.py` 在 `app.exec()` 之前做三件事，任何一件失败都会直接退出并打印原因：

1. `QGuiApplication` + `QQuickStyle.setStyle('Basic')`：所有控件自绘，Basic 风格只提供
   `Popup` / `ListView` / `ScrollBar` 骨架（原生风格会拒绝自定义 `contentItem`）。
2. 注入上下文属性 `uiState`（状态投影）与 `bridge`（动作通道）。属性名**不能**叫 `state`
   ——那是 QML `Item` 的内置状态机属性，会把注入对象遮蔽，界面会静默退回浅色。
3. 加载 `Main.qml` 后校验 `window.property('uiStateReady')`，并收集 `engine.warnings`；
   有 QML 告警即视为启动失败（默认返回码 3），避免"界面能开但样式全错"。

### 1.4 配置与本地数据

| 路径 | 内容 | 是否进 Git |
|---|---|---|
| `work/studio/data/settings.json` | 语言、服务器、窗口位置/不透明度等界面偏好 | 否（`.gitignore` 已忽略） |
| `work/studio/data/profile.json` | 三张区域卡的当前目标色与参数 | 否 |
| `work/studio/data/history.json` | 寻色记录 | 否 |
| `work/studio/data/sessions/` | 每次寻色的截图、采样与结果 | 否 |

界面偏好读写集中在 `ui_settings.py`；语言切换由 `i18n.py` + `qt_ui/i18n_qt.py` 两级词典完成。

---

## 2. 目录结构

```
run_qt.py                     Qt 入口：路径解析（源码 / PyInstaller）、引擎装配、启动自检
run_qt.bat                    Windows 启动包装
work/studio/qt_ui/            Qt Quick 界面层（本目录之外都是原作者代码）
├── __init__.py
├── host.py                   宿主：QtHost / QtCard，接管界面并复用 business 的全部业务方法
├── core.py                   状态投影：UiState（主题、文案、卡片字段）+ Tk 变量替身（shim）
├── bridge.py                 QML → Python 的唯一动作通道（Bridge，全部 @Slot）
├── dialogs.py                对话框：教程/支持、寻色记录、染色方案、窗口选择、色板查看器
├── overlay.py                寻色浮窗（Qt 版 SearchOverlay）：事件接入 + 状态 + 计时
├── eyedropper.py             屏幕吸管：冻结截图 + 取色会话
├── picker.py                 目标色面板的数据源（9×5 色域 / 常用色 / HSL）
├── update.py                 软件更新面板（Qt 版 UpdateUI 的承载）
├── window_fx.py              弹窗/浮窗的出现动画、位置与边界夹取
├── i18n_qt.py                Qt 专用补充词表（EXTRA），与主词典 i18n.py 叠加
└── qml/                      QML 组件
    ├── qmldir                模块声明（把 Loc.qml 注册为单例）
    ├── Loc.qml                文案单例：Loc.t('原文')
    ├── Main.qml               主窗口（标题栏 / 环境条 / 三列卡片 / 运行栏 / 页脚）
    ├── RegionCard.qml         区域卡：目标色、模式、容差、替代色、目标色集合、读数
    ├── Popover.qml            浮层基座：按锚点自动选方向 + 半透明遮罩 + 出入场动画
    ├── InlineColorPicker.qml  就地展开的目标色面板（色域 / 常用色 / HSL 精调）
    ├── AtlasPanel.qml         目标色集合预览（浮层内容）
    ├── QuickPanel.qml         六个入口共用的紧凑浮层（窗口/方案/记录/教程/支持/更新）
    ├── Overlay.qml            寻色浮窗（阶段、进度条、候选方案、不透明度面板）
    ├── Eyedropper.qml         全屏取色层（冻结画面 + 十字准星 + 跟随标签）
    ├── Viewer.qml             允许色图查看器（缩放/拖动/悬停读色）
    ├── InfoDialog.qml         只读信息框（教程、支持）
    ├── HistoryDialog.qml      寻色记录列表
    ├── PresetDialog.qml       染色方案管理
    ├── WindowDialog.qml       游戏窗口选择
    ├── UpdateDialog.qml       软件更新（含 QML FileDialog 选离线包）
    ├── EnvWindowButton.qml    环境条「游戏窗口」按钮
    ├── UiButton.qml           按钮
    ├── UiCombo.qml            下拉
    ├── UiField.qml            HEX / 文本输入
    ├── UiSlider.qml           容差滑杆
    ├── UiCheck.qml            复选框
    ├── UiScrollBar.qml        细滚动条
    └── RoundedImage.qml       圆角图片（clip 只裁矩形，需自绘遮罩）
```

---

## 3. 核心组件

### 3.1 主窗口是怎么实现的

```
run_qt.py
  ├─ QGuiApplication + QQmlApplicationEngine（没有 QApplication、没有 QWidget）
  ├─ engine.rootContext().setContextProperty('uiState', host.state)
  ├─ engine.rootContext().setContextProperty('bridge',  host.bridge)
  └─ engine.load(qml/Main.qml) → host.attach_window(window)
```

分三层，改动时要看清自己改的是哪层：

1. **QML 视图**（`qml/Main.qml` + `RegionCard.qml` + `Ui*.qml`）
   只做布局与动画。所有文字过 `Loc.t('简体中文原文')`，颜色过
   `uiState.themeColor('token', uiState.appearance)`，从不写死主题色。

2. **状态投影**（`qt_ui/core.py` 的 `UiState`）
   一个 `QObject`，把整个界面需要的数据压成属性：`appearance`、`language`、
   `revision`、`cards`（`QVariantList`，每张卡一个 `dict`）、`status`、`footer` …
   `state.card(index, **changes)` 写单张卡的字段并触发 `cardsChanged`。
   为减少重绘，`UiState` 会把同一轮事件循环内的多次 `changed` 合并成一次发射
   （`_emit_pending` + `QTimer.singleShot(0, ...)`）——这是"长时间运行越来越卡"
   修复的关键，改动时不要退回逐次 `emit`。

3. **业务宿主**（`qt_ui/host.py` 的 `QtHost(core.Business, QObject)`）
   原来的 Tk `App` 是"业务 + 控件"混在一起；这里把 Tk 控件换成
   `MenuShim / SliderShim / CardLabelShim / NullShim`（`core.py`）等替身对象，
   于是 `business.py` 里那些 `self.card.status.configure(...)`、`self.q.get()`
   之类的调用可以原样执行，结果被替身转成 `UiState` 的字段。
   `QtCard`（`host.py:48`）同理：它继承 `core.RuleSource`，保证送进寻色引擎的
   `rule()` 字典与原版逐字一致。

**动作方向只有一条**：QML 调 `bridge.xxx(...)`（`bridge.py`，全部 `@Slot`）
→ `Bridge` 转发给 `QtHost` → 宿主改状态或调业务方法 → `UiState` 发射
→ QML 绑定自动重算。**没有** QML 直接改 Python 对象的写法。

### 3.2 寻色浮窗的通信机制

浮窗是独立窗口（`Overlay.qml`），由 `qt_ui/overlay.py` 驱动，替代原 `search_overlay.SearchOverlay`。

```
业务线程 / 引擎
   └─ 事件 dict  ──► QtOverlay.handle(kind, data)      （overlay.py:560）
                        ├─ 进度类：atlas_progress / single_progress /
                        │           native_progress / screenshot_progress
                        │           → update_activity() + progress_text() 写标题正文
                        ├─ 结束类：error / worker_failed / wait_timeout /
                        │           interrupted / done / finished
                        │           → 停心跳、置停止态、渲染收尾文案
                        └─ 其余事件交回 business.handle_event（判定逻辑仍归原作者）
   OverlayState（QObject）── 属性 + 信号 ──► Overlay.qml 绑定
```

要点：

- **状态与视图分离**：`OverlayState` 只存可显示字段（运行态、阶段、当前/总数、
  剩余时间、候选列表、不透明度），QML 只读；写入口都在 `QtOverlay` 的方法里。
- **候选方案**：`_candidate_rows()` 把引擎结果投影成 `[{id,title,details,summary,action,disabled}]`，
  点击后经 `chooseCandidate(id)` 回传；`batch_id` / `default_candidate_id` 必须先赋值，
  否则选择会被直接 return 掉。
- **进度条**：每阶段都要持续动。确定态按 `current/total` 填充并叠加常驻流光；
  不确定态用 `progressSlide` 往复。两个动画分别在 `Overlay.qml` 的 `progressFill`
  与 `progressSlide` 中，不要改成 `SequentialAnimation on x`（不支持 `onStopped`，
  容易一条动画播完就停住）。
- **计时**：`QtOverlay` 内部用**一个** `QTimer` 同时承担心跳与秒计时；
  早期版本在 `tick()` 里又 `after(60)` 自续，导致一秒内多次重入（实测 1 秒 135 次），
  改成"只踢一次、自续一次"。
- **窗口属性持久化**：位置在 `moveTo` 后写回，`set_opacity` 走 250ms 防抖落库；
  出场动画的终点透明度必须读用户设置（`slide_in(final_opacity=...)`），否则会把
  用户调好的不透明度覆盖成 1.0。
- **点击穿透 / 不抢焦点**：交给 `overlay_native`（原生服务），QML 侧不处理。

### 3.3 吸管准星的交互逻辑

`qt_ui/eyedropper.py` + `qml/Eyedropper.qml`，一次取色 = 一个 `QtEyedropper` 实例。

1. **冻结画面**：`ImageGrab.grab(all_screens=True)` 抓整块虚拟桌面（物理像素），
   通过 `FrozenProvider`（`QQuickImageProvider`）交给 QML。用 ImageProvider 而不是
   data URI，是因为整屏 base64 会卡首帧。
2. **全屏窗口对齐**：窗口几何按 `物理尺寸 / DPR` 设置，再用 `GetClientRect` +
   `ClientToScreen` 实测校验，不一致直接报错（宁可失败也不取错色）。
3. **坐标**：`preview(x, y)` 收 QML 逻辑坐标但**不**使用它算像素，而是取
   `GetCursorPos` 的物理坐标再映射到冻结图（`screen_mapping.frozen_image_point`），
   保证 125%/150% 缩放下命中单个物理像素。
4. **交互**：`MouseArea` 的 `onPositionChanged` → `preview()` 返回 HEX →
   更新十字线（`cursorX/cursorY`）与跟随标签；左键 `confirm()`、右键/`Esc` `cancel()`。
   `Esc` 另有 `GetAsyncKeyState` 轮询兜底（窗口不抢焦点时键盘事件可能收不到）。
5. **跟随标签**：深色圆角卡片（`#F2262A33`，圆角 8）+ 24×24 圆角 4 正方形色块
   （浅色描边 + 内层深描边）+ 白色 14px Consolas 的 HEX。标签只显示色块与色值，
   不显示颜色中文名、不显示操作提示。
   位置由 `cursorX/cursorY` + `labelFlipX/labelFlipY` 决定；翻转阈值按标签**实测尺寸**
   计算（`cursor + label.size + 18 > 窗口`），贴边时整体翻到另一侧。
6. **收尾**：`confirm/cancel` 只能改状态并把 `window.close()` + `engine` 释放排到
   下一轮事件循环（`QTimer.singleShot(0, teardown)`）。在 JS 栈里同步析构
   `QQmlApplicationEngine` 会段错误（表现为"点吸管瞬间闪退"）。
   这些方法**必须**带 `@Slot`，否则 QML 调用会静默失效。

### 3.4 HSL 滑块在哪、为什么这么写

- 视图：`qml/InlineColorPicker.qml`，三条滑杆在文件末尾的 `Repeater` 里
  （`objectName` 为 `pickerSlider_hue` / `pickerSlider_sat` / `pickerSlider_lig`）。
- 数据：`qt_ui/picker.py` 的 `PickerState`，`pick_cell` / `pick_color` / `adjust`
  三个写入方法，`satTrack` / `ligTrack` 提供渐变端点。
- 往返：拖动 → `bridge.pickerSlide(cardIndex, h, s, l)` → `host.apply_inline_picker`
  → `PickerState.adjust` → 状态回推 → 滑杆绑定重算。

两条必须保留的约束：

1. **`Repeater.model` 只能是静态 key 列表**（`['hue','sat','lig']`）。
   曾用内联 JS 数组承载动态值，结果每次拖动都重建全部委托，鼠标抢占丢失，
   表现就是"只能单击、拖不动"。
2. **三条滑杆一律可拖**，不按颜色状态禁用。
   中性色（黑/白/灰）的 `PickerState.neutral == (sat == 0)` 曾被用来禁用色调滑杆，
   于是点过「常用色」里的 #000000 / #FFFFFF / #7F7F7F 后色调就锁死。
   现在 `neutral` 只用于文案提示，不参与 `enabled`。

---

## 4. 打包

### 4.1 正式发布（原作者流程 + Qt 开关）

`work/studio/build_release.py` 是唯一的打包脚本。**默认打 Qt 版**，
需要对照 Tk 版时才显式切回去：

```bat
:: 默认即 Qt 版，不必设变量；下面这行只是显式声明
set COLOR_STUDIO_UI=qt
set COLOR_STUDIO_UPDATE_PUBLIC_KEYS=release\update-public-keys.json
set TESSERACT_HOME=C:\Program Files\Tesseract-OCR
python work\studio\build_release.py
```

`COLOR_STUDIO_UI=tk` 会改打 `app.py`（Tk 版）并 `--exclude-module PySide6`。

产物：

```
outputs/release/ColorStudio/ColorStudio.exe       主程序（onedir）
outputs/release/ColorStudio/ColorStudioUpdater.exe 更新辅助
outputs/release/ColorStudio/_internal/...          PySide6 / QML / OCR 资源
```

`COLOR_STUDIO_UI` 取 `qt` 时脚本会追加：

- `--paths work/studio`、`--add-data work/studio/qt_ui/qml;qt_ui/qml`
- `--collect-data shiboken6`、`--hidden-import PySide6.QtQuickControls2`
- 不再 `--exclude-module PySide6`

`run_qt.py` 在 frozen 模式下从 `sys._MEIPASS/qt_ui/qml` 找 QML，与上面的
`--add-data` 目标一一对应，两边改名必须同步。

### 4.2 校验打包结果

1. 启动 `ColorStudio.exe`，确认主窗口出现（不是 Tk 窗口）。
2. 打开一次目标色面板（点目标色块）→ 有色域与三条滑杆 = QML 资源已打进去。
3. 触发一次寻色 → 浮窗出现，说明 `Overlay.qml` 与 `overlay_native` 都在。
4. 用一次吸管 → 全屏冻结 + 跟随标签正常。
5. 检查 `_internal/qt_ui/qml/Main.qml` 是否存在；缺失时程序会打印「QML 加载失败」并退出。

---

## 5. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 界面能开但全白、文字发灰 | `uiState` 被 QML 内建属性遮蔽，或注入名写错；启动自检会拦截 |
| 打印「QML 告警 N 条」 | 某处绑定引用了不存在的属性；按提示修 QML，不要放宽自检 |
| 浮层关闭后再点入口没反应 | `Popover` 的 `open` 被命令式赋值破坏绑定；改由 `openPanel()` 统一驱动 |
| 浮层出现在上一次的位置 | `anchorItem` 用了绑定而不是显式赋值，求值晚于 `show()` |
| 长时间使用越来越卡 | 检查是否有逐次 `changed.emit()`、`QTimer` 未 `deleteLater`、tick 自续成双循环 |
| 打包出来还是 Tk 界面 | 忘了 `set COLOR_STUDIO_UI=qt`（脚本默认 `tk`） |

> `.gitignore` 说明：`/work/studio/*` 默认忽略整个目录，只放行 `*.py`、`*.md` 等白名单。
> `qt_ui/` 若新增目录层级，需要同步补 `!/work/studio/qt_ui/**` 的放行规则，
> 否则 Qt 界面文件不会进 Git。

---

## 6. 与 Tk 版的关系

仓库里仍保留原作者的 Tk 界面（`app.py`、`ui_dialogs.py`、`ui_presets.py`、
`search_overlay.py`、`window_picker.py`、`palette_viewer.py`、`ui_performance.py`、
`resize_surface.py`、`eyedropper.py`、`updater/ui_update.py`），原因有三：

1. `run_studio.bat` 仍可启动 Tk 版做行为对照；
2. `update_bootstrap.py` 的更新健康检查会建一个隐藏 Tk 窗口（`tkinter.Tk()`），
   打包时需要 Tk 运行时可用；
3. 这些文件属于上游仓库，删除会让与上游的差异变大。

Qt 入口不会导入它们：从 `run_qt.py` 出发的静态导入闭包里，模块级
`import tkinter/customtkinter` 的数量为 0。
