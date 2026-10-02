# T05 回放条件、发现聚类与按问题调查实施记录

日期：2026-10-02。对应 [T05 Planbook](mvp-planbooks/technical/05-replay-dedup-investigation.md)。E01～E07 的功能 MVP 已接通；回放结果、Issue 关联和调查假设作为可选增量，不改变原预期、依据和开发者决定。

## 1. 工程交付

| 任务 | 实现及边界 |
|---|---|
| E01 回放包 | `package_version=2`；保留请求入口、浏览器/视口、cookies/localStorage、成功前置序列、独立目标动作、原 step/action ID 和全部尝试。入口技术候选允许零动作。每个技术候选只保存其 source record 对应的结构化事实；不以终页补造起点。旧包按最后成功动作读取并标明来源窗口未知；缺包、坏 JSON、缺前提返回可持久化失败 |
| E02 环境 | 默认 driver 应用浏览器类型/视口并核对实际值；浏览器默认回退不冒充原环境。版本变化单列限制；注入 driver 由调用者负责设置。按原目录/端口恢复自有静态服务；`spa_fallback` 仅 document 导航、无扩展名非 API 路径回退，资源/API 保持 404。hash/query/深链不改写；外部 URL 服务不关闭；自建服务及浏览器 finally 清理 |
| E03 匹配 | 目标动作前冻结事件游标，前置事件不参与目标比较。技术候选核对具体 `page_error` 消息或 HTTP method/完整清洗 URL/5xx status；所有原具体事实匹配才给 reproduced。图片相近不能替代原技术事实；认知画面再现只是人审辅助。无可比较事实/截图、截断和观察失败保持 inconclusive；未出现事实与执行失败分开 |
| E04 分组 | finding_kind、页面、触发动作及可核对事实构成技术 hard key；现代认知记录保留原预期和 basis 差异。现代技术不做文本/截图软合并；双来源成员全部保留。Issue 说明是组织候选，根因未证明；已有 Issue 编号尽量复用，新的编号不占用已有编号；决定始终绑定 Evidence ID |
| E05 增量 | 聚类从 committed Evidence 的独立副本计算，成功后提交关联；聚类中途异常不污染原成员。调查失败保存 failed/status/error，原分析仍可导出。RunManager 的终态调查增量和回放结果写入与双报告缓存共用本地 RLock；不把 partial 改 done，不删除原诊断。报告按调查保存的成员 ID 约束归属 |
| E06 调查 | 只取 Issue 成员的保存事实、步骤、依据、动作及缺失状态，不用当前浏览器 DOM。`State.snapshot` 标为 visible_text，未声称是真 DOM；截图只提供路径/可用性，当前文本调查通道不读取像素。源码受当前 `project.root` 限定，拒绝越界，最多 20 文件、每文件 500 字符，有截断/检索范围说明。输入分段限额、总量有界；模型不能指定已完成状态或输入完整性。输出始终是根因/位置假设 |
| E07 UI/中断 | 仅终态 run 的稳定快照可发起回放，复用单任务占用。worker 保存无登录凭据的阶段/执行进度，由 parent 在共享锁内提交终态并失效缓存。停止/超时返回 inconclusive + termination，保留中断步骤、执行前缀和环境；页面展示前提、目标窗口、匹配依据与限制，失败仍可审核 |

新增的结构化匹配集中在 `replay/signals.py`，回放与聚类共用同一事实身份规则。Playwright 的结构化 page_error 消息可能没有异常名/冒号前缀，因此按已知事件类型与具体消息核对；裸泛化 console 文案仍不能证明再现。

## 2. 兼容与判定语义

- driver 的 `replay_data.action_sequence` 仍是成功动作历史；Evidence 回放包 v2 从末尾抽出当前目标动作，`action_sequence` 专指前置序列，`target_action` 单独执行。失败/不确定尝试不并入成功前缀，未知发出仍禁止宣称前提完整。
- 技术再现不依赖截图；认知回放使用保存的画面及原预期帮助复核，没有必需的 LLM 语义裁判。reproduced 不自动确认 Evidence，也不宣布共同根因。
- failed 表示回放没有完成；not_reproduced 要求可比较且完整的观察窗口；inconclusive 表示缺失、未稳定、前提偏移或中断。公开结果不包含 storage_state、cookies、输入值或捕获的私有页面文字。
- 入口重定向变化是 access 阶段故障，提示认证可能过期或环境改变，不把一个重定向直接认定为已登录/已退出。
- 旧 driver 只能提供当前会话快照时标明初始时间未知；旧包无法补造原 raw/step/basis。保存 DOM/技术文件缺失不以新页面内容替代。

## 3. 验证与复跑

真实浏览器包含入口异常、表单准备→客户端路由→目标异常、缺图技术匹配、history 深链静态恢复、资源/API 404、认证失效、外部服务保留和未支持作用域。确定性回归包含损坏包、错误窗口、method/URL/status 差异、截断、不同按钮相同文案、basis 差异、聚类中断、调查失败及共享缓存更新。

沿用 T02 锁版本 React/Vue/Vite/Next 样例，增加受控表单→提交→客户端导航→具体 JS 异常→新浏览器上下文回放的四条路径（React、Vue、Next App、Next Pages）。测试只证明特定机制路径；生产管线其他回归仍使用模型替身。第三方副本、依赖、缓存、构建、服务日志和运行材料均位于项目内 gitignore 目录。

```sh
# 依赖已准备时只重建项目内忽略目录；首次准备才显式增加 --install。
.venv/bin/python scripts/prepare_t02_frameworks.py
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  --run-frameworks --cov=alienqa --cov-report=term \
  --cov-report=json:.venv/t05-coverage.json \
  --junitxml=artifacts/evaluation/t05-frameworks/junit.xml
.venv/bin/python -m build --no-isolation --outdir .venv/dist/t05
```

最终全量（含显式框架套件）**620 项通过，覆盖率 87.59%**，较 T02 基线新增 46 项回归。真实框架套件共 **20 项**，其中 T05 新增异常独立回放 **4 项**。sdist/wheel 构建与源码、模板、测试样例及第三方排除项核对通过；`git diff --check` 和文档本地链接核对通过。JUnit、汇总及每条异常回放结果保存于项目内忽略的 `artifacts/evaluation/t05-frameworks/`，完整日志/覆盖率位于 `.venv/t05-tests.log`、`.venv/t05-coverage.json`。

## 4. 开放范围

- 本轮真实模型/API/Codex CLI 调用 **0 次**；调查根因准确率、独立人审和真实小应用 gate 未关闭。
- 回放不能恢复外部业务数据、sessionStorage、IndexedDB、SSO/验证码或自动续期；背景窗口只做有界观察，不保证原计时任务再次出现。
- frame/shadow 全链路仍未支持；Next 的额外 shadow 区域仍保留未验证诊断。单一路径匹配不把原不完整扫描改为完整。
- SPA 回退是回放消费者的能力；T01 F07 的自动部署探测/CLI/UI 配置生产者仍需后续实施。所选应用 root 由现有 loader 提供，完整 monorepo 选择属于 T01。
- 调查使用有界文本片段，不建设 source map、全仓理解、组件树或后端链路追踪。当前没有新增手工合并/拆分或按需调查平台。
- 尚未执行干净安装、Windows 或远程 CI 发布验收；这些仍属 T07/T09。
