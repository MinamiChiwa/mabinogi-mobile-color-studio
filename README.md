# 染色工坊 · 瑪奇 Mobile

作者：**南千和** · [爱发电](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink)

适用于**港澳台服瑪奇Mobile**的自动染色工具。运行于 Windows，通过游戏画面识别与鼠标操作，寻找三个染色区域的目标颜色。

> 在游戏中使用本程序可能存在风险，建议谨慎使用。

支持作者完全自愿，不会影响工具使用： [爱发电](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink)

本工具由AI辅助完成。

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

## 使用

从 Releases 下载 `ColorStudio-v0.3.2.zip`，解压后运行 `ColorStudio.exe`，保留旁边的 `_internal` 文件夹。正式包包含 OCR 及英文识别数据，无需安装 Python 或另行安装 Tesseract。升级时请先退出旧版本，并将新版本解压到独立文件夹，避免混用不同版本的文件。

1. 在游戏中将窗口设为 1280 × 960。程序默认启用三个区域；不需要匹配的区域可手动关闭。输入 HEX 或使用选色器、屏幕吸管，也可以填写替代颜色。
2. 每个区域可独立选择精准 HEX 或相似颜色。即使只将一个或两个区域设为精准 HEX，也优先于其余相似区域：先比较精准命中区域数；命中数相同时，再比较所有启用区域的最大色差和平均色差。精准区域必须完全命中 HEX。
3. 相似区域按设定的 ΔE 容差搜索，不受固定 ΔE 8 上限限制。若没有候选满足全部设置，程序仍会按上述优先级自动移到最接近的可执行妥协方案。
4. 在“游戏窗口”中使用自动检测或手动选择目标窗口，然后按 **F8** 或点击开始。浮窗出现后，手动进入游戏内染色倒计时界面；程序先拼接本局大图，再搜索、定位并复核游戏 HEX。**F9** 随时停止。

自动检测兼容标题空格差异，并识别游戏进程名。多个候选时请手动选择；所选窗口关闭后需重新选择。无边框全屏可以使用，正式寻色期间请保持游戏前台和窗口尺寸不变。

程序完成定位后会显示游戏内 HEX，请在游戏中确认结果后手动套用染色。

精准与相似模式均使用本局拼图搜索，并根据候选计算旋转、缩放和平移。自动操作期间请勿移动鼠标。窗口位置或大小在运行期间改变会停止寻色，需要重新按 F8。

界面右上角可选择简体中文、繁體中文或 English，主窗口、浮窗及已打开的信息窗口都会即时切换，无需重启。窗口可拖动调整尺寸，主界面卡片会随宽度切换为三列、两列或单列；帮助按钮打开教程，支持作者窗口提供爱发电与 Patreon 链接。

## 预览与记录

- 主界面显示有序色块概览，点击打开完整允许颜色集合。
- 大图使用 ＋／－ 缩放、拖动浏览及悬停查看 HEX，不需要翻页。
- 寻色记录保存最近 50 次结果，包含三色组合、各区 ΔE、最大和平均色差。
- 正式寻色流程会复核游戏 HEX，并在浮窗中显示结果。精准模式的色差滑条不可用。
- 本机配置、记录及诊断截图默认存放在程序旁的 `data` 文件夹。若安装目录不可写，程序会改用 `%LOCALAPPDATA%\MabinogiMobileColorStudio\data`；该位置也不可用时才使用系统临时目录。
- 开始新一局时，旧会话清理在后台运行。最近 20 次会话及最近 5 分钟内有更新的会话受到保护；其余会话超过 30 天或总大小超过 512 MiB 时可被清理。受保护数据仍可能使总大小超过 512 MiB。系统临时目录中的数据可能被系统清理。

## 开发

Windows 10/11，Python 3.12。源码位于 `work/studio`。

```powershell
python -m pip install -r requirements-build.txt
python work/studio/app.py
python -m unittest discover -s work/studio -p "test_*.py"
```

源码运行与构建还需要安装 Tesseract OCR（含 `eng.traineddata`）。默认位置为 `C:/Program Files/Tesseract-OCR`；构建时可设置 `TESSERACT_HOME`。

源码环境可运行 `run_studio.bat`，它使用项目 `.venv`。OCR 也会识别项目内的 `outputs/dependencies/ocr`。`run_preflight.bat` 提供只读预检并将报告写入独立时间戳目录；该脚本需要源码环境，不是正式压缩包的必需步骤。正式入口使用本局拼图、候选定位和游戏 HEX 复核流程。

当前版本的截图颜色预测仍可能与游戏实际 HEX 存在偏差。工具在移动完成后读取并显示游戏 HEX，最终套用须在游戏内手动完成。当前版本说明见 [0.3.2 更新内容](RELEASE_NOTES_0.3.2.md)，验证范围见 [0.3.2 验证报告](work/studio/RELEASE_VALIDATION_0.3.2.md)。

```powershell
python work/studio/build_release.py
```

产物在 `outputs/release/ColorStudio`。现有发布目录的个人数据会备份到 `work/studio/release-test-data`，不会提交到仓库。游戏实拍回归素材属于本机测试资料，未随仓库分发；缺少这些素材时相关测试会显示跳过。

## 验证范围

有限时间内的搜索不保证精准命中、满足全部容差或找到全局最优组合。布局计算矩阵覆盖 1024×768、1920×1080、3840×2160、5120×2880 及 100%、125%、150%、200%、250% DPI；另有物理像素坐标换算和负坐标多屏测试。上述检查不代表所有 4K、多屏及混合 DPI 配置均已完成实机游戏验证。

简体中文、繁體中文和 English 的主窗口、浮窗、教程、支持窗口及运行状态会即时切换。OCR 固定使用 `eng` 数据，不受界面语言影响；程序会处理 Windows 本地路径的非 UTF-8 输出。工具窗口按显示器工作区计算尺寸；4K 屏幕也应将游戏设为 1280 × 960 窗口模式，无需修改桌面分辨率。

启动后请保持游戏处于前台，并在染色倒计时界面等待程序完成。需要中止时按 F9；如果游戏窗口位置或大小发生变化，请停止后重新开始。无法自动切回游戏时，手动激活游戏窗口即可继续等待识别。底部显示快捷键注册状态；冲突时请关闭其他工具副本或使用按钮。

正式实机验证前，可先执行不进入染色界面的预检。它只读取当前游戏窗口并检查截图、DPI、失焦保护和 F9 保护：

```powershell
$env:PYTHONPATH='work/studio'
.\.venv\Scripts\python.exe work/studio/live_atlas_capture.py preflight .\outputs\preflight-new
```

预检使用新目录，拒绝覆盖已有记录。确认 `preflight.json` 中 `input_sent` 为 `false`、`passed` 为 `true`，且实际客户区符合本次校准要求后，再启动采样。F9、失焦和窗口变化保护为模拟检查。

主界面的颜色卡片保持固定尺寸，仅在跨越列数断点时重排。启用卡片有青色边框和底色，停用卡片显示“未启用”。浮窗可拖动、收起并调整透明度，同时显示当前阶段和已用时间；长内容可滚动，标题和 F9 停止按钮保持可见。颜色数值使用点击或拖动调整，避免滚轮误改。等待期间暂时切换窗口后可返回游戏继续识别；安全中断会提示，普通动作问题会显示恢复状态并保留当前画面。
