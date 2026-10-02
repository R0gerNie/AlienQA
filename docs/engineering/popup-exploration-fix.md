# 弹层探索、目标身份、输入分支与焦点观察

日期：2026-10-02。由[三应用真实基线](open-source-applications.md)中的 Memos 菜单阻挡驱动本轮修复。用户授权完成回归后提交推送；不把模型误报、人审或用户采信作为验收门槛。

## 改动与边界

| 模块 | 改动 | 验证重点 |
|---|---|---|
| T02 浏览器枚举 | 优先枚举已展开的 menu/listbox、模态 dialog 和原生 popover 的末级弹层；识别 DOM 嵌套及 ARIA 触发关系 | 用展开状态或动作后的新出现关系区分常驻导航；弹层打开时不操作被挡背景；无关联的多个弹层明确歧义；关闭后恢复原页面 |
| T02 / T03 单元范围 | 候选带原始触发链，UnitScope 接受由该单元触发的 portal 控件；无 ARIA 连接时使用同 URL 下动作前后新出现弹层的观察 | 初始 scope 不扩大为全页面；无关弹层不能越过范围；隐藏/离开 URL 后清理临时关联 |
| T02 恢复与调度 | 菜单/listbox 提供低优先级 Escape 探测，从层内可聚焦控件发出；已打开弹层降低再打开优先级 | 先检查层内候选，再尝试退出；返回后优先继续剩余工作；不强制点击，不假定 Escape 一定关闭 |
| N03 目标描述 | Target 增加可选 visible，提供角色、可见名称、页面位置、展开能力/状态、焦点和空/非空状态；事前输入标为 `visible-action-v2` | 无文案按钮有可识别的事前身份；白名单不传 CSS、输入值、密码或事后弹层内容；旧 Action 仍可读取 |
| T02 输入分支 | 从可见 label/placeholder 识别 JSON 字段，构造固定合法 JSON、非法文字和空值；记录 Action.input_branch | 已成功分支在相同 URL/字段不反复填写；不截断合法 JSON 或绕过 pattern；表单先尝试合法提交再探测替代输入 |
| N05 焦点事实 | execution 保存 target_focused、document_has_focus、目标可见/存在状态及步骤引用，送入判定的 control_state | 动作前后事实与本步绑定；未知/消失不能变成 false；焦点状态不能证明特定光标或样式呈现 |

可见目标信息来自浏览器事前 DOM 布局和可访问属性；没有读取框架对象、事件处理函数或产品内部答案。输入分支当前重点支持 JSON，不宣称所有业务格式都能自动构造。通用行业预期、采样并集与局部未知仍保持 `general-user-v4 / sampling-merge-v3 / judgment-v3`；源码和输入契约增量另行冻结。

弹层关联采用可观察的触发关系及动作前后变化，有限范围内仍可能缺少关系、遇到歧义或无法退出；保留未执行与失败，不借助强制点击绕过遮罩。源码版本及临时状态变化可能使历史回放条件不同。

## 测试与真实复测

新增 `tests/test_popup_exploration.py` 与 `tests/fixtures/popup-app/`，覆盖菜单、子菜单、无关联 portal、范围外背景、多模态歧义、Escape、返回保存、目标白名单、JSON 分支/表单和焦点血缘。生产管线测试通过模型替身检查全部生成/执行/判定链路，不用替身成绩替代真实模型结果。

首轮完整默认回归暴露两项旧 Mock 的弹层枚举兼容问题和一项只列三个动作字段的回放断言。驱动对非列表枚举结果保留兼容；回放断言改为逐项核对完整已保存动作，包含新增分支字段。JSON 表单另有先测试非法输入而阻挡合法提交的问题，按回归调整调度。失败记录保留，最终回归采用修正后的源码。

真实复测复用原授权 200 次批次：上一轮已用 105 次，本轮硬上限 95，覆盖所有模型角色、失败、修复及报告。冻结目录 `artifacts/evaluation/popup-fix-20261002/frozen/`；结果目录 `artifacts/evaluation/popup-fix-real-20261002/`。Memos 定向 8 步优先执行，IT-Tools 定向与 TodoMVC 自主各 4 步。

命令：

```bash
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/browsers"
.venv/bin/python scripts/run_application_suite.py \
  --output artifacts/evaluation/NEW-OUTPUT \
  --real-model --max-calls REMAINING-AUTHORIZED-CALLS \
  --cases memos-directed it-tools-directed todomvc-autonomous \
  --case-actions memos-directed=8 --config config/codex.yaml
```

`--cases` 保留指定顺序，`--case-actions` 只修改所选场景的动作预算；默认仍是六个四步场景。不同运行目录不能重置或重复使用本批调用额度，旧结果和剩余额度分别记录。全部源码、工具链、缓存、会话、数据与结果继续位于项目内 gitignored 路径。

## 最终结果

发布版本完整默认回归 **817 passed、0 failed、0 skipped**，覆盖率 **88.11%**；另外 **24 条锁版本 React/Vue/Next 结构、交互与回放路径通过**。wheel/sdist 及运行/验收资产核对通过，新增 popup 夹具包含于 sdist，第三方目录排除。结果在 `artifacts/evaluation/popup-fix-20261002/{release-regression.xml,release-coverage.json,frameworks.xml,distribution.json}`，早先失败和复测日志保留。

| 真实场景 / 本机报告 | 动作与状态 | 来源候选 → 要求 | 发现 / 未知要求 | 调用 |
|---|---|---:|---:|---:|
| [Memos 定向](../../artifacts/evaluation/popup-fix-real-20261002/model/case-001-run-1/analysis.html) | 八步均执行完成；包含菜单、Upload、Private 和 Save；6 passed、1 mismatch、1 inconclusive，run partial | 34 → 31 | 2 / 2 | 38 |
| [IT-Tools 首次定向](../../artifacts/evaluation/popup-fix-real-20261002/model/case-002-run-1/analysis.html) | 常驻导航误判为多个弹层，0 动作；partial，保留失败分母 | 0 → 0 | 0 / 0 | 2 |
| [TodoMVC 自主](../../artifacts/evaluation/popup-fix-real-20261002/model/case-003-run-1/analysis.html) | 输入、失焦、Enter 新增、再次输入四步 passed；run completed | 15 → 12 | 0 / 0 | 18 |
| [IT-Tools 修复后定向](../../artifacts/evaluation/popup-fix-real-20261002-static-menu/model/case-001-run-1/analysis.html) | 合法 JSON、失焦、非法 JSON、失焦四步 passed；run completed | 20 → 16 | 0 / 0 | 18 |

Memos 保存后页面出现本次正文 `AlienQA test`；原来被遮罩挡住的触发按钮未再被反复点击。两条 Upload 主观落差都保留到 Evidence 与 HTML，该步骤没有原生文件选择窗口的观察记录，不能将这两条直接宣称为 upstream 产品缺陷。Save 的权限标识要求保留未知，编辑器的 Private 不冒充已保存条目的可见权限依据。

本轮共 **16 个动作完成，69/69 来源成员与 59/59 合并要求保留，2/2 judge 落差进入 Evidence 和 HTML**；全部四份报告存在。`completed` 表示当前已选步骤处理完成，仍是有限动作范围，不代表整个应用 QA 通过。错误的常驻菜单分类已由回归与新的真实扫描修复，原零动作记录未覆盖。

追加 **76 次**：expectation=32、gist=9、visual=16、judge=16、investigator=2、reporter=1。全部响应成功，attempt 与调用预算对齐；已返回 prompt_tokens=707537、completion_tokens=12902，76 次金额/币种及 total_tokens 仍未知。原 200 次批累计 **181/200，余 19 次**，未另开额度。合并账目见本机 [batch-reconciliation.json](../../artifacts/evaluation/popup-fix-20261002/batch-reconciliation.json)。

修复后 IT-Tools 的源码另存 `frozen-static-menu-fix/`，使用先前 58 次复测之后剩余 37 次硬上限，实际用 18 次。首批冻结后的旧替身兼容和 JSON 表单调度改动以工程复测记录；首批三个真实场景的输入与源快照不重写。

本机未重新创建新依赖安装环境，旧 CI 不归给本版本。推送通道使用已有 SSH；当前机器的 GitHub CLI 未登录，公开 Actions API 返回 403，网页和浏览器通道也未取得状态，因此远程 CI 结果保持未知，不能记为通过。

## 下一步

优先增加原生文件选择、上传等当前不可见窗口的事件/观察记录，以及更长的编辑、保存、删除等任务路径；保留模型主观要求，不以这些新事实删除旧发现。正常/异常/合理例外及两步历史控制仍需在当前契约下单独复跑。保留动作上限、焦点与样式差别、权限标识未知及多弹层歧义，不承诺绝对无漏报。
