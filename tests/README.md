# 测试目录导航

测试与生产源码分开放置，但保留旧模块名，方便从故障记录查找。运行方式见[测试指南](../TESTING.md)。

| 要查的问题 | 优先找哪些模块 |
| --- | --- |
| 截图采集、搜索、收尾与色卡 | `test_screenshot_*`、`test_refinement_*` |
| 内存读取、服务器适配、原生路线 | `test_native_*` |
| 多区域优先级、颜色要求与妥协 | `test_region_priority`、`test_color_matching`、`test_priority_search_paths` |
| 停止、快捷键、窗口/DPI | `test_run_stop`、`test_hotkeys`、`test_window_target`、`test_screen_mapping` |
| 界面、保存与五语 | `test_*ui*`、`test_profile_*`、`test_release_localization` |
| 更新、签名、安装事务 | `test_updater_*`、`test_update_assets` |
| 旧图集和历史路线回放 | `test_atlas_*`、`test_native_refinement_recorded` 等，按故障选取 |
| 共享模拟器与路径 | `test_support.py`、`test_paths.py`，本身不作为功能测试 |

示例：修复截图停止后色卡不更新，运行 `python run_tests.py --modules test_screenshot_stop_results test_screenshot_ui`。不要为了这个问题运行全部历史图集或更新签名测试。

大多数用例用模拟输入，不操作游戏。少数桌面检查会创建真实窗口；历史图片回放可能需要未随仓库分发的本地样本。缺样本会跳过并显示原因，不能算作完成实机验证。
