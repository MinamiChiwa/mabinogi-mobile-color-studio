# 测试：只检查本次改动

推荐入口是 `python run_tests.py`。先安装根目录 `requirements.txt`；在已激活的虚拟环境中运行。

## 日常操作

```powershell
# 基础冒烟：颜色规则、停止状态、配置、优先级、窗口坐标和测试入口
python run_tests.py

# 改了停止处理，就只运行对应模块；支持多个名称
python run_tests.py --modules test_run_stop test_hotkeys

# 也可以只运行一个用例
python run_tests.py --modules test_run_tests.RegressionEntryTests.test_duplicate_names_are_run_once

# 查看选择，不执行；记录放在被忽略的 outputs 目录
python run_tests.py --list
python run_tests.py --modules test_run_stop --json outputs/stop-tests.json
```

`--modules` 不会再套用默认筛选，拼错名称或导入失败会报错。`run_tests.ps1 -Modules test_run_stop,test_hotkeys` 是同一入口的 Windows 包装。

## 什么时候扩大范围

| 范围 | 命令 | 用途 |
| --- | --- | --- |
| 基础冒烟 | `python run_tests.py` | 环境与核心规则快速检查；不含真实桌面操作 |
| 指定模块 | `python run_tests.py --modules test_screenshot_live` | 日常修复首选；只导入指定模块及其依赖 |
| 常用集成 | `python run_tests.py --suite quick` | 兼容旧入口，覆盖面较大，不是日常默认 |
| 发布检查 | `python run_tests.py --suite release --json outputs/release-tests.json` | 打包前检查；包含真实 Tk/桌面检查，需要可用桌面 |
| 历史回放 | `python run_tests.py --suite research` | 排查对应历史问题时才使用，部分依赖本地样本 |
| 全部 | `python run_tests.py --suite full` | 大范围迁移才使用，禁止每次修改都运行 |

`--no-desktop` 可以排除真实桌面检查，但不能据此宣称发布验收完成。日志中的通过、跳过、失败分别统计；缺失的历史样本不算通过。离线测试不能证明实机颜色效果或 4K 性能。

## 文件在哪里

- `tests/studio/`：应用行为测试和共享模拟器，已与生产源码分开。
- `scripts/test_run_tests.py`：测试入口自身的检查。
- 根目录 `fixtures/`：随仓库提供的小型样本。
- `work/studio/fixtures/`、`work/studio/data/`：可选本地历史记录，不提交。

测试文件名保留原名，方便从旧报告找到对应用例。`test_paths.py` 统一生产源码位置，移动测试不会改变本地样本的读取位置。

如使用 pytest，显式文件或用例会直接执行，不再被隐藏的默认分组筛掉；不带路径时默认只选基础冒烟。日常优先使用上述入口，避免 pytest 为筛选而先收集全库。

## 添加或删除测试

先复用现有模拟器和用例。新增测试应能解释“玩家遇到什么问题，错误行为是什么”。同一行为的重复检查应合并；仅检查源码字符串的旧检查应在有行为覆盖后删除。保留仍在使用的历史策略测试，按需执行，不用测试总数衡量质量。
