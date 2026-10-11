# 韩服登录前适配调查与接入交接

日期：2026-10-12。范围仅多服务器适配；自动更新、主 UI、搜索策略与发布由其他对话负责。

## 结论

无法登录仍能完成构建指纹、静态布局发现、核心算法比对与登录窗口只读预检。已得到当前韩服的明确适配参数。现有取色与输入模型有较强复用依据，不需要因为服务器语言变化重新设计搜索算法。

当前成果是 `diagnostic_only` 适配候选，不是已验收的韩服自动染色工具。韩服未登录时染色类保持未初始化标记，没有活跃色板可采集；实际色板、手势配置及操作响应仍待登录后验证。调查未发送任何游戏输入、未操作登录、未消耗染色道具、未修改游戏文件。

证据目录：`project/outputs/server-adaptation-2026-10-12/`。生产源码和 Git 仓库未在本轮修改或发布。

## 失败原因与构建差异

此前韩服记录在准备阶段报 `Unsupported game/metadata build for static object walk`。这与本地客户端指纹结果吻合：韩服和台服的 GameAssembly、metadata 不同，原台服对象入口在韩服指向无效值；现有工具不能直接复用它们。

两服均为 x64、IL2CPP metadata v31、Unity 2021.3.51p3；UnityPlayer SHA-256 完全相同。因此共享 Unity 原生屏幕、鼠标及几何布局有精确构建依据。

| 文件 | 韩服 SHA-256 | 台服 SHA-256 |
| --- | --- | --- |
| GameAssembly | bd9d827b7cd342c677c1e93a752f61c2e75a913d08ac9879ce285c852986ca08 | 1675c2131534d0ab2fc053af8a2e394d326ba7d22eff0019734be96b1808678f |
| metadata | cdeed3914cc11325e9771047bdbe4bb0acf1733f16f01783418f753c2a6fde8a | 3f6827a41d26ab50ef0051b881cb2c6dcab0c12aab5e95cc7da0071fae63a847 |
| UnityPlayer | e969642866c2195f16a0bd0e52ff8ffe87cad5b213fda9a62ca1564970e2fa26 | 同韩服 |

以下均为模块相对 RVA，不是 ASLR 后的绝对进程地址。

| 参数 | 韩服 | 台服 |
| --- | --- | --- |
| DyeingPaletteInstanceImpl 类入口 | 0x10d1bf18 | 0x106c9010 |
| 染色类未初始化标记 | 0x20036bfb | 0x20035507 |
| MMInputSystem 类入口 | 0x10d7e580 | 0x1074fa20 |
| InputManager 类入口（研究核对） | 0x10bbc140 | 0x10589658 |
| UnityEngine.Input 鼠标 getter 缓存 | 0x11694ce8 | 0x11100078 |
| UnityPlayer 原生鼠标 getter | 0x185310 | 同韩服 |
| UnityPlayer 屏幕对象全局入口 | 0x1b23390 | 同韩服 |

## 如何发现，而不是猜偏移

1. 按 metadata v31 解析完整类名、类型索引、继承、字段类型、方法签名和 token。
2. 从 PE 内代码模块名称及唯一结构引用定位方法指针表，按所在程序集与方法 token 关联原生方法。
3. 从类型数量及相邻注册表结构定位字段偏移与 Il2CppType 表，读取真实字段类型和偏移。
4. 由 byvalTypeIndex 推导 IL2CPP 未初始化类型标记 `0x20000001 | (index << 1)`，要求 DLL 中入口唯一，并要求目标类自身方法实际引用该入口。
5. 从 UnityEngine.Input 注入 getter 的机器指令定位缓存槽；在韩服运行进程重复读取并确认实际函数等于 `UnityPlayer + 0x185310`。
6. 同一方法按完整参数类型匹配，移除函数间 padding，归一化重定位地址后比较指令；另比较可解析的调用目标序列。

该方法独立恢复了已知正确的台服染色、输入和鼠标入口，作为发现方式的参考验证。不能简单按固定 RVA 差值换算其他服务器。

旧 Il2CppDumper 在当前韩服的注册表解析处出现 `Array dimensions exceeded supported range`。本轮未靠强制版本或忽略错误继续使用错误结构，改用上述针对性解析。

## 已完成的验证

- 58 个相关类的字段名称、字段类型和偏移一致；额外 4 个委托、UIChildTransform、BaseDynamicUISlot、MMReadOnlyList 包装类的继承与字段签名一致。泛型参数的 metadata 索引不同不应误判为不同的泛型类型。
- 染色实例 14 方法、动作控制 19 方法、手势识别 10 方法、DyePalette 12 方法、扭曲 2 方法，共 57 个核心方法的归一化指令序列一致，包括两种采样重载、周期 Wrap、拖动、缩放、旋转、惯性和范围校验。
- 归一化比较会屏蔽重定位调用地址，不是逐字节相同证明。核心非构造方法的已解析调用序列也一致；部分构造函数共享了不同数量/命名的泛型或共用实现别名，未逐一证明全部原生辅助函数等价。不能据此替代实机验证。
- 韩服登录窗口实际只读核对到 `MMInputSystem → InputManager`，静态字段和实例字段偏移符合 metadata，`inputEventAssistant = 0`，使用 legacy mouse 分支。
- 韩服鼠标 getter 缓存实际指向共享 Unity 函数；viewport origin 为 `[0,0]`、scale 为 `[1,1]`。
- 原生 Screen HWND 所属 PID 与韩服一致；原生尺寸与 Win32 client rect 均为 1280×720。所有绑定读数前后相同。
- 韩服染色类入口值为 `0x20036bfb`，正好等于当前 metadata 推导的未初始化标记。无需无意义地遍历整个堆寻找尚不存在的色板。
- 定向验证检查覆盖指纹变更拒绝、候选禁止输入、尺寸/HWND、类型标记、字段、核心比对及台服参考入口恢复。结果保存在 `verification.json`。

本地只读记录 `kr-login-runtime-verified.json` 保留运行时 PID/HWND/必要指针以便复核；不得作为随软件分发的用户遥测。适配候选没有账号资料或绝对运行时地址。

## 生产接入还需改动的具体位置

接入方读取 `kr-adapter-candidate.json`，不要把候选直接添加为输入可用。

| 模块 | 必须处理 |
| --- | --- |
| native_live/build_adapters.py | 完整指纹选择；补充 palette marker、input class RVA、getter cache RVA、Unity layout id、能力等级及字段结构证据 |
| native_live/native_provider_backend.py | `_bind` 和未初始化处理的重复读取均使用 adapter 参数；目前重复读仍硬编码台服 0x106c9010，marker 也固定台服 |
| native_live/read_dye_input_backend.py | input class 和 mouse cache 改为 adapter 参数；Unity getter/viewport 由 Unity 指纹布局选择 |
| native_live/read_toucharea_rect.py | 从已验证适配器选择管理对象布局和共享 Unity 布局；目前仅接收台服 GameAssembly/metadata 哈希 |
| native_live/read_toucharea_geometry.py | 使用上游布局选择结果，避免再次引入服务器名单限制 |
| native_live/capture_dye_state.py、read_dye_motion.py | 对照候选字段结构；保持当前运行时类名和字段验证。需活跃色板才能验证实例链和实际 settings |
| native_live/scan_live_dye.py | 主流程使用选中 adapter 的 class。文件独立 CLI 仍硬编码台服入口，也应跟随统一绑定 |
| 窗口定位/视觉识别 | 韩文标题已识别；标题只负责定位，不替代指纹。韩服 UI 取色点、数字/HEX 的实际布局仍需截图及对象几何验证 |

仅在注册表中增加韩服 palette RVA 会产生“准备能过、输入/几何仍失败”的半适配状态，上表各入口必须统一。

## 后续服务器的自适应方案

采用“构建指纹注册表 + 离线发现 + 能力验证”，而不是维护服务器语言到固定地址的映射。

- 已知 GameAssembly/metadata 使用对应管理对象适配器；UnityPlayer 独立选择原生几何和鼠标布局。同一指纹换标题/服务器无需再分叉。
- 未知构建先生成只读诊断。若为可解析 v31/x64，按上述结构发现生成候选；schema 或原生引擎变化则单独分析，不能直接借用旧地址。
- 静态发现结果缓存为指纹绑定的小 JSON；运行期只做指纹匹配与必要的对象字段核对。不要每次开染色时反编译 300 MB DLL。
- 能力按证据升级：`diagnostic_only → palette_readable → model_verified → input_verified`。发现成功不能自动提升输入能力；验证完成后由维护者随工具版本分发适配模块。
- 搜索策略和 3 秒结束余量继续由现有模型负责。兼容性核对在准备阶段完成，不给搜索阶段新增反复扫描或新的消极时间限制。
- 文件、布局和私有证据各自保存。Git/发行包只放研究工具、脱敏最小 fixture、已审核布局与报告；不放游戏 DLL、完整 metadata、反汇编全集或用户进程记录。

## 当前条件下尚不能完成的验收

需可登录客户端或其他韩服测试者提供一次真实染色记录：色板 2/3 区域、实例链、254×254 RGB 纹理、NormalizedPositionY、ColorPreserveRatio、实时 HEX 与模型预测核对。随后才验证拖动、正反滚轮、旋转、缩小到最大范围、重试和结果回读。

无需继续消耗时间反复扫未登录进程。下一步可先在隔离代码目录抽离上表适配参数并做定向回归；真正活跃色板与输入验收仍需登录条件。韩服当前不得在发行说明中写“完整支持”。

## 复现命令

在 `D:\Working\ColorstudioProject` 用项目 `.venv` 运行；研究依赖为 pefile、capstone。未改动生产依赖清单。

```powershell
& project/.venv/Scripts/python.exe project/outputs/server-adaptation-2026-10-12/discover_layout.py C:/Game/MabinogiMobile project/outputs/server-adaptation-2026-10-12/kr-layout
& project/.venv/Scripts/python.exe project/outputs/server-adaptation-2026-10-12/discover_layout.py C:/Nexon/Library/MabinogiMobile_TW/appdata project/outputs/server-adaptation-2026-10-12/tw-layout
& project/.venv/Scripts/python.exe project/outputs/server-adaptation-2026-10-12/compare_builds.py
& project/.venv/Scripts/python.exe project/outputs/server-adaptation-2026-10-12/compare_wrappers.py
& project/.venv/Scripts/python.exe project/outputs/server-adaptation-2026-10-12/probe_login.py
& project/.venv/Scripts/python.exe project/outputs/server-adaptation-2026-10-12/build_candidate.py
& project/.venv/Scripts/python.exe project/outputs/server-adaptation-2026-10-12/verify_candidate.py
```

`probe_login.py` 只绑定唯一韩文客户端，并核对加载文件来自韩服目录；即使台服同时运行也不会读到台服。该脚本只读，没有操作游戏输入的实现。
