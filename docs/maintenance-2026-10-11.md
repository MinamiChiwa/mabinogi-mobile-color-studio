# 本地维护规则

当前工作区只保留公开版 `outputs/release-v0.4.1`、上一候选版 `outputs/release-v0.4.2rc4` 和当前候选版 `outputs/release-v0.4.2rc5`，以及最近的验证证据。历史源码与文档可从 Git 恢复；原始截图和包不在 Git。清理前必须保留用户原始压缩包及当前发布依赖的最小测试样本。

回归分层如下：

- `python scripts/run_tests.py --suite quick`：当前产品合同、UI、DPI、重试、会话和少量关键路线，适合每次代码修改。
- `python scripts/run_tests.py --suite release`：quick 加入打包前的保存色板、保护回程、两区域、代表路线和桌面检查。
- `python scripts/run_tests.py --suite research`：历史搜索矩阵、候选分布、旧图像路线和完整研究回放。
- `python scripts/run_tests.py --suite full`：所有已发现测试，仅用于版本审计或框架升级。

当前选择规模为 quick 535、release 577、research 1131、full 1695。最近 quick 实跑为 529 通过、6 个可选样本跳过、零失败，约 61 秒；旧 quick 为 735 项、约 480 秒。历史 rc10 路线回放从 quick/release 移到 research/full，节省了主要耗时。

新测试不会自动进入 quick。测试选择报告会列出未分类模块；确认它属于当前产品合同后，再加入 `QUICK_MODULES` 或 `QUICK_TEST_IDS`。历史回放应放在 research，避免每次改 UI 或输入保护都重新运行旧路线。

发布前只需保留源码、三语 README、`TESTING.md`、`VERIFICATION.md`、当前版本 release notes 和最近一次验证报告。用户配置、游戏会话、截图和原始压缩包不能进入 Git 或发布包。

当前 rc4 的真实三白路线仍需一次用户实机验证。离线 compiler 和回归结果证明路线、时间预算和适配逻辑已经覆盖，不能替代游戏内最终色码确认。

## rc5 收尾检查

- [x] 核对 Git 提交与开发副本一致，DPI 后端测试已进入 quick。
- [x] 修正测试文档的自动纳入规则，合并旧版本流水账。
- [x] 为发布判定加入缺失必要样本检查，并完成先失败后通过的入口回归。
- [x] 从用户原始 data (3).zip 恢复约 700 KB 必需证据，不重新收集游戏数据。
- [x] 执行 quick 与精简 release，记录实际跳过和耗时（见下方限制）。
- [ ] 构建 rc5，检查字节码、资源、启动、便携包 CRC/SHA。

Git 主库位于 `D:/Working/ColorstudioProject/ColorStudio-handoff-2026-10-04/repo`；开发和带样本验证目录为 `D:/Working/ColorstudioProject/project`。开发目录没有 .git。源码变更同步到主库后本地提交，不自动推送或正式发布。

## 最终源码验证与限制

rc5 quick：536 项，535 通过、1 个历史 OCR 跳过，零失败，66.579 秒。release：578 项，575 通过、3 跳过，零断言失败，289.576 秒；其中两项 rc16 相似色完整路线因原始会话被清理而缺样本，发布判定为未完成。需要恢复 `20261010-235332-5fe7c98a` 的原始记录；不能用另一张色板或模拟数据假装复现原问题。

发现并移除 Git 主库的重复旧测试选择器、失效的旧选择器测试，以及与当前实现冲突的旧说明。根目录 Python、PowerShell 和 pytest 统一使用 scripts/run_tests.py；原有单样本门控测试引用的 API 已不存在，其当前有效契约仍在 test_local_fixture_guards 中。

妥协结果事件／落盘集成测试曾重复执行全局细化，单项花费 63.230 秒。该测试本来就注入固定妥协路线，现在同时注入“无进一步细化”，两个服务集成用例合计 4.399 秒通过。真实细化和回程求解仍有独立测试，生产算法未因测试提速修改。此定向结果不冒充重新测得的整套 release 耗时。

本轮仅生成本地候选，不覆盖用户桌面程序或数据、不推送 GitHub。跨硬件实机与三白精准实测仍未完成，不宣称适配所有电脑。
