# 回归测试

日常使用 quick，打包使用 release。精简测试不改变实际搜索范围、时间预算或游戏色码验收。

```powershell
.\.venv\Scripts\python.exe scripts/run_tests.py --json outputs/test-quick.json
.\.venv\Scripts\python.exe scripts/run_tests.py --suite release --json outputs/test-release.json
.\.venv\Scripts\python.exe scripts/run_tests.py --suite research --json outputs/test-research.json
.\.venv\Scripts\python.exe scripts/run_tests.py --suite full --json outputs/test-full.json
```

根目录 `run_tests.py`、`run_tests.ps1 -Suite quick` 与 `pytest --test-profile=quick` 共用同一选择器。旧分组入口已移除；完整发布判定使用上面的标准入口和 JSON 报告。

## 当前分层

| 集合 | 范围 |
| --- | --- |
| quick | 设置、方案、区域优先级、多语言、DPI 与坐标、输入和会话保护、计时与重试、关键路线契约；4 个真实桌面代表检查。 |
| release | quick 加完整桌面矩阵、记录色板的双黑／三黑／相似路线、保护恢复、实测结果保存和备用图像策略集成。 |
| research | 历史搜索矩阵、更多色板与扰动、研究工具及历史 rc10 完整路线。 |
| full | 全部发现的测试；release 与 research 的并集覆盖全部测试。 |

当前名单在 `scripts/run_tests.py`。新增模块不会自动进入 quick：未分类模块列入报告并在 research/full 执行；审核后加入模块或用例白名单。单模块内昂贵的会话回放可明确留到 release。

```powershell
# 只列出测试，不执行
.\.venv\Scripts\python.exe scripts/run_tests.py --suite release --list --json outputs/test-selection.json
# 不创建真实测试窗口；不能作为发布验收
.\.venv\Scripts\python.exe scripts/run_tests.py --no-desktop --json outputs/test-unit.json
```

真实桌面检查会创建和关闭工具测试窗口，必须顺序执行。所有集合使用离线模型、记录样本或测试窗口，不操作游戏、不消耗道具。离线结果不代表实机精准命中。

## 证据与发布要求

JSON 报告包含选择清单、通过／跳过／失败／错误数、逐项耗时、最慢用例及未分类模块。必要用例被改名或丢失会失败退出。

部分样本属于本机私有验证资料，不进入 Git 或便携包。缺失时测试明确跳过；quick 的成功不表示这些项目已执行。完整 release 缺少任何必要样本或桌面验证时，`release_complete` 为 false，命令返回非零。唯一允许的补充样本跳过是历史私有 OCR 档案 `test_archived_heldout_hex_including_four_previous_misses`（原因必须为 `Local capture archive unavailable`）。不要为获得绿色结果扩大例外名单。

开发环境的 `work/studio/fixtures` 和当前发布依赖的少量记录样本必须保留；清理临时输出前先核对测试引用。没有完整私有样本的干净 Git 副本可做源码检查，不能独立签发完整发布结论。可复用的脱敏固定样本仍是后续测试可移植性的改进方向。

## 最新结果

当前 rc5 结果及时间见 [维护记录](docs/maintenance-2026-10-11.md)；机器负载影响时长，以 JSON 为准。旧版本逐次测试计数可从 Git 历史查阅，不在本文件重复追加。
