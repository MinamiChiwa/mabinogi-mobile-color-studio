# 本地维护规则

当前工作区只保留公开版 `outputs/release-v0.4.1`、当前候选版 `outputs/release-v0.4.2rc4`，以及最近的验证证据。历史候选包和大体积截图属于可恢复的 Git 历史或已经归纳到 `docs/research` 的记录，不继续占用工作区。

回归分层如下：

- `python scripts/run_tests.py --suite quick`：当前产品合同、UI、DPI、重试、会话和少量关键路线，适合每次代码修改。
- `python scripts/run_tests.py --suite release`：quick 加入打包前的保存色板、保护回程、两区域、历史路线和桌面检查。
- `python scripts/run_tests.py --suite research`：历史搜索矩阵、候选分布、旧图像路线和完整研究回放。
- `python scripts/run_tests.py --suite full`：所有已发现测试，仅用于版本审计或框架升级。

新测试不会自动进入 quick。测试选择报告会列出未分类模块；确认它属于当前产品合同后，再加入 `QUICK_MODULES` 或 `QUICK_TEST_IDS`。历史回放应放在 research，避免每次改 UI 或输入保护都重新运行旧路线。

发布前只需保留源码、三语 README、`TESTING.md`、`VERIFICATION.md`、当前版本 release notes 和最近一次验证报告。用户配置、游戏会话、截图和原始压缩包不能进入 Git 或发布包。

当前 rc4 的真实三白路线仍需一次用户实机验证。离线 compiler 和回归结果证明路线、时间预算和适配逻辑已经覆盖，不能替代游戏内最终色码确认。
