# 技术子计划 06：开发者决定、分析报告与离线产物

> 状态：H01～H08 已完成工程实现与确定性集成验收。详见 [T06 实施记录](../../t06-implementation.md)；真实模型效果、仓库外干净安装与发布验收仍由 N06/Q04/Q05 承接。
> 父节点：[MVP-02 的 R03～R06](../02-findings-review-report.md)；共享契约以 [MVP 索引](../README.md)为准。
> 为独立开发者保留一般用户认知落差、技术候选和自己的解释；“按设计”不删除原声，未审不阻断 analysis。

## 当前落点与缺口

| 模块 / 已有入口 | 当前行为 | 本计划改进 |
|---|---|---|
| `review/models.py`：`Decision`、`ReviewState`、`Report` | 五态 enum 与备注已存在；Report 只有旧计数 | 复用四种决定与 pending，保留旧计数含义 |
| `ui/app.py`：`run_review`、`run_decide` | 仅提供 confirmed/rejected，提交时备注置空 | 返回完整决定/备注/证据行；合法四态与备注保存 |
| `review/webui.py`：`index`、`decide`、`report` | 独立审核支持 note，但只有两种决定，未用共享锁 | 与主 UI 使用同一语义和快照规则 |
| `review/report.py`：`ReportBuilder.build`、`_validate` | confirmed-only；pending/by-design/skipped 拦截 | 新增显式 analysis，旧默认与 gate 保持 |
| `ui/runs.py`：加载/保存、`save_review` | 原子写 JSON；重审仅失效 `report.html`，缺文件可默认为空 | 两种缓存失效、读取错误分层、终态快照 |
| 两套审核模板、`ui/templates/run.html`、CLI | 二态开关和单报告入口 | 原生控件接线、双入口与明确输出路径 |
| 报告 `_image`、`_sanitize_summary` | 已内嵌图片、提示缺图、净化模型 HTML | 复用这些能力，补分析内容与离线整体验收 |

源码入口：[报告构建](../../../../alienqa/review/report.py)、[审核模型](../../../../alienqa/review/models.py)、[主 UI](../../../../alienqa/ui/app.py)、[历史目录](../../../../alienqa/ui/runs.py)、[独立审核](../../../../alienqa/review/webui.py)。
边界：不做 Issue 合并拆分、团队审批、PDF、云端链接；不增加内容哈希、取证数据库或新的富报告持久化体系。

## H01：统一决定与备注的写入契约

- 父任务：R03；阶段 M1，P0。文件：`review/models.py`、`review/service.py`、`ui/app.py::run_decide`、`review/webui.py::decide`。
- 输入：`{evidence_id, decision, note}`；决定只接受 confirmed/rejected/by-design/skipped，pending 是未处理默认值；note 为字符串，允许空。
- 输出：JSON `{ok: true, evidence_id, decision, note}`；两入口遵守相同校验，继续使用 `ReviewState.decide/decision/note`，不建第二个 enum。
- 序列：读取 JSON → 校验对象/字段 → 锁内确认 Evidence ID 存在 → 更新 state → 持久化并失效双缓存 → 返回保存结果。
- 错误：非法 JSON/决定/备注类型 400，未知 run 或 Evidence 404；写盘失败返回明确保存错误，UI 不宣称成功。内存 state 不先于成功持久化成为新事实。
- 验收：待审→按设计并保存中文备注，刷新后恢复；按设计→确认、仅修改备注均使两报告失效；未知 ID 不写 review.json。

## H02：审核页面使用四态控件并展示原声

- 父任务：R03/R06；阶段 M1，P0。文件：`ui/app.py::run_review`、`review/webui.py::index`、`ui/templates/review.html`、`review/templates/inbox.html`。
- 输入：Evidence、ReviewState 和现有调查/回放结果；行数据增加 note、finding_kind、basis、动作/截图及说明，不靠 classification 猜来源。
- 输出：明确“待审 / 确认问题 / 不采信 / 按设计 / 暂跳过”；每行原生 select、textarea、保存按钮与保存状态，复用现有模板与原生 fetch。
- 序列：服务端回填当前决定/备注 → 用户编辑 → fetch 同时提交三字段 → 成功才更新保存状态；失败保留编辑内容，恢复可操作控件。
- 原声始终可查：预期、依据、模型观察摘要、推理、截图、技术信号分栏；技术候选 basis=null，旧字段标“未记录”，不补造。
- 错误：fetch 网络失败、非 2xx、非法响应都显示可理解原因；不能用关闭的 checkbox 把 pending/by-design/skipped 显示成 rejected。
- 验收：真实浏览器检查控件、请求字段、备注刷新、失败反馈、重放按钮共存；不用只验证 Flask 返回 200 代替接线验收。

## H03：ReportBuilder 增加显式双模式

- 父任务：R04；阶段 M1，P0。文件：`review/report.py::ReportBuilder.build/_validate`、`review/models.py::Report`、相关调用点。
- 已实现 API：`build(evidences, state, investigations=None, diagnostics=None, *, mode="confirmed", scan_context=None)`；保留旧默认及 gate。
- 输入 mode 仅 analysis/confirmed；scan_context 消费既有范围、steps、stop_reason、运行预算与终态元数据，不另建原始日志库。
- 输出仍是 Report；accepted_count 只数 confirmed、total_count 数全部 Evidence。analysis 展示数单独标明，不重定义旧字段或历史 RunRecord.accepted_count。
- 序列：校验 mode → confirmed 执行旧 gate / analysis 取全部 → 确定性渲染 → 可选模型补充 → 返回；零条记录也是合法输入。
- analysis 标题“QA 与用户认知分析”，全部五态与备注明示；confirmed 保持 confirmed-only 及 pending/by-design/skipped gate。
- 错误：非法 mode 抛输入 ValueError，不能静默回退；补充模型异常不阻断确定性正文；confirmed 被 gate 拦截时入口指向 analysis。
- 验收：五种状态混合数据 analysis 无漏项，accepted_count/total_count 正确；省略 mode 的旧调用与旧 gate 回归行为不变。

## H04：报告内容区分记录、模型解释与开发者决定

- 父任务：R04/R06；阶段 M1，P0。文件：`review/report.py::_evidence_dict/_render_recorded_evidence/_technical/_repro`。
- 输入：上游新增 finding_kind/basis 与既有动作、状态、artifacts、replay、调查、ReviewState；只增量消费字段，不回写或重判 Evidence。
- 输出每条记录依次给出来源与完整性、原始动作/可见文字/技术信号/截图、事前预期及 basis、模型观察摘要/推理、调查假设、决定和备注。
- 将现有 observation_summary 明确标为模型摘要；技术信号与截图是采集记录。原始 DOM 若显示，仅作为转义文本；根因始终标假设及调查状态。
- 序列：按保存内容读记录 → 缺字段/缺文件如实标注 → 附加模型解释 → 附加决定；按设计与 rejected/skipped 均保留原声。
- 错误：技术 artifact 已声明但读取失败，给出局部“不可读取”提示；不能静默丢失信号后宣称证据完整，也不让单张缺图阻断整份报告。
- 验收：同一“保存无反馈”证据的截图、依据、摘要、按设计备注同时存在；调查失败留错误与原始证据，技术候选不虚构预期。

## H05：终态读取与一致快照

- 父任务：R05；阶段 M1 建最小终态检查，M2 完成异常/交错验收，P0。文件：`ui/app.py::run_report`、`ui/runs.py` 加载接口、`review/webui.py`。
- 输入允许终态 done/partial/error/timeout/cancelled；running/unknown 拒绝导出。锁内重新读取 RunRecord，不能消费锁外的旧状态。
- 已实现 `RunManager.load_report_snapshot(run_id)`，返回 Evidence、ReviewState、调查、诊断、范围及终态 context；新 run 先验证 P06 最后已提交的 checkpoint_seq、成员和引用，以该快照为扫描权威，不靠独立汇总文件猜完整性。
- 序列：锁内确认终态 → 一次加载快照 → build → 原子写指定模式文件；决定写入与报告读取共用同一本地锁。
- 扫描终态保证 worker 不再写前缀；watchdog 收回进程后才终止运行。该供应约束由 [运行管线计划](04-runtime-pipeline-persistence.md)交付。
- 新 run 的 `evidences.json=[]` 只有与已提交快照成员一致才是有效空结果；已提交且仅含失败诊断的终态可出诊断分析。两者写“未记录发现”，不写“测试全部通过”。旧 run 无 checkpoint 按已明确的兼容路径读取，不能伪造提交序号。
- 文件缺失区别于损坏：旧记录缺新可选文件标未记录；明确存在的坏 JSON/schema 返回可定位读取错误，不当成空数组；缺必需数据且无诊断不能出伪分析。
- 独立审核由已完成 collect 的 CLI 注入 context，添加局部锁保护决定、保存与生成；重载磁盘 review 遵守相同校验，不建多人版本机制。
- 验收：报告与重审同时请求，导出对应一份有效决定快照，重审后缓存失效；取消只读已落盘前缀；空记录、诊断-only、坏 JSON 分别覆盖。

## H06：两种文件缓存与所有变更失效

- 父任务：R03/R04/R05；阶段 M1，P0。文件：`ui/runs.py::save_results/save_review/save_diagnostics/save_scope/save_replay_result`、两报告路由。
- 路径固定 analysis→`analysis.html`、confirmed→既有 `report.html`；已实现 `invalidate_reports(run_id)`，内部只删除这两个固定路径。
- 输入是报告实际消费的数据更新；Evidence、决定/备注、调查、诊断/范围更新均失效两缓存。若 H04 展示回放结果，回放结果保存也必须失效。
- 序列：锁内成功保存新数据 → 失效两缓存 → 更新 run 计数。终态 run 的 generation、decide、调查/范围/诊断/回放结果保存共用同一本地锁，防止任何新数据写完后旧报告迟到回填。
- 回放 worker 只返回结果给 parent，由 parent 在锁内保存/失效；运行中的扫描不允许正式报告，因此无需跨进程锁或新的版本服务。独立审核同样保护它实际消费的数据更新。
- 不以新模式扩大 accepted_count；输出 HTML 用当前原子写方法，写失败不留下半页可读缓存。
- 错误：缓存不可删除/不可写明确返回，不能展示旧文件为最新；运行中已有旧文件也不得绕过 H05 的终态检查。
- 验收：分别生成两文件，改备注/决定后两文件均不存在；新 analysis 保留全部项，新 confirmed 按原 gate；分别交错 generation 与 decide/回放结果/调查更新，无旧报告复活。

## H07：CLI、主 UI 与独立审核报告入口接线

- 父任务：R04/R06；阶段 M1 建 analysis 主入口，M2 补全部兼容路径，P0。文件：`ui/app.py::run_detail/run_report`、`ui/templates/run.html/review.html`、`review/webui.py/templates/inbox.html`、`__main__.py`。
- 报告路由读取显式 `?mode=analysis|confirmed`；旧无参数路径保留 confirmed 兼容，新页面主要链接带 mode=analysis，并独立标出确认问题报告。
- 主 UI 显示两个文件存在状态与生成/查看/下载；下载仍消费同一模式快照产物，不能通过另一个入口绕过状态或 gate。
- CLI 已增 `--report-mode analysis|confirmed`，默认 analysis；只有显式 confirmed 需要旧终稿条件，auto-confirm 仍清楚标未经人工审核。
- CLI 未审默认结果可生成 analysis，标准运行目录写 analysis.html；显式 `--output` 优先，未指定时按模式选文件名，不覆盖另一个模式的旧产物。
- 独立审核同步 mode 与输出映射，CLI 向 create_app 传终态 scan_context；终止与历史页面合同接 [本地运行/UI 计划](07-local-run-ui-lifecycle.md)。
- 错误：非法 mode HTTP 400 / CLI 参数错误；confirmed gate 409 提供 analysis 入口；文件路径不可写告知实际路径与原因。
- 验收：页面链接/fetch/query/CLI 参数真正到达 build.mode；未审和按设计能导出 analysis，旧路径仍维持 confirmed 回归；两个产物不互相覆盖。

## H08：离线可读与已有净化能力复用

- 父任务：R06；阶段 M2 验收、M3 发布，P1。文件：`review/report.py::_image/_sanitize_summary/_pre`、下载入口、README 使用说明。
- 复用现有 data URI 截图与 HTMLParser 白名单，不引入新净化依赖；动态文字/备注/异常/DOM 使用 escape，模型补充统一经过现有 sanitizer。
- 输入只允许已记录可嵌入的图片；缺路径、读失败、非支持格式沿用提示；相对 artifact 路径按 run 目录解析，与绝对旧路径保持兼容。
- HTML 展示复现条件但不导出 storage_state/cookies；模型编排 payload 也排除凭据，不能将完整 replay 包直接序列化进正文。
- 输出独立 HTML 不依赖本机绝对图路径、在线 JS/CSS、活动 DOM；复制后保留全部决定、备注与图像，缺回放/调查说明缺失。
- 验收：复制到另一目录并离线打开；script、onerror、javascript href、恶意备注不能执行，缺图有提示；原始本地 replay 仍可由既有入口使用。

## 集成顺序与完成证据

H01/H02 可先行；H03/H04 消费父 R01/R02 的 Evidence 增量；H05/H06 的最小安全边界与 H03 一并进入 M1，不等报告内容完成后补锁。
H07 接所有入口；H08 在 M2 完成离线与注入回归，在 M3 的安装 smoke 中重新消费实际产物。
供应方：[管线/持久化](04-runtime-pipeline-persistence.md)提供终态与前缀；[回放/调查](05-replay-dedup-investigation.md)提供可选解释与复现结果；字段契约仍属于父计划。
实现测试落点：`tests/test_review.py`、`tests/test_ui_app.py`、`tests/test_ui_browser_flow.py`、`tests/test_cli_regressions.py`、`tests/test_pipeline_browser_flow.py`，新增 `tests/test_t06_reports.py` 与 `tests/test_t06_browser_flow.py`；测试矩阵与实际结果见实施记录。
整体验收已在主 UI 与独立审核两个入口执行：真实 Chromium 扫描产生两类候选及调查失败诊断，页面保存按设计备注并保持另一条 pending，下载 analysis，修改为 confirmed 后重新下载，复制到另一目录离线阅读。模型响应为替身。
上述验收证明交付链路；一般用户是否认同预期、真实模型费用与误读仍由 MVP-04 的效果验证评估，不从报告单测推导。

实现时在写入前先检查/删除双缓存，成功保存后再次失效，避免删除失败后旧 HTML 继续被当作最新结果；保存/生成/回放完成结果使用同一 RunManager 本地锁。回放 worker 只写 completion，由 parent 保存正式结果。既有终态扫描数据的增量更新同步写入原 scan.json 权威，旧目录继续采用显式兼容路径。
