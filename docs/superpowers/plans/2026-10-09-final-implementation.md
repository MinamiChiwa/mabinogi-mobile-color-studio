# ColorStudio 最终实现推进计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 默认在当前会话顺序实施；不据本文自行创建子代理。真实游戏实验和正式发布使用独立确认门。

**Goal:** 在真实 120 秒预算内提供单区、双区、三区可信实测结果，精准未命中仍保留妥协，完成机制验收后才发布。

**Architecture:** 保留现有视觉闭环，先补共享证据和预算，再验证本局动作能力、单区恢复与增量多区。完整 48 步留作对照；局部候选必须有独立支持和安全返回条件。跨局复用及其它设备响应不属于首版默认承诺。

**Tech Stack:** Windows、Python 3.12、NumPy/OpenCV、Tesseract、CustomTkinter、unittest；pytest 为可选开发入口。

**Spec:** `docs/superpowers/specs/2026-10-09-final-implementation-design.md`。新接口、测试名和实验命令在以下任务完成前只是实施契约，不是当前可运行功能。

## Global Constraints

- 推荐游戏客户区 1280×960；实验中不改变 DPI、窗口、画板外部状态。
- 游戏正式染色开始就计消耗 1 枚，不以确认点击判断成本。
- 每次新增实机验证单独确认、最多 1 枚；不自动重试或连续开局。
- 当前 `0.3.6` 保持验证中技术候选；正式验收前不改标签、不覆盖发布包。
- 不自动开始、确认、套用或取消游戏染色。
- 默认收尾保留 15 秒；慢返回或慢 OCR 只增加保留，不侵占它。
- 精准模式未命中继续有界找近似；最终只有双帧实际 HEX 可标记达标或已定位妥协。
- F9、失焦、窗口变化、真实截止后不发送返回或补读色输入。
- 质量矛盾、配准未知等故障停止新输入，按既有上限 3.5 秒只读当前 HEX。
- 缺失 HEX、截图、姿态、残差和库存证据保持未知；不得用预测、逆变换闭合或图谱缺色代替实机真值。
- 每个任务先运行相关生产/诊断用例；共享边界变动后运行 all。测试数量不作为验收目标。
- 实施时保留既有工作树与原始会话；禁止 reset/clean、全量覆盖或顺手删除 legacy。

## 里程碑与资源

| 里程碑 | 任务 | 完成依据 | 新染色剂 |
| --- | --- | --- | ---: |
| M0 接手基线 | 0 | 文档与版本身份一致、原始证据有副本 | 0 |
| M1 离线闭环 | 1–2 | 证据与预算贯通，初始/历史最佳保护 | 0 |
| M2 候选能力 | 3–6 | 动作能力门、单区恢复、渐进多区与像素反馈离线通过 | 0 |
| M3 首局验收 | 7 | 一局综合机制/三区混合报告及用户确认 | 最多 1，单独确认 |
| M4 模式验收 | 8 | 五类配置有当前策略的实机证据 | 每次最多 1，单独确认 |
| M5 发布 | 9 | 实机门、全量测试、构建身份与发布说明 | 0 |

保守规划约 5–6 局：五类配置各一局，综合机制局若满足三区混合完整指标可以合并，否则单独计一局。已有效验证的当前策略证据可以减少局数。这个估计不是总成本承诺，也不是累计授权；失败分析后才提出下一局，额外重复要重新说明原因与累计成本。

依赖顺序：0 → 1 → 2 → 3/4 → 5 → 6 → 7 → 8 → 9。3 与 4 可分别审查，但均在 2 的证据/预算接口上工作。

## 文件与职责

| 文件 | 责任 | 处理 |
| --- | --- | --- |
| `work/studio/search_evidence.py` | 本局时间、观察和结果指标 | 新增，不包含 Windows 输入 |
| `work/studio/workflow_budget.py` | 动作、CPU 阶段与收尾预算 | 扩展现有实现 |
| `work/studio/response_profiles.py` | 本局分条件动作能力 | 新增，不安装跨局参数 |
| `work/studio/incremental_atlas.py` | 连续帧累计、局部支持与快照 | 新增，复用 CaptureAlignment/PeriodicAtlas |
| `live_atlas_capture.py` / `atlas_capture_worker.py` | 采集、守卫与有界后台任务 | 保留逐帧质量边界 |
| `atlas_live_adapter.py` / `atlas_service.py` | 候选绑定、验证、检查点与终态 | 接入上述边界，不重写 UI |
| `single_region_search.py` / `single_region_live.py` | 单区探索和倍率层恢复 | 加强现行流程 |
| `hex_feedback_search.py` / `atlas_execution.py` | 稳定 HEX 与有限整数邻域 | 保持全部启用区共同评分 |
| `gesture_response_probe.py` / `mechanism_experiment.py` | 一局综合实验与报告 | 显式实验入口 |
| `search_overlay.py` / `ui_progress.py` / `ui_strings.py` | 当前/历史、妥协及故障提示 | 三语同步 |
| `run_tests.py` / `TESTING.md` | 测试范围与缺失素材 | 新增用例正确分类 |

## Task 0：冻结可追溯基线与修正文档结论

**Files:** 修改 `PROJECT_STATUS.md`、`GAME_MECHANISM_VALIDATION_GATE.md`、`VERIFICATION.md`、`REACHABLE_SEARCH_PLAN.md`；创建 `outputs/final-implementation-baseline-20261009/manifest.json` 和证据副本。

**Interfaces:** 消费 Git 状态、`build_info.source_identity()`、现有 build-info 与原始日志；产出只读证据清单、当前指纹及事实/推断分栏。原始 JSON 不回写。

- [x] 记录 dirty 文件列表、HEAD、源码指纹、EXE 指纹和测试基线；不把同为 0.3.6 当成同一实现。
- [x] 复制现存机制报告及最近有效会话到不会被 sessions 清理的独立目录；不存在的旧资料记 missing，不捏造补全。
- [x] 删除当前文档中“未确认所以未消耗”的结论，明确进入正式倒计时按用户规则计 1；记录历史软件无确认事件与资源成本是不同事实。
- [x] 把“游戏无精确白色/三区无解”改为“当前重采样图谱未记录精确目标”；撤销由这项推断产生的永久停止规则。
- [x] 对冲突的“最新”记录按会话日期与源码指纹整理；标明当前精准未命中继续妥协的修订仍待实机。
- [x] 运行 production、格式检查；只提交这一任务涉及的文档和清单引用，不提交私有截图。

**完成门:** 接手者能准确区分当前源码、旧包、历史现象、待验收修复；实验成本规则一致。没有新游戏操作。

## Task 1：统一本局指标并贯通真实预算

**Files:** 新增 `search_evidence.py`、`test_search_evidence.py`；修改 `workflow_budget.py`、`test_workflow_budget.py`、`atlas_stage_budget.py`、`atlas_live_adapter.py`、`live_atlas_capture.py`、`single_region_live.py`、`mechanism_experiment.py`。

**Interfaces:**

- `RoundEvidence(session_id: str, source_sha256: str, rules: list, game_deadline: float)`。
- `record_duration(stage: str, seconds: float) -> None`；stage 为 capture、registration、ocr、search、binding、input、return、verification、storage。
- `record_observation(codes: list, frame_ids: tuple, pose: list | None, pose_epoch: int, verified: bool, now: float) -> dict`。
- `report(now: float) -> dict`：指标、样本数量、未知字段及最终剩余时间；颜色用既有评分，`verified` 仅来自两帧一致实读。
- `WorkflowBudget.allow_operation(*, now, operation_seconds, return_seconds, verification_seconds, positioning_seconds=0.) -> bool`。额外定位成本用于搜索/绑定阶段，已有 API 向后兼容。

- [x] 写预算反例：过去只在动作前检查，搜索/绑定已耗尽定位时间；未知耗时不得自动按零计费。

```python
def test_search_cannot_spend_the_final_return_and_double_read_budget(self):
    budget = WorkflowBudget(0., 120.)
    self.assertFalse(budget.allow_operation(now=98., operation_seconds=5.,
        return_seconds=12., verification_seconds=4.))
    self.assertTrue(budget.allow_operation(now=80., operation_seconds=5.,
        return_seconds=12., verification_seconds=4.))
```

- [x] 跑相关用例，先看到新预算接口缺失或旧生产调用未留预算的失败。
- [x] 实现校验与公式：reserve=`max(finish_reserve_seconds, return_seconds + verification_seconds + 2)`；required=`operation_seconds + positioning_seconds + reserve`；严格小于硬截止才允许。
- [x] 统一阶段计时；少于 20 个有效样本使用观测最大值/保守默认的较大者，之后使用受保守下限保护的 P95。读色分别标识本次验证与最终验证，避免重复计费。
- [x] 正式绑定默认启用预算保护；候选分批绑定，保留已绑定可执行候选，预算触发不清空它们。搜索原生调用不可严格抢占时以有界批次检查，输入守卫仍独立有效。
- [x] 完成配准耗时均值/P95、首次已定位结果与最终实测剩余时间的报告；未观测到的值保持 null。
- [x] 用历史日志重放 CPU 慢、OCR 慢、动作后返回变远三类情形；运行 production 和 all 后精确提交。

**完成门:** CPU、输入、配准和读色都遵守一个硬截止；下一探索不能吃掉定位/返程尾部。源码测试不等于实机性能达标。

## Task 2：任何探索前建立实测检查点并统一收尾

**Files:** 修改 `atlas_service.py`、`atlas_live_adapter.py`、`live_atlas_capture.py`、`single_region_search.py`、`search_overlay.py`、`ui_progress.py`、`ui_strings.py`；扩展 `test_atlas_checkpoint_recovery.py`、`test_atlas_service.py`、`test_single_region_search.py`、`test_search_overlay_atlas.py`。

**Interfaces:** 使用 Task 1 的观察字段；复用 `_measured_quality()` / `candidate_quality()` 判断真实结果，保留 `best_result_current`、`historical_best_unrestored`、`positioning_complete`，增加 `baseline_result` 与 `best_observed_result`。旧调用方仍可读取原结果字段。

- [ ] 写真实颜色反例：先观察近白，后到深色，预算结束应返回近白；验证失败时不能把保存近白显示为当前色。复用现有 FakeIO，避免再建一套同源几何模拟。

```python
def test_exact_miss_restores_measured_near_white_after_a_worse_trial(self):
    io = FakeIO(color=lambda offset: '#FFFEFE' if not offset.any() else '#777777')
    with patch('single_region_search.visible_candidates',
               return_value=[dict(source=np.array([85., 180.]))]):
        result = run_single_region(io, scene(), rules('#FFFFFF', exact=True),
            game_deadline=100, limits=QuickSearchLimits(max_candidate_trials=1, max_explorations=0))
    self.assertEqual(result['actual_colors'][0], '#FFFEFE')
    self.assertTrue(result['best_current'])
    self.assertTrue(result['compromise'])
```

- [ ] 先运行上述反例及多区故障/停止用例，分清已满足的行为与真正缺失的路径。
- [ ] 在进入可操作画板后、首个输入前记录双帧基线及姿态参考；后续校准也必须有离开/返回基线的预算。
- [ ] 正常探索预算结束只执行有证据的最佳定位与复核；故障或安全中断执行既有停止语义，不盲目返回。
- [ ] UI 区分“已定位妥协”“只读当前颜色”“此前最佳未恢复”，展示各区真实 ΔE；同色但不同位置只在实测证据相符时更新检查点。
- [ ] 扩展三语回归，运行 production 和 all，精确提交。

**完成门:** 精准未命中不是失败条件；未知姿态不是继续找色的理由。只读 fallback 不能被呈现为最接近候选已到达。

## Task 3：建立本局动作能力与配准复用证据

**Files:** 新增 `response_profiles.py`、`test_response_profiles.py`；修改 `gesture_evidence.py`、`gesture_replay.py`、`atlas_bound_route.py`、`atlas_live_adapter.py`、`atlas_runtime.py`、`single_region_live.py`；新增/扩展诊断回放用例并在 `run_tests.py` 正确分类。

**Interfaces:**

- `ResponseProfiles(session_id, geometry, dpi, source_sha256)`；不跨局缓存。
- `add_sample(*, kind, direction, condition, point_error, frame_ids, codes, held_out, passed) -> None`；condition 包含支点范围、倍率范围、输入协议。
- `allows(kind, direction, condition) -> bool`：至少 3 个可靠样本且有独立预测检查，通过 0.25 px 初始工程门槛；只适用于已有条件。
- `invalidate(kind, direction, reason) -> None`；`route_allowed(gestures, condition) -> bool` 对路线每步检查。

- [ ] 写少样本、只有逆变换闭合、跨局、方向不同、越过倍率/支点范围不能晋级的反例。

```python
def test_one_wheel_direction_does_not_authorize_the_other(self):
    profile = ResponseProfiles('round-a', (0, 0, 1280, 960), 96, 'source-a')
    condition = dict(anchor_band='center', scale_band=(.95, 1.05), protocol='integer-wheel-v1')
    for index in range(3):
        profile.add_sample(kind='wheel', direction=-1, condition=condition,
            point_error=.1, frame_ids=(f'before-{index}', f'after-{index}'),
            codes=['#A0A0A0'] * 3, held_out=index == 2, passed=True)
    self.assertTrue(profile.allows('wheel', -1, condition))
    self.assertFalse(profile.allows('wheel', 1, condition))
```

- [ ] 实现证据拒绝规则；原布尔 verified 字段由有效本局能力导出，不允许直接赋 True 绕过晋级。
- [ ] 从已有报告导入样本并逐项列出缺口；旧资料缺原始配对、DPI 或条件时只能标 observed，不能自动授权新局。
- [ ] 用同一前后截图离线对照“复用位姿/快速平移检查/完整配准”，记录三个取色点误差、总耗时和失败率；没有独立参考就不声称测得真实误差。
- [ ] 保持复杂动作、倍率变化、弱纹理、验证落点强制完整配准。快速路径最初只记录影子结果，不改变发送输入。
- [ ] 绑定、重绑定、重规划都使用本局条件门；未知动作保持平移方案与只读终态。运行相关 diagnostics、production 和 all 后提交。

**完成门:** 本局门可用但默认没有凭空获得的能力；没有证据不能为解决“没有候选”而放宽动作门。

## Task 4：完成单区域有限探索与倍率层恢复

**Files:** 修改 `single_region_search.py`、`single_region_live.py`；扩展 `test_single_region_search.py`、`test_single_region_zoom.py`、`test_single_region_zoom_bands.py`。

**Interfaces:** 保留 `run_single_region()` 参数、QuickSearchLimits 和现行返回字段；接 Task 1–3 的预算/本局能力，不新增整板拼图或旋转动作。

- [ ] 补跨倍率不可恢复、当前倍率有更好可返样本、完全没有精确样本、慢读色占用返程四类反例；已覆盖的用例直接复用，不重复新增。
- [ ] 初期保持约 60 秒主探索、最多 16 次缩放及现行相对倍率范围；所有动作同时通过共同预算门。
- [ ] 将全局最佳与倍率层最佳分别参与可返程评估；返回后游戏 HEX 不相符则明确未恢复，优先保留可验证倍率层结果。
- [ ] 动作无响应、能力失效或配准失败停止方向/输入；不发送盲目反向滚轮。
- [ ] 记录单区首次实测改善与最后复核时间；运行现行 single suites、production 和 all 后提交。

**完成门:** 单区不建全图；精准未命中仍有实测妥协。几何到达不能代替颜色恢复。

## Task 5：离线验证后接入增量多区域采集

**Files:** 新增 `incremental_atlas.py`、`test_incremental_atlas.py`；修改 `progressive_atlas_replay.py`、`atlas_capture_worker.py`、`live_atlas_capture.py`、`analyze_live_atlas.py`、`atlas_adapter.py`、`atlas_live_adapter.py`、`atlas_service.py`。

**Interfaces:**

- `IncrementalAtlasBuilder(scene, rules, check)` 复用 CaptureAlignment。
- `append(name, image, command=None) -> None`；只按相邻已观测帧添加。
- `snapshot() -> dict`：status、frame_count、pose、atlas、candidates、quality、cost_estimates；周期不足时 atlas=None。
- `local_candidate_gate(*, supported_regions, neighborhood_complete, heldout_passed, pose_reliable, return_allowed) -> bool`。支持全部启用区域才能返回 True。
- 正式入口增加显式实验选项 `incremental_capture=False`，初次实机前不替换默认 48 步。

- [ ] 先写“缺第三材质/缺一个邻域点/错误当前姿态/返回不可支付不得发布”的测试。

```python
def test_partial_map_cannot_publish_a_candidate_with_an_unknown_third_region(self):
    self.assertFalse(local_candidate_gate(supported_regions=[True, True, False],
        neighborhood_complete=True, heldout_passed=True,
        pose_reliable=True, return_allowed=True))
```

- [ ] 在已有真实轨迹上比较连续 6/12/18/24 步前缀和完整路线；周期、位姿、耗时都只能使用前缀信息，禁止借用后续帧或完整图的参数。
- [ ] 保留独立留出帧；分别报告采集输入数、注册帧数、建图帧数与实际候选质量，不能只报训练帧更少。
- [ ] 实现 insufficient_evidence/local_supported/global_supported/quality_failed 四种状态；全图 90% 门仅用于 global_supported，局部候选必须独立验证所需支持。
- [ ] 周期不足时只保留基线并有预算地获取信息；材料矛盾或配准未知立刻停止输入。不要以“局部搜索”绕过已有故障门。
- [ ] 候选采用少量绑定批次；有可信收益且能支付定位/返程时停采集，实测后决定改善或收尾。连续追加也要支付从预计下一姿态返回检查点的成本。
- [ ] 采集存储与配准可拆分队列，但质量失败必须在下一输入前可见；原生调用不能及时取消时报告延迟，不伪造严格实时能力。
- [ ] 离线质量/预算未优于基线时保留对照路线，先修证据缺口；通过后接显式实机实验开关。运行 diagnostics、production 和 all 后提交。

**完成门:** 相同时间预算下能产生全部启用区都有支持的候选，或诚实保留基线；不用“49 张图的少量锚点”宣称提速。

## Task 6：最终落点联合 HEX 反馈与结果一致性

**Files:** 修改 `hex_feedback_search.py`、`atlas_execution.py`、`atlas_live_adapter.py`、`atlas_service.py`、`search_overlay.py`；扩展 `test_hex_feedback_search.py`、`test_atlas_feedback_adaptive.py`、`test_atlas_compromise_recovery.py`、`test_candidate_ranking.py`。

**Interfaces:** 复用 `stable_hex_read()`、`score_observation()`、`retain_best()` 和执行 return_guard。外部每次输入都基于当前可靠 pose；算法只提出有限候选，不自行操作 Windows。`score_observation()` 的生产 `score_key` 统一为 `(not accepted, maximum_delta_e, average_delta_e, -exact_matches)`；现有 `score_codes()['rank']` 是按各区容差归一化的旧原型顺序，不能直接沿用作生产排序。保留该旧字段用于诊断，并补真实反例验证新 key。

- [ ] 补“第二区域改善但另外两区恶化”“一像素试探变差后返回”“局部更好样本没有返回时间”“只读色不得冒充定位”的反例。
- [ ] 将候选附近整数 3×3 邻域限制在一次最多 8 个试探，包含返程/双帧费用；能达标立即停，不能预算不足时仍走完整邻域。
- [ ] 按全部启用区域的真实最大/平均 ΔE 评分；预测精确命中不能跳过游戏 HEX。
- [ ] 只探索有可信收益和返回证据的邻居，误差/响应超范围立即结束；每次实测改善更新共同检查点。
- [ ] 保留精准分支和均衡妥协分支，不在动作绑定前按颜色去重。预测风险和实测质量分开记录。
- [ ] 运行具体反例、production 和 all；更新三语终态文案后提交。

**完成门:** 微调服务于联合质量；不会整局围绕一个区域无收益平移，不把历史结果当当前实测。

## Task 7：准备并执行一局综合机制/三区混合验证

**Files:** 修改 `gesture_response_probe.py`、`mechanism_experiment.py`、`live_atlas_capture.py`、`run_response_probe.ps1` 的协议选项；扩展 `test_gesture_response_probe.py`、`test_mechanism_experiment.py`；生成只读 `outputs/final-live-proposal-<时间>/proposal.json`。

**Interfaces:** 实施后新增 `comprehensive` 协议；接 RoundEvidence、ResponseProfiles 和预算。`run_comprehensive_probe(game, scene, reference, *, evidence, profiles, budget, search_current, snap, log) -> dict`；`search_current` 只从同一个 game、当前画面和已有增量快照调用候选流程，不重新进入游戏、不重新等待正式染色，也不重置截止时间。proposal 包含源码指纹、目标规则、拟执行动作、优先级、每步预计成本、跳过条件、预计 1 枚和收尾计划。不能通过运行入口自动点击开始。

- [ ] 写假时钟验证：低优先级动作预算不够时跳过，最终复核保留；故障/F9 后无新输入；本局不会重启第二次正式染色。
- [ ] 先在离线 IO 中完整运行协议及停止路径；确认命令在本机 PowerShell 与实际仓库路径可用，检查 Python/OCR，缺依赖先配置。
- [ ] 生成可审阅动作清单后才请求这一局确认，不先消耗资源再补说明。
- [ ] 确认后只读预检；用户准备 1280×960 游戏前台、目标染色物品和 1 枚染色剂，不改变窗口/DPI。失败不要求先进入染色。
- [ ] 执行优先级协议：0–10 秒双帧基线；10–30 秒重复小步平移及复用影子比较；30–55 秒双向滚轮/允许的旋转条件取证；55–105 秒按已获得能力尝试三区候选与有限微调；最后至少 15 秒只做已证最佳返回与双帧复核。真实耗时不足就跳过后续机制，不强行完成所有动作。
- [ ] 对精确依赖某方向的复杂动作，样本不足则不晋级；当局使用已支持平移。宏观配准与 HEX 都不过门时只读退出。
- [ ] 保存“已观察 / 基于观察推断 / 仍未验证”报告及完整指标；让用户确认结论。没有重复、目标色差或返程证据的项目保持未验证。

**完成门:** 这一局只消耗最多 1 枚，能解释每个动作和最后颜色；不要求用户为同一未修复问题重复消耗。若完整满足三区混合验收指标，Task 8 可复用该项。

## Task 8：按缺口逐局完成模式验收

**Files:** 修改 `GAME_MECHANISM_VALIDATION_GATE.md`、`VERIFICATION.md`；生成 `outputs/final-acceptance/<源码指纹>/matrix.json`，每份原始会话独立保留。

**Interfaces:** matrix 行包含配置、源码/包指纹、证据会话、期望达标规则、实际指标、失败原因、资源成本和是否可复用。配置变动后的离线评分不是独立实时搜索验收。

| 配置 | 验证重点 | 一局预算 |
| --- | --- | ---: |
| 单区精准 | 没有精准样本仍找近似，最佳恢复真实 | 最多 1 |
| 单区相似 | 连续两帧达标即停，不再无收益探索 | 最多 1 |
| 双区混合 | 两区域共同位姿、预算与精准妥协 | 最多 1 |
| 三区混合 | 三材质支持、联合改善、不围绕单区消耗时间 | 最多 1 |
| 三区精准 | 3/3 才算精准，其余明确妥协；不因图谱缺色直接停 | 最多 1 |

- [ ] 检查历史当前策略证据是否足以复用，不因会话同版本号就复用；新增修订影响过的路径要补验证。
- [ ] 每次提交具体配置、待回答问题和预计 1 枚，得到单次确认后才运行；每局结束报告累计预计成本及已确认进入回合次数。
- [ ] 比较初始基线、首次定位与最终结果；正常可靠姿态收尾必须保留/恢复已验证最佳，无法恢复必须明确异常原因。
- [ ] 五类配置记录最大/平均 ΔE、命中、首次结果时间、最终剩余、动作数、配准成本、返回与文案。目标未达标可以是有效妥协验收，但不能据此宣称高精准率。
- [ ] 性能目标未达到（10 秒基线、60 秒首次已定位结果、最终争取 15 秒手动余量）必须列出实际数值和原因。缺结果不算通过。
- [ ] 发现故障先离线复现、修复、相关回归；不自动再开局。若已有六局规划不足，说明新增理由和资源成本后重新决策。
- [ ] 失败组合保留在报告；要求用户确认实测妥协对该用途是否可用，不替用户定义颜色满意度。

**完成门:** 五种配置有可追溯实机结果，关键安全/最佳保护语义通过。跨设备/其它窗口不扩大声明；用户不认可实用效果时不进入正式发布。

## Task 9：构建可复现候选并决定发布

**Files:** 修改 `build_info.py`、`build_release.py`、三语 README、`VERIFICATION.md`、`PROJECT_STATUS.md`；创建新版本发布说明文件。版本暂定 0.3.7，实际以最终 Git 状态确定。

**Interfaces:** build-info 绑定版本、策略修订、源码 SHA、Git 提交；发布说明比较上一次实际发布包指纹，不能只比较最近对话或最后一个提交。

- [ ] 确认 Task 7–8 的用户结论及实机门；未满足时只留受限技术候选，不改正式状态。
- [ ] 精确提交相关代码/测试/文档，禁止 git add -A 把本机证据和其它未提交工作混入。生成当前测试分组报告，不把 deselected 或素材 skip 当作已通过。
- [ ] 运行 `python run_tests.py --profile all` 或 `python -m pytest -q -rs --test-profile=all`，执行 compileall、diff 检查及构建；缺构建依赖先配置。
- [ ] 使用隔离输出目录构建新版本；若门前需要本机候选包，必须用独立 preview 身份/目录，不覆盖既有 0.3.6 标签或资产。
- [ ] 核对 EXE build-info、Git 提交和源码指纹、三语文案、OCR eng 数据；检查无 profile/history/session 私有数据。
- [ ] 发布说明列出从上次包以来全部变化、每种实机样本/实际耗时、失败/妥协结果、限制和未验证范围；列出测试整理但不暗示改变游戏精度。
- [ ] 提供新包校验值与发布说明供用户审阅；获得发布确认后才推送新版本标签和资产，不改旧标签或同版本覆盖。

**完成门:** 用户认可的范围内完成产品闭环、证据与包一致。任何未验收复杂动作或模式都明确限制；不能把受限平移版本命名为完整多区域精准实现。

## 自检与停止条件

- [ ] 本设计中的每项产品要求能映射到上述任务及验收门。
- [ ] 接口名称与字段一致；新增 API 均在相应任务定义，不在执行时猜测。
- [ ] 新测试验证故障/外部行为，不为了数量新增重复测试。
- [ ] 零成本阶段完成前不要求用户进染色；新局必须有具体proposal和单次确认。
- [ ] 单次失败后只做分析，未修复同一问题不要求重复实机。
- [ ] 少量采集未通过独立局部质量门时保留既有安全行为，不降低阈值来“让测试通过”。
- [ ] 用户不同意增加消耗或接受限制时交付当前可审阅候选和剩余证据缺口，不宣称最终完成。

下一实际任务为 Task 0；它不消耗染色剂、不操作游戏、不改变正式发布状态。
