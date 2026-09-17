# 染色工坊 · 瑪奇 Mobile

作者：**南千和** · [爱发电支持作者](https://afdian.com/a/minamichiwa)

适用于**港澳台服瑪奇Mobile**的自动染色工具。运行于 Windows，通过游戏画面识别与鼠标操作，寻找三个染色区域的目标颜色。

> 在游戏中使用本程序存在风险，请用户自行斟酌。

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

## 使用

从 Releases 下载完整压缩包，解压后运行 `ColorStudio.exe`，保留旁边的 `_internal` 文件夹。

1. 启用需要匹配的区域，输入 HEX 或使用选色器、屏幕吸管；可以填写替代颜色。
2. 选择精准模式或相似模式。推荐先从相似模式 ΔE 8–12 开始，色差越小越接近目标。
3. 在游戏中使用普通染色剂，教学结束后按 **F8** 开始；**F9** 停止。

相似模式进入容差范围后仍继续寻找更接近的组合。除所有启用区域命中目标原色外，剩余约 30 秒返回本轮最佳组合。工具会复核游戏色码，完成后弹窗提示，由玩家决定是否使用妥协颜色。

精准模式遇到接近颜色会以该色块为缩放中心分批放大。旋转以右键按下处为圆心，缩放以鼠标位置为支点。窗口位置或大小在运行期间改变会停止寻色，需要重新按 F8。

界面右上角可选择简体中文、繁體中文或 English；切换时保存方案并重新打开程序。

## 预览与记录

- 主界面显示有序色块概览，点击打开完整允许颜色集合。
- 大图支持缩放、拖动、滚动及悬停查看 HEX，不需要翻页。
- 寻色记录保存最近 50 次结果，包含三色组合、各区 ΔE、最大和平均色差。
- 自动复核套用默认关闭。精准模式的色差滑条不可用。
- 本机配置、记录及诊断截图存放在程序旁的 `data` 文件夹。

## 开发

Windows 10/11，Python 3.12。源码位于 `work/studio`。

```powershell
python -m pip install -r requirements-build.txt
python work/studio/app.py
python -m unittest discover -s work/studio -p "test_*.py"
```

源码运行与构建还需要安装 Tesseract OCR（含 `eng.traineddata`）。默认位置为 `C:/Program Files/Tesseract-OCR`；构建时可设置 `TESSERACT_HOME`。

```powershell
python work/studio/build_release.py
```

产物在 `outputs/release/ColorStudio`。现有发布目录的个人数据会备份到 `work/studio/release-test-data`，不会提交到仓库。游戏实拍回归素材属于本机测试资料，未随仓库分发；缺少这些素材时相关测试会显示跳过。

## 验证范围

见 [VALIDATION.md](VALIDATION.md)。有限时间内的搜索不保证每次找到精准颜色或全局最优组合；当前实机验证不覆盖所有 DPI 与显示器组合。

按 F8 后最多等待60秒，可先从背包进入普通染色并完成教学；识别到色板和倒计时后自动开始。等待期间不操作鼠标，按 F9 可取消；超时会弹窗提示重新按 F8。

主界面维持三列卡片，窗口按56:45比例缩放，顶部精准色提醒始终可见。启用卡片有青色边框和底色，停用卡片显示“未启用”。所有工具界面控件均不接受滚轮输入；数值使用点击或拖动调整。等待期间暂时切换窗口后可返回游戏继续识别；中断或错误会弹窗提示。
