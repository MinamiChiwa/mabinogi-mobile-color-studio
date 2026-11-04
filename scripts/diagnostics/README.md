# 游戏诊断入口

根目录只保留日常开发启动器 `run_studio.bat`。原诊断启动器集中在本目录，仍从项目根目录加载开发环境和源码。

| 入口 | 用途 |
| --- | --- |
| `run_preflight.bat` | 进入诊断前检查 |
| `run_grid_capture.bat` | 网格采集 |
| `run_point_probe.bat` | 取色点探测 |
| `run_response_probe.bat`、`run_response_probe.ps1` | 输入响应探测 |
| `run_rotation_compare.bat` | 旋转对照 |
| `run_zoom_reversibility.bat` | 缩放往返探测 |

新输出统一写入 `runtime/diagnostics/`。除预检外，诊断协议可能发送游戏输入；应在用户明确授权对应实机测试后执行。整理时只校验路径与 PowerShell 语法，没有运行这些协议。
