# ColorStudio 自动更新实施计划

> **For agentic workers:** 使用 `superpowers:executing-plans` 按任务实施；当前用户要求换模型后继续执行，本轮仅完成方案。不主动派生子代理。步骤以复选框记录。

**Goal:** GitHub 有兼容新版本时显示更新按钮，经用户决定下载和安装；按文件差异更新，保留全部用户资料，并提供无需联网的离线导入。

**Architecture:** 签名发布清单描述完整应用文件集合；客户端比较本地 SHA-256，只下载缺失或变化的文件。独立更新器在主程序退出后以事务日志替换文件、处理明确归属的旧文件，并在启动失败时恢复。网络与离线入口共用校验和安装引擎。

**Tech Stack:** Windows、Python 3.12、CustomTkinter、PyInstaller onedir；标准库 HTTPS/ZIP/哈希/事务日志，`cryptography` 的 Ed25519 验签及 `packaging.version.Version` 版本比较（实施时选定并锁定兼容版本，补许可证和打包验收）。不要自写密码算法。

**Spec:** 本文第 1–8 节是完整设计约束，第 9 节是实施清单，第 10–12 节是交付与接续要求。

## 1. 已确认范围

- 用户于 2026-10-11 选择“先只做 GitHub 与离线更新”。不部署域名、CDN、公共代理或镜像服务；可抽象下载源，但不实现未获请求的服务。
- GitHub 项目：`https://github.com/MinamiChiwa/mabinogi-mobile-color-studio`。公开稳定版目前是 0.4.1；本地候选为 0.4.2rc8，不要把候选或草稿误推给稳定版用户。
- 自动仅指后台检查；检查不下载程序包，不自动退出、安装、提权或重启。用户明确点击后才下载；下载结束由用户点击“安装并重启”。允许取消下载、稍后安装、忽略当前版本、关闭自动检查和手动检查。
- 染色运行、等待染色、吸管、窗口选择等占用操作期间禁止进入安装事务；下载也暂停，避免影响有限的游戏时间。已有可用更新按钮可以显示，点击说明“结束当前操作后可更新”，不得因此停止染色。
- 不改寻色模型、时间预算或输入规则：首次 30 秒 OCR 宽限、最多 3 秒尾余量、F9 停止、仅游戏实测可宣称精准命中保持原义。更新日志不得披露内存读取细节。
- 必须简中、繁中、英语三语；不增加 GitHub token 要求，不读取或上传游戏日志、截图和用户颜色。
- 无更新器的 0.4.1/现有旧包无法凭空显示更新按钮，必须先手动安装一次具备更新器的引导版本。其后的兼容版本才支持应用内更新。
- 本轮不实现自动更新、不生成签名私钥、不发布。后续执行者可实现并本地验证；发布签名密钥和正式 GitHub 发布是交付前的明确步骤。

## 2. 当前代码与文件布局

开发目录 `D:\Working\ColorstudioProject\project` 包含 `.venv` 和私有历史验证素材，不是 Git 仓库。实际 Git 为 `D:\Working\ColorstudioProject\ColorStudio-handoff-2026-10-04\repo`。只同步本任务明确修改的源码和文档；禁止镜像整个开发目录或把 `data`、fixtures、密钥、输出提交。

| 现有文件 | 接入用途 |
| --- | --- |
| `work/studio/app.py` | Tk 主界面、事件队列、busy/开始/退出状态；更新 UI 只在 Tk 线程更新 |
| `work/studio/ui_strings.py`、`i18n.py` | 三语文本与动态切换 |
| `work/studio/ui_settings.py`、`profile_store.py` | 用户设置原子保存；更新偏好不覆盖现有设置 |
| `work/studio/app_data.py` | 便携 data，或 LocalAppData，再或临时目录回退 |
| `work/studio/build_info.py` | app_version、policy_revision、源码摘要；版本使用 PEP 440 比较 |
| `work/studio/build_release.py` | PyInstaller onedir；添加独立更新器、签名所有者清单等产物 |
| `scripts/verify_release.py` | 当前 122 个生产模块和资源校验；加入更新器和签名产物验证 |
| `scripts/run_tests.py`、`TESTING.md` | quick/release/research 选择；保持精简日常测试 |

当前 rc7 包实测解压约 407.4 MiB：主 EXE 6.23 MiB，`_internal` 401.07 MiB。小版本常只改主 EXE、build-info 和文档；以实际哈希/压缩大小计算节省，不能承诺每次只下载 6 MiB。Python、OCR、OpenCV 或运行库变化时可能需要大包。

应用数据保护范围：整个 `<安装目录>/data`、真实选用的 `%LOCALAPPDATA%/MabinogiMobileColorStudio/data`、临时回退 data、未知用户文件、captures/sessions、方案、历史以及用户自行存放的文件；不能只保护四个 JSON。更新器不得调用 `resolve_data_directory` 来重新猜测活动数据目录。由当前程序记录实际 DATA 绝对路径与数据位置标记，启动新版本沿用；相对便携路径随安装目录迁移。不能因更新器提权切换账户而迁移用户数据。

## 3. 发布产物与信任

### 3.1 首版采用文件差异，不采用二进制补丁

每个发布提供以下 GitHub Release assets：

1. 完整便携 ZIP：新用户和手动救援使用。
2. `update-manifest.json` 与 `update-manifest.sig`：一个平台/架构的完整文件集合和签名；多架构时加平台后缀。
3. `blob-<sha256>.zip`：每个变化文件一个独立压缩资产，内部固定条目 `payload`；散文件按内容去重。为避免一千多次请求，允许把数百个很小且同生命周期的文档/资源归为一个 bundle（组内每项仍有哈希）。大 DLL 不混入常改 EXE bundle。
4. `ColorStudio-offline-<version>-win-x64.zip`：完整目标清单和全部目标 blobs，自包含；另提供 `ColorStudio-offline-from-<base>-to-<target>-win-x64.zip` 小离线差异包，明确 base 清单摘要。

GitHub 每个版本保存自己的所需 blobs，保证旧发布下架不破坏新发布依赖；客户端只下载实际需要的资产。构建对相同源码保持固定依赖和可复现资源布局，减少无意义变化。先实测相邻包 changed-bytes，再考虑二进制补丁；首版不用 bsdiff 等额外链路。

### 3.2 清单结构与校验

示意（摘要省略仅用于阅读，真正 schema 必须要求 64 位小写十六进制值）：

```json
{
  "schema": 1,
  "app_id": "MabinogiMobileColorStudio",
  "version": "0.4.3",
  "channel": "stable",
  "platform": "win32",
  "architecture": "x86_64",
  "release_sequence": 1,
  "minimum_updater": 1,
  "data_schema_read": [1],
  "data_schema_write": 1,
  "key_id": "release-2026-01",
  "files": [
    {"path": "ColorStudio.exe", "sha256": "<file digest>", "size": 6536160,
     "blob": "blob-<blob digest>.zip", "blob_sha256": "<blob digest>", "download_size": 4000000}
  ]
}
```

- 发布脚本生成规范 UTF-8 JSON bytes，Ed25519 对原始文件 bytes 签名；客户端先验签再解析，不重新序列化后验签。签名上限固定，清单建议最大 8 MiB、文件最多 20,000 项、每项大小和总解压大小必须有界，当前包充足适配。
- 公钥和信任 key_id 内置；签名私钥只在维护者安全环境/受控发布 Secret，不能在仓库、客户端或日志。测试使用专用临时密钥。密钥轮换需旧受信任密钥签发新密钥授权并由新引导版本带入，不信任下载文件里任意新 key_id。
- GitHub API/网页的 tag 和版本只能提供发现线索；只有签名清单是可信更新内容。清单版本、平台、release_id/tag 选择结果须一致；校验每个下载 blob 和最终展开文件的大小/哈希。
- 禁止清单向任意绝对 URL 下载；资产名映射到选中的固定 GitHub 仓库发布。允许 GitHub 官方资产重定向所需域名并始终验证 HTTPS，不关闭证书校验。域名集合在集成时用真实下载确认并受测试覆盖，禁止 HTTPS→HTTP。
- Windows 路径按大小写无关比较：拒绝绝对路径、盘符、UNC、`..`、反斜杠别名、ADS 冒号、NUL、设备名、末尾空格/点、重复路径和大小写冲突、文件/目录前缀冲突；限制路径长度并在 staging 预检。拒绝 symlink/junction/reparse point，包含安装根、父链和目标各层，安装前再次检查。
- 永不允许清单拥有 `data/`、用户数据实际路径、更新事务目录或外部路径。根目录可管理程序文件及明确已知文档；新增应用路径必须属于编译时批准的应用目录，不能让清单扩展任意删除范围。
- 不显式接受远端 delete 脚本：删除集 = 上一份已签名所有者清单 − 新清单。仅删除本地哈希仍等于旧清单的普通文件；被用户改动的旧文件保留并提示。被改动的待替换应用文件先显示冲突、备份后经用户确认替换，不静默覆盖。未知同名路径冲突不自动接管。禁止清理未知父目录。
- 普通检查只推荐更高版本；稳定版排除草稿和预发布。预发布通道需用户主动开启。`0.4.2rc8 < 0.4.2 < 0.4.3`。记录已验证发布序列高水位，拒绝在线回放降级；崩溃回滚是本地事务恢复，独立于该防回放策略。离线手动降级首版不支持，展示原因。

## 4. 检查、下载和离线体验

启动主窗可操作后才异步检查，默认每 24 小时最多一次，手动检查可立即触发；一次 worker，禁止检查叠加。沿用系统代理及证书；不内置公共加速代理、不要求关闭防火墙。网络失败不弹阻断对话框，不改变寻色可用性。

GitHub API 使用 ETag/If-None-Match，识别 304、403/429、Retry-After 和 rate-limit reset；没有缓存时 304 需重新请求。稳定通道请求 latest；预发布通道有界分页找最大兼容版本；同一版本撤回、资产未齐或签名失败不显示可安装。缓存已签名信息与“上次检查时间”，过期标明，不能将旧缓存声称刚检查过。API 故障时可尝试固定仓库 latest/download 清单地址（稳定通道）；失败即提供离线导入。

建议初始网络值：连接 5 秒，读空闲 15 秒，检查总预算 20 秒，最多两次带退避的重试；下载只设空闲超时和用户取消，不设小机器无法完成的总时限。若底层不能独立设置连接/读超时，用一种明确实现并写测试，不能声称标准库已自动分别支持。取消/操作开始时停止新请求，现有读在短超时内退出。

有更新时主界面出现“有新版本 0.x.x”，打开详情显示当前/目标版本、三语变更、预计下载量、配置保留说明和按钮“下载更新”“稍后”“忽略此版本”“导入离线更新”。版本忽略仅影响提醒，手动检查仍可找到。下载显示真实字节/总字节、速度、取消和重试，不显示虚假完成率。

HTTP 断点使用 `.part`，绑定目标哈希、size、ETag；Range 请求只有返回匹配的 206 Content-Range 才追加，200 必须重建，416 检查完整哈希，否则重建；服务端变化/截断/错误页均不能当成成功。下载并发最多 2，整段哈希完成后再标记 ready。可复用本地哈希相符文件和已验证缓存，但安装前再次核对基线以免用户在下载期间改包。

离线导入共用 manifest/签名/计划/事务，不运行 ZIP 中代码或脚本。流式展开并严格检查 zip-slip、重复成员、大小、压缩炸弹和额外条目。完整离线包适用于任意受支持的更新器基线；小差异包若本地缺所需 blob，显示“此离线包不适用于当前文件，请导入完整离线更新包”，不可静默联网或半装。用户可以在可访问 GitHub 的另一台电脑下载，再用 U 盘复制。**仅 GitHub 无法保证所有地区直连；离线包提供可操作的替代途径，不是突破网络限制。**

## 5. 安装事务与回滚

状态机：`idle → checking → available → downloading → ready → waiting_for_exit → staged → applying → pending_health → committed`。任一步失败记录具体原因，下载失败回 available，安装失败进 rolling_back/recovered；恢复失败保持 recovery_required，不启动混合版本。

### 5.1 安装前

1. 用户点击安装后再次检查所有工具操作已结束，保存 profile/settings/presets 待写事件，释放输入并停止热键；未知失败留在旧版本，不能强杀游戏或其他程序。
2. 独占安装目录命名互斥锁（规范路径+用户 SID）；额外多进程检查只针对同目录 ColorStudio 的 PID/创建时间。已有另一实例则提示先正常退出；不同目录副本不互相误阻断。
3. 暂存独立 updater 到安装树外的该次事务目录，包含其所需运行库；不能直接用正在替换的 `_internal` 跑 helper。首版建议小型 PyInstaller onefile 更新器，仅校验、替换、进程和恢复依赖；验证无需管理员可启动。旧 helper 执行本次事务，新 helper 作为普通目标文件供下次使用。
4. 记录事务 UUID、规范安装根、原进程 PID/创建时间、活动 DATA、完整 old/new 清单摘要、操作列表/哈希、阶段、备份位置。事务文件仅当前用户和管理员可写，原子 write+flush+fsync+replace；提权 helper 必须重新验签并重新计算计划，不能信任用户可改的任意路径指令。
5. 预估空间 = 压缩缓存 + 所有变化文件展开 + 被替换/移除文件备份 + helper + 日志余量，并分别核对涉及磁盘。目标旁同盘 staging 用于原子逐文件 rename。目录不可写时说明可选择管理员重试或复制到可写目录，不循环弹 UAC；取消 UAC 旧包仍可使用。异用户提权不自动执行，避免错误 DATA 归属。

### 5.2 应用与恢复

- helper 获得父进程句柄/创建时间校验并等待正常退出后，才开始修改；等待超时取消安装保留旧版，不终止用户进程。
- 写前日志记录 intent；替换前将旧文件移动到备份，再将已经完整验证的 staged 文件原子改名到目标，记录完成。最后替换主 EXE 和 ownership manifest。多个文件并非一个原子操作，因此日志恢复是必需的，不能称“整个包原子替换”。
- 引导版本的 EXE 在导入 UI/OpenCV 前检查未完成事务：若 applying/recovery_required，只启动外部恢复 helper，不运行混合版本。新 EXE 同样支持。安装锁覆盖文件动作；启动健康检查由事务 token 授权，不绕过锁直接进入正常运行。
- 文件被杀毒软件/第三方锁住：短暂有界重试，仍失败就回滚已完成动作；不要求关闭杀毒，不无限等待，不为释放锁杀进程。突然断电后根据 intent/当前文件/备份的哈希判定哪个 rename 已发生；操作幂等。恢复也失败时保留日志、备份及独立恢复入口，提示具体路径，不清理恢复证据。
- 删除也是移动到备份，提交健康后才按保留策略清理；保留至少最近一次成功更新的完整回滚材料直到后续一次正常启动。清理只处理本工具生成且清单记录的 UUID 目录，不任意递归用户路径。
- helper 先启动新版本 `--update-health-check <transaction>`：导入必要依赖、核对包身份/资源、创建并销毁隐形 Tk 测试窗，不读游戏、不注册全局热键、不写用户配置；验证成功后启动正常 UI，并要求其完成 UI 初始化后写含事务 token+版本的 ready 信号。超时需明确慢机等待提示/可重试（初始建议 90 秒），不可把网络不可达或游戏未开当成失败。
- pending_health 阶段正常启动禁止配置 schema 迁移/自动写回，先完成就绪握手；提交后才写设置。首版新版本必须保持数据 schema 双向兼容，不做破坏迁移。未来需要迁移时单列用户文件备份/迁移日志/回滚策略，不能拿安装备份覆盖用户更新后新数据。
- 新版本自检崩溃/ready 失败，先确认该次进程已退出，恢复旧程序文件和旧 ownership 清单，保留用户 DATA 内容；展示恢复结果。不循环自动再装同一失败版本。
- 运行来源必须是普通本地目录；UNC/网络盘、重解析路径、不能保证锁和同盘 rename 的位置首版明确引导复制到本地可写目录。中文/空格/4K 高 DPI/多用户/普通与管理员账户纳入验收；架构不匹配不能运行更新器。当前只发布 win-x64，ARM64 若跑 x64 模拟需通过实际包测试，不虚构原生支持。

## 6. 可维护模块和接口

新代码放 `work/studio/updater/`，禁止把安装逻辑塞入已有大型 app.py。

| 新文件 | 单一职责 / 对外接口 |
| --- | --- |
| `types.py` | 冻结 dataclass：Manifest、FileEntry、BlobEntry、UpdatePlan、ProgressEvent；计划不含可执行代码 |
| `manifest.py` | `verify_manifest(raw: bytes, signature: bytes, trusted_keys: dict) -> Manifest`；schema/路径/平台验证 |
| `discovery.py` | `check_release(current_version: str, channel: str, cache: dict, cancel) -> CheckResult`；HTTP 通过注入 client |
| `planner.py` | `plan_update(root: Path, old: Manifest, new: Manifest) -> UpdatePlan`；差异、冲突、空间与保护数据目录 |
| `download.py` | `prepare_blobs(plan, cache_dir: Path, cancel, emit) -> Path`；下载/恢复/验签后展开准备 |
| `offline.py` | `import_offline(archive: Path, cache_dir: Path, cancel, emit) -> Manifest`；安全解包；复用 planner |
| `transaction.py` | `apply_update(transaction_dir: Path, emit) -> None`、`recover_update(transaction_dir: Path) -> None`；日志幂等/备份/恢复 |
| `win_process.py` | 同安装目录锁、PID创建时间、权限、reparse/文件锁、受控启动和健康握手 |
| `service.py` | `UpdateService`：check/download/import/cancel/install 状态机；所有事件进入 app 队列，不操作 Tk |
| `ui_update.py` | 主窗更新按钮/详情/进度/离线导入；不用搜索浮窗承载更新，不改变游戏焦点 |
| `update_helper.py` | 独立 helper CLI；只接受自己的 transaction UUID 与定位信息，重新验签和重算路径 |
| `update_bootstrap.py` | app import 之前识别事务/健康模式/恢复入口；避免导入未完整安装的大依赖 |
| `scripts/build_update_assets.py` | 产物清单、压缩 blobs、签名、完整/差异离线包、体积差异报告 |
| `scripts/verify_update_assets.py` | 清单/所有 blobs/离线包/所有者集合与便携包逐文件一致性验证 |

`CheckResult` 包含状态、验证后 Manifest、检查时间和本地化 reason_code，不返回任意远端文案 HTML。`UpdatePlan` 至少包含 installs/removals/reused/conflicts、old/new 清单摘要、所需 blob 集合、download_bytes、stage_bytes、backup_bytes、protected_paths。`ProgressEvent` 为 kind + received/total + reason_code + version；日志脱敏，不含 token/用户名全路径；本地诊断可保留必要路径。Manifest 对解析后的 `files` 使用 tuple，禁止业务层随手改签名后的内容。

## 7. 用户文本初稿（实施时三语同步）

| 状态 | 简中 | 繁中 | English |
| --- | --- | --- | --- |
| 发现 | 有新版本 {version} | 有新版本 {version} | Update available: {version} |
| 下载说明 | 预计下载 {size}，保留当前设置和染色方案。 | 預計下載 {size}，保留目前設定與染色方案。 | Download: {size}. Your settings and dye presets will be kept. |
| 正在操作 | 结束当前操作后可更新。 | 結束目前操作後即可更新。 | Finish the current operation before updating. |
| 就绪 | 更新已准备好，安装将关闭并重新打开工具。 | 更新已準備完成，安裝將關閉並重新開啟工具。 | Ready to install. The tool will close and reopen. |
| 断网 | 无法连接 GitHub，不影响寻色。可稍后重试或导入离线更新包。 | 無法連線至 GitHub，不影響尋色。可稍後重試或匯入離線更新包。 | Cannot reach GitHub. Color search is still available. Retry later or import an offline update. |
| 回滚 | 更新未完成，已恢复原版本；用户资料已保留。 | 更新未完成，已恢復原版本；使用者資料已保留。 | Update failed. The previous version was restored and user data was kept. |

“已保留资料”“已恢复原版本”只能在验证成功后显示；恢复失败必须显示恢复待处理，不能套用成功文案。大小/字节进度来自实际清单。签名不符提示包无法验证，可重新获取官方包；不要把它误报为时间不足。

## 8. 必测边界与通过标准

| 组 | 场景 | 必须观察到 |
| --- | --- | --- |
| 版本 | rc8→stable、稳定→rc、同版本、旧缓存/撤回、架构不符、minimum_updater更高 | 只推荐兼容更高版本；需新引导版时给手动升级说明 |
| 网络 | GitHub阻断、DNS/TLS失败、系统代理、403/429/304、半截下载、200/206/416变化 | 不阻塞寻色；不执行坏包；可取消/重试/离线 |
| 差异 | EXE改动、依赖改动、缺文件、同哈希复用、大小写冲突、用户改过旧文件 | 下载量准确；只操作有权管理的文件；冲突可见 |
| 离线 | 完整包跨多个旧版、小包wrong-base、签名坏、Zip Slip/炸弹/重复/链接条目 | 兼容可装，不兼容完全不改安装目录 |
| 事务 | 每个日志/rename边界中断、helper被杀、断电模拟、磁盘满、杀毒锁文件 | 可幂等恢复旧/新完整状态，不能启动混合依赖 |
| 数据 | portable/LocalAppData/temp回退，data里任意子文件和未知文件 | 字节哈希一致；不切换数据归属；不删除历史 |
| 权限 | 普通/管理员、UAC取消、多实例、异用户、中文/空格/长路径、只读目录 | 不强杀、不无限提权；准确说明下一步 |
| UI | 三语、100/150/200% DPI、窄窗、更新时用户开始染色、关闭对话框 | Tk响应、操作互斥；退出不遗留线程或输入 |
| 健康 | 新exe导入失败/资源缺失/Tk失败/冷启动慢/正常UI未ready | 失败恢复且旧包能启动；正常确认后才清理 |
| 发布 | 从rc8同依赖到引导版、引导版到下一小版 | 真实冻包演练，两次更新；第二次只下载变化文件 |

日常 quick 只纳入纯 schema/version/path/diff/state 单元测试；下载/崩溃注入/冻包/UI在 release。不要用上百条重复全局寻色路线证明更新功能。所有更新测试使用临时目录和伪服务，不修改桌面工具或游戏。GitHub在线真实读取烟测允许只读，创建/发布需明确授权。

## 9. 按依赖实施任务

每项按“写代表失败用例→跑红→实现→跑本项→同步明确文件→本地提交”执行。下列命令均在开发目录运行，先设置 `$env:PYTHONPATH='work/studio'`。测试示例定义验收行为，实施时在相应测试类中构造签名和目录 fixture；不要仅复制断言而缺边界验证。

### Task 1：可信清单、版本与安装所有权

**Files:** 新建 updater/types.py、manifest.py、planner.py；test_updater_manifest.py、test_updater_plan.py；修改 requirements/构建依赖锁。

- [ ] 写失败用例，使用测试 Ed25519 key pair；验证篡改单字节拒绝、三种 traversal、Windows别名冲突、data目标拒绝、rc8到正式版成立。

```python
def test_old_modified_file_is_never_scheduled_for_removal(self):
    self.install_owned('obsolete.dll', b'original')
    (self.root/'obsolete.dll').write_bytes(b'user edit')
    plan = plan_update(self.root, self.old_manifest, self.new_without_obsolete)
    self.assertNotIn('obsolete.dll', plan.removals)
    self.assertIn('obsolete.dll', plan.conflicts)
```

- [ ] 执行 `python -m unittest test_updater_manifest test_updater_plan`，确认失败属于未实现行为。
- [ ] 实现第 3 节签名/schema/路径与差异规则；版本比较使用 Version，所有者清单随引导版出厂并验签。未知旧版不能按清单任意删除。
- [ ] 跑绿并记录下载/空间统计；本地提交 `feat: validate signed update manifests and file plans`。

### Task 2：生成可验证发布资产

**Files:** scripts/build_update_assets.py、verify_update_assets.py、test_update_assets.py；build_release.py、verify_release.py。

- [ ] 临时两版包 fixture：一个 exe变化，一个 DLL相同，一个旧文件删除；验证完整离线包自包含，差异包只含所需变化 blob。

```python
def test_manifest_matches_every_application_file(self):
    result = self.build_assets(self.clean_package)
    self.assertEqual(result.file_hashes, self.hash_application_files())
    self.assertFalse(any(p.startswith('data/') for p in result.file_hashes))
    self.assertEqual(result.changed_blobs, self.expected_changed_blobs)
```

- [ ] `python -m unittest test_update_assets` 跑红；实现固定时间戳 ZIP 和全文件哈希、测试/正式密钥分离、差异报告。参数明确 `--package --previous-manifest --version --channel --key-file --out`；密钥路径不打印、内容不入包。
- [ ] 构建产物验证 CLI：`python scripts/verify_update_assets.py <out> --package <clean-package>`；篡改任一文件必须非零退出。
- [ ] 跑绿并提交 `build: generate signed file updates and offline packages`。

### Task 3：GitHub发现、断点下载与离线导入

**Files:** updater/discovery.py、download.py、offline.py；test_updater_network.py、test_updater_offline.py。

- [ ] 注入假 HTTP client/本地测试服务，不用真实互联网测试重试；覆盖304无缓存、429、取消、Range忽略、签名错误和wrong-base。

```python
def test_range_ignored_restarts_instead_of_appending(self):
    self.partial.write_bytes(b'old-prefix')
    self.server.respond(status=200, body=self.target_blob)
    self.download()
    self.assertEqual(self.completed.read_bytes(), self.target_blob)
    self.assertFalse(self.partial.exists())
```

- [ ] `python -m unittest test_updater_network test_updater_offline` 跑红；实现第4节超时、代理、限流、hash校验、无网络离线操作。ZIP成员流式处理，禁止 extractall 无校验。
- [ ] 断网条件下完成离线准备；取消保留可验证 partial，不误报告 ready；跑绿并提交 `feat: prepare updates from GitHub or offline archives`。

### Task 4：独立安装器、日志恢复与健康门控

**Files:** updater/transaction.py、win_process.py、update_helper.py、update_bootstrap.py；test_updater_transaction.py、test_updater_windows.py；app.py早期分发和build_release.py。

- [ ] 对每个 write-intent/rename/write-done 注入终止点，重启恢复；至少覆盖替换、删除、新建、主exe和ownership。fixture在全树放用户文件并保存哈希。

```python
def test_crash_after_backup_recovers_data_and_program(self):
    before = self.hash_all_user_files()
    self.apply_until_fault('old_file_backed_up')
    recover_update(self.transaction_dir)
    recover_update(self.transaction_dir)  # recovery is idempotent
    self.assertEqual(self.hash_all_user_files(), before)
    self.assertEqual(self.hash_program_files(), self.old_program_hashes)
```

- [ ] `python -m unittest test_updater_transaction test_updater_windows` 跑红；实现第5节状态和权限，先做文件事务，再接PID/锁/退出握手，最后健康回滚。helper必须独立于安装中的 `_internal`。
- [ ] 冻包健康模式不启动游戏、不热键、不保存用户数据；测试两实例、锁定DLL、磁盘满、UAC取消、恢复时再次中断、pending事务重启。
- [ ] 全组跑绿，提供临时目录可重复崩溃演练脚本；本地提交 `feat: install updates with recovery and startup health checks`。

### Task 5：用户可控三语UI与设置

**Files:** updater/service.py、ui_update.py、app.py、ui_strings.py、ui_settings.py；test_updater_service.py、test_updater_ui.py。

- [ ] 写状态机和隔离Tk测试：检查不下载、下载不安装、busy不开始安装、F8在下载期间先取消/暂停下载、取消对话框不结束染色、忽略不阻断手动检查。

```python
def test_busy_session_keeps_update_ready_without_installing(self):
    self.service.mark_ready(self.plan)
    self.app.busy = True
    self.click_install()
    self.installer.assert_not_called()
    self.assertEqual(self.service.state, 'ready')
    self.assertFalse(self.runner.stop.is_set())
```

- [ ] `python -m unittest test_updater_service test_updater_ui` 跑红；只用线程队列回主线程刷新，更新检查延后到窗口初始化完成，无无限重试定时器。
- [ ] 实现三语第7节文案和真实字节进度、版本/下载量、离线选择、退出前待写设置 flush；保持搜索浮窗与游戏不受影响。
- [ ] 三语和DPI测试、关闭重开测试跑绿；本地提交 `feat: add user-controlled update and offline import UI`。

### Task 6：验收、文档和引导版交付准备

**Files:** test_updater_packaged.py；scripts/run_tests.py、TESTING.md、三语README、版本发行说明、VERIFICATION.md。

- [ ] 按第8节矩阵记录结果和未覆盖机器；quick只加入廉价契约组，release加入冻包/事务/UI。单独更新测试可用 `python -m unittest discover -s work/studio -p 'test_updater*.py'`。
- [ ] 在隔离目录进行真实旧冻包→新冻包更新和新版本失败回滚：校验所有应用文件、用户DATA、未知文件和新UI可启动；证据包含下载字节/完整包对比，不能只声称“增量”。
- [ ] 验证最小引导版无密钥/用户文件泄露；包不带任何 `data`。实际签名密钥由维护者安全生成保存；无正式密钥时仅完成测试签名包，不能发布成正式更新源。
- [ ] 更新三语用户说明：旧版需首次手动升级、离线包差异/完整区别、不可达GitHub的处理、失败恢复目录、权限处理。
- [ ] 执行项目 quick；发布前执行 release 与资产校验。当前两份 rc16必要历史素材缺失应如实记录，不能绕过验收或扩大跳过白名单。
- [ ] 本地提交 `docs: document verified bootstrap and incremental update workflow`，交付明确文件清单、测试结果和发布步骤；尚未得到本轮正式发布授权时停止在可审查产物。

## 10. 发布操作顺序

1. 维护者安全准备 Ed25519 签名密钥并把公钥固定入引导版；私钥不上Git，不使用测试key正式发布。代码签名证书可改善SmartScreen体验，但不能代替更新清单签名；没有证书时诚实说明Windows可能提示未知发布者。
2. 固定依赖构建干净完整包与独立helper，生成最终所有者清单；避免循环哈希：清单/签名不自列为受管理负载，其写入是事务收尾元数据。包中公钥源文件与helper本身仍列入应用所有权。完整便携 ZIP 可在清单生成后封装，清单不包含完整ZIP的自引用摘要。
3. 生成清单/签名/blobs/离线完整包和一个受支持base的小离线包；校验全文件集合、总下载大小、单asset GitHub限制与资产名长度；过大的单blob拆分成签名chunk列表或使用完整包提示，不上传超限资产后才发现。
4. 获正式发布授权后创建draft，一次上传所有资产；从GitHub重新下载manifest/signature和代表性blob验签，确认assets齐全再发布。发布客户端不得在draft/部分上传时推送按钮。
5. 引导版发行说明明确“以后可在工具内更新，此前版本需手动下载一次”。稳定和预发布通道分开；不能只加一个版本检查按钮却没有可靠更新器。
6. 出现坏版先撤回推荐元数据/发布，避免继续分发；已下载用户依靠签名版本和健康失败回滚。撤回清单不等于远程删除用户文件；不要静默强制降级。

## 11. 下一模型接续入口

可直接给下一模型：

> 请按 `docs/superpowers/plans/2026-10-11-auto-update.md` 实现自动更新。用户已选 GitHub＋离线包，不部署镜像。开发目录是 project，实际Git在同级 ColorStudio-handoff-2026-10-04/repo；不复制私有数据。先读取当前Git状态和本计划，完成 Task 1–6 的本地实现与验证，再给可审查候选。没有新一局染色或正式发布授权，不消耗道具、不发布。保留全部用户文件、最多3秒尾余量及原搜索策略；不要重新实现本轮已完成的细化提示。

本计划不需要用户在“内联/子代理”间再次选择，用户已表示会换模型继续本对话。是否发布、正式签名密钥安排由交付阶段解决；前面的离线实现和测试可自主推进，不因没有CDN或证书停止。

## 12. 本轮提示功能的交接边界

rc8 仅增加细化阶段经游戏实测复核的当前HEX/ΔE与用户批准的等待说明，并同步主窗及三语浮窗。控制器把已复核anchor随进度事件发送；后续验证提升anchor时更新显示。它不把预测候选当实测、不展示增长路线数、不更改搜索范围/时限/动作，也没有自动更新实现。

实际桌面操作与截图验证在隔离UI中进行，不读取或操作游戏。完整发布结论仍受原历史素材缺失限制。浮窗本来排除屏幕捕获，UI测试截图只在测试fixture中临时取消排除，生产行为不变。

## 13. 2026-10-12 实施状态

Task 1–5 的本地模块、主窗入口、独立 helper 和测试已接入；Task 6 的签名测试资产、冻包成功升级/失败回滚及数据哈希验证完成。完整/差异包共用目标清单，差异基线另用签名 offline-base 描述，避免连续离线更新的基线分歧。首版对程序文件冲突引导手动使用完整官方包，不自动提权。

正式公钥及发布私钥未生成；测试密钥只用于隔离包。当前不推送/发布。历史 rc16 两份必要相似素材缺失，正式 release verdict 仍不完整。实施证据和首版边界见 `docs/verification-auto-update-2026-10-12.md`。韩国服后续任务见 `docs/superpowers/plans/2026-10-11-server-adaptation.md`，不要宣称已经支持韩国客户端。
