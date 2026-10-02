# T02：浏览器交互、状态与框架机制兼容

版本：2026-10-02-tech-2。状态：B01～B07、B08 首版检测/覆盖说明及 B09 最小真实框架工程路径已实现；见 [实施与验收记录](../../t02-implementation.md)。额外 frame/shadow 支持、真实模型效果和真实小应用仍分别验收。以下保留实施契约与边界。消费 [MVP 共享契约](../README.md)，对应 J01/J04/J05、L02/L03/L04/L05、V01/V03/V04。
本节点负责让已有运行 URL 的真实控件可发现、可操作、可观察、可回放；不建设 React/Vue 插件，不读取框架内部状态作为用户预期。
技术兼容按 DOM 和浏览器机制验收；出现框架名称不代表已支持该框架的所有组件库、路由、鉴权和构建模式。

## 1. 实施前能力与具体缺口（历史基线）

| 模块 / 函数 | 已有实现 | 本节点需要增强的地方 |
|---|---|---|
| `driver/action.py::Target/Action` | selector/text/role/坐标；click/hover/type/press/select | 目标作用域、可访问名称、定位结果与执行结果尚未形成可核对的统一输出 |
| `PlaywrightDriver._locator_chain/execute` | selector → 非精确 text → 无名称 role → 坐标兜底；成功后记入动作序列 | 重复文字与同 role 目标不唯一；定位失败与执行后等待失败共用异常降级，可能重做已执行动作 |
| `interactive_elements` | 原生控件、部分 role、contenteditable、弹出提示；最多 200 项，生成 id 或 DOM 路径 | 未枚举 role=combobox/listbox/option 等完整交互结构；DOM 路径易受重排影响，截断无独立覆盖说明 |
| `_perform/extract_candidates` | fill/select_option/press；空字段填值；必填勾选优先；选中 native select 后停止准备 | 未验证受控值重渲染、blur/change 提交语义；自定义 select 的展开和选项选择没有专门候选 |
| `launch/navigate/wait_for_settle` | goto；DOMContentLoaded 最多 3 秒，异常后继续；固定等 300ms | 当前没有 networkidle 等待；也没有 hydration、异步反馈就绪条件和明确的等待超时结果 |
| `form_state/signature` | 可见字段值、checked/disabled/readonly 进入摘要；URL 保留 query/hash；值不写入 State 快照 | modal/expanded/selected/busy 等可见交互状态未统一进入签名；字段 index 与 DOM 重排可能制造新状态 |
| `StateTracker/ActionPlanner` | 状态内成功记账、失败有限重试；返回边和自环；顺序轨迹 | tracker 的 execute 异常不会形成 visit；成功回放序列与全部尝试需通过 step ID 对齐 |
| `storage_state/replay_data` | cookies/localStorage、实际入口 URL、成功动作序列、视口 | 未保存 sessionStorage；并无完整登录系统、自动续期或第三方认证承诺 |
| 页面与作用域 | 当前 driver 从主 page 枚举控件、采文本和状态 | 没有项目级 frame 路径；shadow 内 locator 可用不等于枚举、状态、回放全链路可用 |

实施前回归主要是静态 HTML：`test_browser_controller.py`、`test_state_tracker.py`、`test_exploration_regressions.py` 和 `test_replay_engine.py`。
它们覆盖原生填表、勾选、选择、页面跳转、状态返回和 localStorage 回放；当时尚不能代替真实 React/Vue/Next 机制验收；本轮新增的锁版本机制路径与实际限制见实施记录。
URL 边界核对：CLI/UI 校验后保留输入，driver 读取真实 page.url；`signature()` 保留 query/fragment，`route_path()` 只去 scheme/host、保留 query/fragment，`normalize()` 仅处理可见文字。当前这些层不会合并不同 hash 页面。
仍有缺口：源码路由提示尚未标识 hash/history 模式；普通静态服务尚无 SPA 深链 fallback，这是 F07 的职责。`RuntimeObserver._parse_http_status()` 只以 path 作聚合键，会合并不同 origin/query 的 HTTP 状态；该技术信号聚合不等于页面状态签名，原始 HTTP URL 应由 T04 保留。

## 2. 模块输入、输出与兼容约束

- 输入继续是运行 URL、可选 cookies/localStorage、候选 `Action`、扫描剩余时间和动作预算。
- 候选输出增加可见标签、可访问名称、控件状态及作用域信息；这些是浏览器可观察信息，不含源码、框架 store 或评估答案。
- 执行输出说明定位策略、匹配数量、是否发出动作、动作结果、等待结果、最终 URL 和实际经过时间。
- `Target` 的新字段只能是可选增量；旧 selector/text/role/坐标记录继续读取，旧回放没有作用域时只按旧规则执行。
- 成功执行与业务反馈分开：点击发出成功但没有反馈，不应改成定位失败；判断材料不足交给 J05 标记未知。
- 输出交给 T04 的原始步骤持久化接口；本节点不新增日志数据库，不另定原子写入或恢复协议。
- `step_id` 由运行层分配；状态图、全部尝试、成功动作前缀和 replay 消费同一 ID，不能以数组下标充当永久身份。

## 3. B01：稳定目标与有限定位降级

修改：`driver/action.py`、`PlaywrightDriver.interactive_elements/_locator_chain/execute`、`planner/models.py`。
依赖：共享 Target 增量与 T04 步骤输出；可以独立于模型修改实施。

- 枚举时记录 label/aria-label/可访问名称、role、稳定属性及可见作用域；保留通用 CSS 路径作为补充。
- 定位先校验现有 selector 与可见目标，失败再用唯一 label 或 role+name、精确文本；坐标仅作有记录的最后降级。
- 多个匹配不任取 `.first`；使用已有表单/dialog 作用域区分，否则返回 `ambiguous_target`，让 planner 尝试其他候选。
- 不要求目标产品新增 data-testid；已有 testid 可利用，缺少 testid 不应失去基本能力。
- 记录真正使用的 locator 和坐标条件，供回放优先使用；坐标依赖原视口，布局已变时不能声称稳定复现。
- 整条定位链共享剩余时间；执行已经发出后等待失败，不再循环降级重发同一个 click。

验收：两个“保存”按钮分别命中对应表单；DOM 插入兄弟节点后仍能按唯一语义定位；同名歧义明确失败；坐标降级可追溯。
异常对照：selector 失效、元素被替换、遮罩挡住、动作后截图/等待失败，各产生正确阶段结果且不重复提交。

## 4. B02：受控表单与实际提交语义

修改：`PlaywrightDriver._perform/interactive_elements/form_state`、`ActionPlanner.extract_candidates/plan`。
依赖：B01；对应 J01、L03 和 V01。继续使用浏览器 DOM 交互，不赋值框架内部对象。

- 验证 fill 后 React 受控 input 和 Vue 绑定值经重渲染仍保留；读取真实 DOM 值，不把调用无异常当成最终值已接受。
- 将需要离开字段的 blur/change 场景拆成可观察交互步骤；不要向所有控件无条件合成事件或额外提交。
- 保留原生 select 的 value、必填 checkbox/radio、已有值字段和禁用/只读过滤；不得因状态变化无限轮换选项。
- 样本值优先满足可见的 type/min/max/maxlength 与格式提示；无法构造合法值则记录校验观察，不猜测内部业务数据。
- 区分填值、提交和校验反馈；输入失败不能把后续未提交算成产品“保存没反馈”。

验收：React/Vue 填值 → blur → DOM 反馈 → 提交结果可核对；必填勾选位于提交按钮之后仍能在有限步数内提交。
异常对照：受控值被产品重置、可理解的格式错误、合法禁用按钮和真正无反馈分开记录；正常校验不被固定当作故障。

## 5. B03：自定义控件、弹层与动态 DOM

修改：`interactive_elements`、`planner/planner.py`、`planner/models.py`，复用 B01 的作用域。
依赖：B01/B02；对应 J04/J05、L03、V01。

- 分开原生 select 与 role=combobox/listbox/option：先展开，再枚举当前可见选项，再点击唯一选项；不用 select_option 操作 div。
- 支持可见 dialog/modal 及 portal 挂载；弹层出现时从可见层生成候选，关闭后恢复背景候选，避免继续点击被遮挡控件。
- 对每次动作后的 DOM 重新枚举，候选不能长期持有已 detach 的 locator；虚拟列表仅覆盖实际呈现项目，不声称遍历全部数据。
- 展开/关闭/选中状态进入 B05；200 项枚举上限保留且显示截断诊断，不能把未枚举区域记为检查完成。
- 无可识别 role/标签的复杂画布、拖拽编辑器和封闭组件明确列为未验证，避免把坐标点选包装成完整兼容。

验收：native select、可访问自定义 select、portal 弹层和列表重渲染各完成一个正常路径；关闭弹层后可继续探索。
异常对照：空弹层、选项点击不改变值、元素消失、枚举截断和无法识别控件分别可说明。

## 6. B04：SPA、SSR/hydration 与异步观察窗口

修改：`launch/navigate/execute/wait_for_settle`、`runtime.py`；运行层消费新的等待结果。
依赖：B01；B02/B03 提供机制样例。对应 L02/L03、J05、V01/V03。

- 区分初始导航、hash/history 客户端路由、整页跳转；读取动作后的真实 URL，导航不以是否触发新 document 为唯一依据；深链刷新与静态服务 fallback 消费 F07，不能靠删 hash/query 或改到根 URL 掩盖环境问题。
- 初始文档可读和控件可交互分别处理；SSR HTML 出现不代表 hydration 后处理器已生效，不读取 React/Vue 私有标志。
- 用有上限的可见状态/控件与 URL 稳定观察替代单一固定 300ms；加载中状态、反馈变化和截止时仍 pending 一并输出。
- 不强制全站 networkidle：轮询、流式请求和埋点不应永远阻塞；具体动作观察窗口在剩余 run 时间内有明确上限。
- 保留即时和等待后的观察引用，防止先拍到 loading 就断言“缺反馈”；等待超时可支持“仍加载中”，不能伪造最终失败。
- 导航、各定位尝试和 settle 都计入统一时间预算；run 停止后不再发起新动作，迟到反馈不改写原执行结果。

验收：hash/history 路由均产生正确状态和回放；SSR 页面晚绑定事件后可执行；延迟成功反馈能进入判定材料。
异常对照：无限 loading、请求失败后有解释、轮询页面和超过观察窗口分别可终止、可说明，不能共同显示检查通过。

## 7. B05：用户可见状态签名与候选收敛

修改：`form_state`、`state/signature.py`、`state/tracker.py`、`planner/planner.py`。
依赖：B02/B03/B04；对应 J04 和 L03。

- 在已有 URL/文字/字段摘要上增加可见 dialog、expanded、selected、disabled、busy 等稳定状态；不哈希整个 DOM 或框架 store。
- 字段身份优先唯一标签/稳定属性和作用域，index 只作最后降级；重排相同内容不应无限创造新状态。
- 表单值用于内部状态摘要，沿用不写入 State 文本快照的边界；J04 的可见历史独立裁剪，不能把密码/session 值当用户经验。
- 继续保留返回、自环、计数变化和不同 hash/query；相同可见文字的两个 hash/query 页面也不得合并。时钟噪音对照要验证，不因去噪抹掉有意义的时间反馈。
- 新增状态特征可缺省；旧保存图可以读取，不直接与新版摘要混用证明“已探索”。

验收：只切换 checkbox/展开菜单/改变 selected 就有新状态；恢复原状态形成返回边；重排和时钟不会造成无界重复探索。
异常对照：永远变化的页面仍由动作/时间预算终止，报告明确剩余覆盖，不把收敛失败叫作产品 Bug。

## 8. B06：尝试轨迹与成功回放前缀

修改：`StateTracker.capture/trajectory`、`ActionPlanner.record_result/explore`、driver 执行输出；回放消费者按共享契约接线。
依赖：B01/B04/B05 与 T04 原始步骤接口；对应 L03/L04、V01。

- 全部尝试记录 step ID、前状态、action、执行/等待阶段结果和可获得的后状态；失败尝试不冒充成功边或完成候选。
- planner 继续成功后记账、失败有限重试；同状态失败耗尽不堵住其他候选，进入新状态后是否重试遵循统一预算。
- replay 的 action_sequence 保持成功前缀，同时引用原 step ID 与实际定位策略；失败步骤作为诊断保留，不直接追加成可执行前缀。
- 读取旧动作序列时允许没有 step ID；回放失败指出中断步骤，后续未执行不能报告成“没有复现”。

验收：失败 → 有限重试 → 其他成功动作的完整尝试可读；成功前缀在新上下文重放；返回和自环的步骤不丢失。
异常对照：动作已发出但等待超时不会重复执行；途中 replay 失败保留准确中断位置，截图匹配不自动证明认知结论。

## 9. B07：登录态边界与访问结果

修改：`launch/storage_state/replay_data` 及输入/回放消费者；对应 L02/L04、V01/V04。
依赖：B04/B06；复用 cookies/origins 格式与本机私有回放包，不新建凭据服务。

- 验证 cookies 和 localStorage 在初次扫描及新上下文回放生效；实际进入登录页时记录访问结果，不假定已扫描业务页。
- 过期会话、重定向、跨 origin 存储和无效文件分别说明；原始会话内容不进入报告、prompt 或公开样例。
- sessionStorage 当前未恢复，MVP 明确列限制；需要它的应用不能被宣称登录态兼容，是否补支持由实际小应用需求决定。
- IndexedDB、自动登录、多步 SSO、验证码和自动续期同样不由 storage_state 名称推导为已支持。

验收：cookies/localStorage 保护页面完成前置路径；会话过期回到登录页可解释；分享 HTML 无凭据。

## 10. B08：frame/shadow 支持层级

修改：Target 可选作用域、driver 枚举/定位/状态接口；依赖 B01/B05/B06。对应 L03/L04、V01。

- 首版必做检测与覆盖说明：发现 frame 或 shadow 相关内容时，说明已访问、未访问或无法枚举的区域。
- 如小应用验收确有需要，随后补可识别同源 iframe 和 open shadow root 的完整枚举→定位→状态→回放，作用域是可选增量。
- Playwright 提供 locator/frame 能力并不证明 AlienQA 已打通；仅单次手工定位成功不能写为全链路支持。
- 跨源 iframe、嵌套复杂 frame、closed shadow、第三方支付/认证先列未验证或不支持；不绕过封闭边界，不自动扩成企业兼容项目。

验收：主页面继续可扫描；不可访问区域有明确限制。新增支持只有通过发现与独立回放成对测试后才进入支持矩阵。

## 11. B09：最小真实框架样例与集成 gate

修改：扩展 `tests/fixtures/`、既有浏览器/planner/state/replay 测试；新增样例 manifest，配合 V01/V03。
依赖：B01～B07；B08 首版至少覆盖限制显示。框架 fixture 使用明确版本和锁文件，不要求外部大型仓库或 CDN。

| 样例 | 必须验证的机制 | 正常 / 异常配对 |
|---|---|---|
| 最小 React 页面 | 受控 input、重渲染、portal dialog、history 路由 | 值保留/重置；可关闭弹层/空弹层；正确路由/无反馈 |
| 最小 Vue 页面 | v-model、blur/change、条件控件、自定义 select | 正常校验/无解释；选项更新/选中不生效 |
| 最小 Next 页面 | SSR 到客户端可交互、客户端导航、延迟反馈 | 正常 hydration/事件未生效；延迟成功/持续 pending |

先复用 HTML 配对完成模块回归，再运行这些小页面；浏览器链路使用模型替身，真实模型效果单独按 V03 记录。
每个样例固定入口、版本、重置方法、动作/时间预算、成功路径和正常对照；标签答案仅在评估侧，不进入扫描输入。
最小集成 gate：在有限预算内填表→提交→反馈→导航/弹层→保存证据→新上下文回放，各步骤与截图对应同一次动作。
关闭顺序：B01/B02/B04 先保证基础路径，B03/B05/B06/B07 合并验收，再运行 B09；B08 的额外支持不阻塞主 URL 闭环。
支持矩阵写明验证过的版本和机制；三个样例通过仅证明这些路径，不等于 React/Vue/Next 或组件库全兼容。
