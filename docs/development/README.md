# 开发指南

## 先运行程序

需要 Windows、Python 以及 Tesseract OCR。Python 依赖以根目录 `requirements.txt` 为准；构建依赖见 `requirements-build.txt`。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python work/studio/app.py          # 或双击 run_studio.bat
python -m pip install pytest; python -m pytest
```

若 OCR 不在默认安装目录，按应用设置指定路径。开发环境也不要自动进入染色或套用结果。

## 改动从哪里开始

| 想改什么 | 主要入口 |
| --- | --- |
| 启动、更新确认与关闭 | `app.py`、`qt_ui/host.py`，见 [Qt 界面说明](qt-ui.md) |
| 主窗口、色卡、按钮（QML） | `qt_ui/qml/Main.qml`、`qt_ui/qml/RegionCard.qml` |
| 寻色流程、事件分发与结果显示 | `business.py` |
| 截图寻色流程与结果展示 | `screenshot_live.py`、`screenshot_presentation.py` |
| 精准寻色接入与数据读取 | `native_live/service.py`、`native_live/scan_live_dye.py` |
| 停止来源与快捷键 | `run_stop.py`、`hotkeys.py` |
| 浮窗 | `qt_ui/overlay.py`、`qt_ui/qml/Overlay.qml` |
| 颜色规则与优先级 | `color_matching.py`、`region_priority.py` |
| 已选多区域方案的落点纠偏 | `destination_policy.py`、`native_live/route_feedback.py`；全局优先级仍由搜索层决定 |
| 配置与方案保存 | `profile_store.py` |
| 五语文案 | `i18n.py`、`locale_ja.py`、`locale_ko.py`、界面短标签 `qt_ui/i18n_qt.py` |
| 自动更新（镜像优先、直连回退） | `updater/`、根目录 `release/release-config.json` |

表中未写目录的 Python 文件均在 `work/studio/`。截图模式从画面获得数据；精准模式读取游戏进程，二者不是同一数据来源。“精准 HEX”是颜色要求，不能与“精准寻色”模式混用。

## 修改、检查、交付

1. 根据故障日志找到流程入口，先区分读取、搜索、输入、结果显示哪个阶段出错。
2. 修改最小必要范围，复用现有测试。执行受影响用例，见[测试指南](../../TESTING.md)。
3. 报告真实验证范围，不把离线回放写成实机测试。日志保留到本地 `outputs/`。
4. 更新当前说明；历史实验报告无需逐份改成最新版。正式发布按[发布指南](release-tooling.md)。

## 停止与结果的开发约束

- F9、真实色盘结束、绑定变化后不能继续输入。
- 手动停止或色盘结束时不一定能拨回本轮最好颜色；UI 必须区分当前实测和上次实测，不能无证据显示“已恢复”。
- 看起来足够黑不等于 exact HEX 满足；最终判断使用实际色码。
- 截图与精准模式的整局耗时、4K 表现需要分别实测，不能由单条优化或离线用例推断。

这些是实现与验证约束，不是可以随意放宽的颜色验收标准。

## 如何找旧资料

当前开发只需本页、[Qt 界面说明](qt-ui.md)、测试指南和发布指南。`docs/research/` 与 `docs/server-adaptation/` 的日期报告是当时的故障证据；请勿直接照抄旧命令或旧预算。已被实现取代的逐步计划和旧实验副本从当前树移除，可从 Git 历史找回，见[整理记录](maintenance.md)。
