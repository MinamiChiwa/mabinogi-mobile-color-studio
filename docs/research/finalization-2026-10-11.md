# 0.4.0 收尾验证

本次范围为界面尺寸与 DPI 过渡、文本、自动保存和命名方案、区域优先级、测试分层，以及用户 rc16 三白相似失败的诊断修复。用户授权同步 Git 与发布。没有新染色局、游戏输入、道具消耗或自动套用。

## UI

rc16 `reflow` 将每个窗口宽度交给卡片重排，并对 CTkScrollableFrame 的内框调用继承的 `grid_configure`，导致它脱离 canvas window。现在颜色卡片保持固定宽，只有列数断点改变布局，外视口单独居中与调整；正常 Win32 重绘标志保留。

完整工具连续 16 次尺寸更新，自建窗口 `geometry()+update()` 不含故意等待，普通层平均 313.5ms、最大 376.4ms；WinEvent 通知触发的单快照层平均 11.98ms、最大 16.14ms。图像来自自身客户区 PrintWindow，截图失败回退到正常页面。没有替换 Tk WndProc。一个试验性的 WndProc 原型触发 GIL 崩溃，已经完全排除；最终回调只向队列写事件。

用户在发布回归期间截到的 v0.4.0/#010203 画面揭示第二个问题。可控复现及原生 HWND 清单证明只有一个主窗口和独立方案窗口，不能解释为多个主窗口重叠。100%/150% 分步切换时，CTk 子控件重新挂载隐藏页面并暴露旧像素。现在先挂载快照，暂存 CTk 页面几何管理缓存，整个同步缩放批次完成后重新布局、处理子控件 idle 绘制，再撤去覆盖。定时任务使用 after(0)，避免子控件内部 update_idletasks 提前执行 after_idle。原生拖动与缩放所有权独立，最小化/异常/销毁均清理。

真实屏幕 ImageGrab 对照中，旧代码即时画面重复控件和断层；修正后两轮 100%↔150% 即时画面为完整旧帧，随后为完整新帧。测试夹具先销毁窗口再恢复全局缩放，方案窗口不截获下一轮的主界面点击。最终定向 8 项检查通过，17.3s；后续最小化所有权故障检查 6 项通过。证据留在本地 UI 目录，不公开桌面截图。

## 规则与方案

全部启用区域达标是最优接受层。Explicit priority=1/2/3 时，未全达标先比较所有区域的命中位，再比较同顺序 Delta-E。候选生成与预截断、自动选择、原生预测、实测记录、路线细化及保护返回一致。旧 API 未指定 priority 时继续均衡排序。禁用区域忽略，替代颜色等价，Exact 不放宽六位 HEX。

当前设置 300ms 合并自动保存，关闭立即刷新；输入未完成亦保留。命名方案保存/编辑/载入/删除独立于结果历史。损坏草稿启动不覆写，用户修改时备份；写入失败不显示已保存。旧单份 profile 保留颜色与独立 settings 策略。

三语教程不要求固定游戏分辨率，备用策略有注释。材质不含纯黑白和多色精准成功率提示与当前规则一致。窄窗状态、方案说明随可用宽度换行。

## 相似故障

rc16 三白 ΔE≤8 在局部五秒帧解码预算耗尽时错误退出为 insufficient_time，整局仍约余 53 秒。修复分离 advisory timer 与真实 deadline，保留先前成功 OCR 值和同 checkpoint 原生值，并明确其截图来源。有限重读不重复输入；F9/真实截止仍生效。

原色板已有三色达标数学候选，但单目标编译 0.35s 与单向滚轮不能完成大旋转和倍率微调。新增两腿整数正反滚轮，完整 float32 回放并记录夹限、时长与动作；单目标编译 1s、整体三色阶段预算仍最多6s。原会话生产规划约1.656s保留17动作达标候选，预测 ΔE=7.735/0.342/4.381。按实测每动作额外2.4s进行控制器模拟，在90秒内完成且留至少10秒。这是离线条件模型证据，没有新的游戏实机命中声明。

所有目的的路线在入场前预留整条动作数和回读/执行时间，不在更差的半路才发现额度不足。

## 验证入口

默认 quick 约30s，保留3个桌面代表检查和核心纯逻辑；release 保留完整桌面矩阵与实际生产搜索代表；research/full 保留历史矩阵。没有通过测试分层削弱实际搜索。

冻结前 quick：449项，448通过、1原本私有 OCR 档案跳过，0失败/错误，28.953s测试执行（29.724s入口总耗时）。完整发布集合此前477项，476通过、1跳过，178.802s；随后 UI 过渡增量与生命周期专测通过。计数以 JSON 时点为准。

无私有资料的公开源码精确跳过不存在的原捕获文件，不吞已有 JSON/schema/hash 错误，也不生成虚假实机素材。旧无当前引用模块原样归档，个人会话、设置和桌面图不提交。

最终冻结发布集合：482项，481通过、1原私有OCR档案跳过、0失败/错误；执行140.667s、入口146.897s。此前477项结果被这次完整冻结集合替代。

Best-result recovery follow-up: complete multi-action returns including opposite wheel legs now execute the entire audited suffix from measured feedback. Independent screenshot verification is required before claiming restoration. New five recovery contracts plus26 existing frame/protected/fine-scale checks:31 passed in19.869s, with no game inputs. Final independent review found no remaining important issue in this scope.
