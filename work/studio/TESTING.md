# 测试范围与维护规则

2026-10-08 完成第一次用途分组；2026-10-09 Task 1 增加 16 项预算与证据回归，Task 2 增加 13 项基线/返程/状态回归。所有既有测试保留；默认开发回归不再把实验诊断、旧搜索和缺少私有素材的检查计入生产验证。

## 运行入口

推荐使用项目虚拟环境，无需安装 pytest：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_tests.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_tests.ps1 -Profile diagnostics
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_tests.ps1 -Profile legacy
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_tests.ps1 -Profile fixtures
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_tests.ps1 -Profile all
```

`-List` 只列出选中的测试 ID，不运行测试。脚本可从其它工作目录使用绝对路径调用。也可以在仓库根目录运行 `.venv\Scripts\python.exe run_tests.py --profile production`；入口默认 production。

已安装 pytest 的开发环境可使用同一分组：

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest -q --test-profile=all
```

pytest.ini 将默认收集限制为 `tests` 和 `work/studio`，不递归收集 outputs 中的备份/旧包。pytest 的 `--test-profile` 同样支持 diagnostics、legacy、fixtures。不要把默认分组的通过数报告为全量通过数；未选择的测试是 deselected，不是 skipped。

## 分组含义

| 分组 | 收集数量 | 用途 |
| --- | ---: | --- |
| production | 719 | 当前单区与多区搜索、输入安全、倒计时、返程、实测结果保护、OCR、UI 和测试分组保护 |
| diagnostics | 105 | 明确启用的机制探针、离线方法比较、回放及报告工具 |
| legacy | 56 | 旧 Runner 搜索、自动套用和旧恢复策略；混合文件中的调色板、记录、吸管及共享几何仍留在 production |
| fixtures | 19 | 依赖私有游戏截图、OCR 或历史运行归档的检查 |

分类规则只维护在仓库根目录 `run_tests.py`，pytest 使用同一规则。新测试默认归 production。安全保护、正式采集路线的几何回归不因文件名带 review/probe 就移入诊断组。

收集数量不等于 unittest 的运行报告数量：某个类在 `setUpClass` 中跳过时，unittest 会以一次类级跳过代替该类的多个测试。pytest 则逐用例报告。每份报告应说明框架、分组、通过、失败、跳过或未选择的数量。

## 本次处理

- ECC 诊断测试不再只断言矩阵有限，而是核对已知 1 像素平移，允许误差 0.05 像素；错误的有限单位矩阵不能通过。这验证离线估计器，不代表游戏配准达到该精度。
- 锚点回放测试明确验证当前仍保留完整连续路线，不声称减少采集。逐个检查真正的 command 记录，避免混用帧序号与交替日志索引。
- `test_visual.py` 改为逐用例检查所有需要的素材，删除由一张无关截图决定整个类是否跳过的门控。缺失素材逐用例写出名称；OCR 检查只影响需要 OCR 的用例。
- 增加 6 个测试基础设施回归，保护分组不漏测、不重复收集、正式安全路径不被迁出，以及独立素材门控。

没有证据证明既有核心用例可安全删除，本次以迁出默认运行和加强断言处理，不为降低数量删除保护。

## 私有素材

视觉用例优先读取 `tests/fixtures/sessions/<会话名>/<文件>` 或 `tests/fixtures/evidence/<文件>`；也可用环境变量 `COLORSTUDIO_TEST_FIXTURES` 指定独立素材根目录。这个目录不受应用会话清理影响，并已忽略 Git 跟踪。迁移期间仍兼容原本的本机素材路径。

其它归档用例仍保留各自历史路径，尚未全部迁移到独立素材目录。现有缺失素材不能用伪造截图代替，更不能把 fixtures 跳过解释为真实游戏验收通过。

## 后续维护

改正式逻辑时运行 production；改实验工具时额外运行 diagnostics；改共享模块时运行 all。发布前必须运行 all，并单独核对 fixtures 的缺失项及真实游戏验收。

删除测试前必须确认相关功能已退出支持范围，或另一个用例完整覆盖相同故障。对“只检查没有异常”、固定调用次数、源码文本存在性等弱断言逐个评估；这些形式不自动等于无用，也不能代替行为验证。测试数量不作为质量或机制已验证的指标。
