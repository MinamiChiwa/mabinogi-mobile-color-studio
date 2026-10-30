# 测试指南

自动测试只覆盖**不需要游戏**就能确定对错的行为契约，整套在 2 秒内跑完，每次改动都可以完整运行。寻色效果只能在游戏里实测，不用自动测试冒充。

## 运行

```powershell
python -m pip install -r requirements.txt pytest
python -m pytest                                   # 全部
python -m pytest tests/test_qt_app.py              # 一个文件
python -m pytest -k mirror                         # 按名称筛选
```

Qt 测试在 `offscreen` 模式下运行，不会弹出窗口、不注册全局热键、不读写 `work/studio/data`。推送和 Pull Request 由 GitHub Actions（`.github/workflows/tests.yml`）在 Windows 上运行同一命令。

## 覆盖范围

| 文件 | 守住的契约 |
| --- | --- |
| `tests/test_rules_and_profile.py` | 卡片设置 → 送进引擎的规则字典；方案文件读写、旧格式迁移与非法输入 |
| `tests/test_update_transport.py` | 镜像优先、失败自动直连 GitHub 并在一段时间内保持直连；API 不走镜像；镜像返回的损坏文件改从 GitHub 重下；篡改的清单被拒绝 |
| `tests/test_update_assets.py` | 发布资产只有签名清单与 blob；校验能发现被改动的 blob；增量下载量统计 |
| `tests/test_qt_app.py` | 全部 QML 可编译、主窗口无告警；寻色中关闭先停止再退出；空闲关闭保存设置；更新后首次启动等待提交、回滚时退出；安装更新时退出；顶栏可打开完整更新对话框 |
| `tests/test_ui_translations.py` | QML 固定文案在英、日、韩界面都有翻译，不残留中文 |

## 写新测试

- **测玩家能遇到的行为、失败恢复和数据契约**。不要为“源码里出现某句话”“某个私有变量存在”写测试；不要为了变绿删除失败用例。
- 先找对应的现有文件追加用例；只有出现新的契约领域才新建文件。修 bug 时先写一个能复现它的失败用例。
- 网络、更新助手、游戏窗口一律用假对象替代（参照 `test_update_transport.py` 的 `Transport`、`test_qt_app.py` 的 `FakeRunner`）。测试不得访问网络、移动鼠标或操作游戏。
- 共享夹具在 `tests/conftest.py`：`qapp`（Qt 应用）、`data_dir`（隔离的数据目录）、`wait_until`（驱动事件循环直到条件成立）。测试用签名密钥在 `tests/signing.py`，只用于测试，从不进入发布包。
- 单个测试应在 1 秒内结束。需要真实桌面、真实游戏或打包产物的检查放到下方手动清单，不放进自动测试。

## 不在自动测试里的检查

| 场景 | 做法 |
| --- | --- |
| 寻色效果、耗时、4K 表现 | 在游戏内分别实测截图寻色与精准寻色，如实记录未测项 |
| 打包内容 | `python scripts/verify_release.py <包目录> --json <报告>`：字节码与源码一致、QML 完整、未打入 Tk 与个人数据 |
| 更新资产 | `python scripts/verify_update_assets.py <资产目录> --package <包目录> --public-keys <公钥JSON>` |
| 真实升级演练 | `python scripts/smoke_frozen_update.py --old-package <旧版包> --assets <新版资产> --keys <测试公钥JSON> --out <空目录>`：在隔离目录里用测试签名完成一次冻结程序升级，覆盖健康检查与首次启动确认 |

发布流程见[发布指南](docs/development/release-tooling.md)。
