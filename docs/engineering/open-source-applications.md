# 开源应用测试：TodoMVC、IT-Tools 与 Memos

日期：2026-10-02。目标是检验 AlienQA 对真实页面的探索、采样并集和发现交付能力。人工审核、误报率、用户接受率均不是验收门槛；浏览器机制断言也不用于否决模型提出的落差。

## 固定样例与搭建

| 应用 | 固定源码版本 | 本机运行方式 | 本轮关注 |
|---|---|---|---|
| [TodoMVC](https://github.com/tastejs/todomvc) React 示例 | `ff43b02e59dfa604386bb382034b2cd07c2bcd8a` | 复用已有构建；静态服务 | 新增、完成、筛选、Enter 与动作历史 |
| [IT-Tools](https://github.com/CorentinTh/it-tools) | `d505845f918e946ec300af7b36efc107e2f66e9e` | pnpm 9.11.0 锁文件安装与生产构建；SPA 静态服务 | 工具导航、转换、输入校验和侧栏覆盖 |
| [Memos](https://github.com/usememos/memos/tree/v0.25.3) | `e17cd163c6c37726f8397c8f426d585b540c9562`，v0.25.3 | 前端 release 构建、Go 编译、SQLite 本机实例 | 登录后编辑、保存、状态连续性及单元定位 |

本轮验证环境为 macOS arm64、Node v25.1.0、Go 1.27.1、项目内 Playwright Chromium。固定的是源码 commit，不跟随 latest；Memos 选择可重复构建的既有版本，不宣称它是最新发行版。

所有第三方源码位于 `examples/open-source/`，依赖、pnpm store、npm 缓存、Go 工具链、模块/构建缓存和临时文件都在 `examples/open-source/real-app-suite/`。数据库、会话、截图与报告写入 `artifacts/evaluation/`。这些路径已由 gitignore 排除，第三方源码和构建不会进入 AlienQA wheel/sdist。没有使用 Docker，也没有安装系统级 Go 或 pnpm。

Go 的 macOS 遥测目录需额外用 `TEST_TELEMETRY_DIR` 指定，通用 `XDG_CONFIG_HOME` 不能覆盖它。首轮构建产生过项目外的六个遥测副产物；准备脚本已修正并验证项目内目录。自动审批曾拒绝迁移这些文件，随后用户明确授权只删除本轮六项，已完成删除且未读取或迁移内容；清理核对记录为 `go-telemetry-cleanup.json`。

源码准备入口：

```bash
.venv/bin/python scripts/prepare_t09_todomvc.py --install
.venv/bin/python scripts/prepare_application_suite.py --install
```

后一个脚本只为 macOS arm64 提供已验证的 Go 工具链下载配方。已有 checkout 版本不匹配时停止，不自动 reset 或覆盖；日志、锁文件与失败产物保留。

## 两类测试与六个模型场景

浏览器机制验证不调用模型：

- TodoMVC：新增两项、完成一项、Active 筛选；新浏览器上下文为空。
- IT-Tools：合法 JSON 得到可见 YAML 输出，非法 JSON 得到可见校验文字。
- Memos：真实注册账号、保存 memo、重载后仍可见；为两个模型场景另建不同空白账号。

模型运行保留自主和定向两个分母：

| 场景 | 入口 / 范围 | 初始条件 | 动作上限 |
|---|---|---|---|
| TodoMVC 自主 | 根页面 | 空白上下文 | 4 |
| TodoMVC 定向 | `#/active` | 空白 Active 页面 | 4 |
| IT-Tools 自主 | 根页面 | 空白上下文 | 4 |
| IT-Tools 定向 | `/json-to-yaml-converter` | 未填写的转换页 | 4 |
| Memos 自主 | 登录后的根页面 | 独立空白用户 | 4 |
| Memos 定向 | 根页面，单元 `Memo editor` | 另一独立空白用户 | 4 |

这里的定向是指定入口或定位单元，动作仍由 AlienQA 自己选择。它不是预写操作序列；四步有限探索也不代表完成整个业务流程。单元无法定位、动作失败或预算未执行均保留原状态。

产品 README、测试断言、数据初始化配方不传给预期模型。登录态是执行前提；模型只读事前可见输入及前序可见历史。Memos 的预置浏览器验证账号与两个模型账号隔离，避免验证数据污染后续场景。

### TodoMVC 初始条件更正

首批应用 manifest 曾将 TodoMVC 定向配方写成“两条待办、一条已完成”。实际固定 React 样例用内存中的 `useReducer(..., [])` 保存待办，`storage_state` 无法传递这些数据；扫描第一步也显示页面为空。

原 manifest 和模型输入保持不变，另存 `preparation-corrections.json` 说明实际条件。当前脚本已去掉错误的预置会话声明，并在浏览器验证中显式检查新上下文为空。该模型场景只能解释为空白 Active 入口的探索，不能宣称验证了已有待办的编辑或筛选。单独的浏览器增删/完成/筛选验证仍有效。

## 运行与计量

先仅做浏览器验证：

```bash
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/browsers"
.venv/bin/python scripts/run_application_suite.py --output artifacts/evaluation/oss-browser-new
```

显式真实模型运行：

```bash
.venv/bin/python scripts/run_application_suite.py --output artifacts/evaluation/oss-model-new --real-model --max-calls 200 --config config/codex.yaml
```

`--real-model` 默认关闭。真实运行须使用新的授权调用预算；此处 200 是本轮授权上限，不能通过重启新目录重复使用同一批额度。六个场景在同一个 evaluation 进程共享预算，包含生成、解析修复、fallback、调查与 reporter。复用本机既有 Codex 登录，不建立新的 CODEX_HOME，不导出凭据。

服务固定绑定 `127.0.0.1:5310`、`:5311`、`:5232`，结束后回收。端口被占用时失败，不借用别人的实例；新输出目录不覆盖旧结果。回放需重新提供对应端口、应用和数据条件，当前脚本结束后的离线 HTML 阅读不依赖服务。

对账命令：

```bash
.venv/bin/python scripts/summarize_application_suite.py artifacts/evaluation/oss-model-new/model
```

它核对来源成员、合并要求、判定落差、已保存 Evidence 和 HTML 中的证据 ID，并汇总全部 attempt、角色、已知 token 与未知费用。运行途中 budget checkpoint 可能落后于正在执行的 attempt；只有终态账目才用于最终对齐。它不评审落差的语义，不给报告设置误报率门槛。

## 本轮记录

配置与源码快照保存在 `artifacts/evaluation/oss-apps-20261002-frozen/`。真实运行目录为 `artifacts/evaluation/oss-apps-real-20261002/`，当前使用 `general-user-v4 / sampling-merge-v3 / judgment-v3`，默认双采样，新批上限 200；与旧批 98/100 分开记账。

首次浏览器准备在 IT-Tools 生产构建的控件定位处失败：构建移除了测试属性，后改用可见占位文字定位。失败目录和日志保留，当时模型调用为零。随后三应用浏览器机制验证通过。模型场景与最终对账结果见下节，不能把“搭建成功”当成模型探索完成。

## 结果与下一步

六个场景都执行了四步并产出离线报告，状态均为 `partial`，停止原因为 `action_budget`；未知、截断和失败按各自记录保留。24 步为 **15 passed、8 inconclusive、1 action_failed**；23 个动作完成，1 个未发出。该状态描述扫描处理过程，不是应用质量分数。

| 场景 / 报告 | 来源候选 → 合并要求 | 无法判断的要求 | CLI 调用 | 实际到达范围 |
|---|---:|---:|---:|---|
| [TodoMVC 自主](../../artifacts/evaluation/oss-apps-real-20261002/model/case-001-run-1/analysis.html) | 17 → 13 | 2 | 18 | 输入、失焦、Enter 新增、再次输入 |
| [TodoMVC 定向](../../artifacts/evaluation/oss-apps-real-20261002/model/case-002-run-1/analysis.html) | 16 → 13 | 2 | 18 | 空白 Active 入口的同类四步 |
| [IT-Tools 自主](../../artifacts/evaluation/oss-apps-real-20261002/model/case-003-run-1/analysis.html) | 22 → 21 | 0 | 18 | 加解密、Token、Hash 导航及输入 |
| [IT-Tools 定向](../../artifacts/evaluation/oss-apps-real-20261002/model/case-004-run-1/analysis.html) | 20 → 18 | 4 | 18 | 转换页非法输入、失焦、离开转换页 |
| [Memos 自主](../../artifacts/evaluation/oss-apps-real-20261002/model/case-005-run-1/analysis.html) | 16 → 12 | 2 | 18 | 搜索与编辑器输入、失焦；没有保存 |
| [Memos 定向](../../artifacts/evaluation/oss-apps-real-20261002/model/case-006-run-1/analysis.html) | 6 → 4 | 1 | 15 | 编辑、失焦、打开工具栏菜单；下一点击被阻挡 |

机械对账确认 **97/97 来源成员保留，81/81 合并要求进入步骤记录**。13 条要求被记录为无法判断；Memos 无文案按钮的两步另有四份空采样及明确弃权理由，未伪造预期。全部六份 HTML 存在，没有来源成员或合并要求静默丢失。

本轮 judge 没有提出 mismatch，因此 Evidence 为 0，也没有触发 investigator/reporter 调用；静态 analysis 仍保存步骤、采样、未知和执行诊断。这不证明没有产品落差，也不能用这批零发现验证真实 mismatch→Evidence→报告的交付路径；该路径的机制回归另行保留。用户不必先认可模型观点才能保留发现。

**调用为 105/200，剩余 95；全部 105 次响应成功，失败/修复/fallback 为 0。** 角色为 expectation=48、gist=13、visual=22、judge=22、investigator=0、reporter=0。逻辑调用、CLI 启动和计量 attempt 对齐；已返回 prompt_tokens=970660、completion_tokens=13356，total_tokens、105 次金额/币种和供应商内部 HTTP 请求数未知，不折算为零费用。路由为 `codex/gpt-6.1-sol`、reasoning_effort=low；供应商内部模型构建版本未知。

最终依据：[运行汇总](../../artifacts/evaluation/oss-apps-real-20261002/model/evaluation.json)、[计量与候选对账](../../artifacts/evaluation/oss-apps-real-20261002/model/accounting-reconciliation.json)。最新配方的零模型浏览器验证在 `oss-apps-browser-20261002-final-v2/` 全部通过；此前与真实扫描同时启动的验证因端口占用失败，原失败目录保留。没有重复真实调用来覆盖原始结果。

工程回归为完整默认套件 799 passed，补充定向 24 passed；按 classname/name 取最新结果去重 **801 项通过、0 项未解决失败**，完整套件覆盖率 **88.10%**。JUnit、覆盖率和去重摘要在本轮真实运行目录。发行资产检查另验证三份新脚本、文档与许可证，以及第三方目录排除；不据此宣称当前未提交源码的远程 CI 或新依赖安装已验证。

### 实际缺口与复测门槛

1. **T02 弹层交互与 T03 单元范围更新优先。** Memos 菜单实际出现 Upload / Link Memo / Location / More，但定向范围仍绑定编辑器原控件，planner 再点同一个触发按钮。Playwright trial click 被 `<html>` 拦截，约 3 秒后未发出动作。错误文字 `action budget exhausted` 指单次动作超时，与四步扫描的 `stop_reason=action_budget` 是两个不同限制。应优先跟踪可见弹层、触发关系、可操作范围及恢复动作，保留阻挡原因，不使用强制点击掩盖问题。复测应能从编辑器进入菜单、操作或退出弹层，并继续到 Save；同时保留超时诊断和原始失败分母。
2. **N03 目标描述需要保留可见身份。** 同一无文案图标被描述成“当前控件”，四份采样都指出无法识别具体目标。这是事前输入缺口。复测应让模型能够关联已选目标和页面上的控件，允许基于图标/位置形成主观要求；不要传入执行后菜单内容来补写事前预期。
3. **T02 planner 的输入应覆盖有意义的分支。** JSON 转换页仍填固定 `AlienQA test`，没有进入合法转换路径；TodoMVC 对非空 Enter 还提出空输入条件要求，保留为未知。需记录条件是否已执行，并按可见控件语义生成合法、非法和边界输入，逐步覆盖这些分支；不删除条件要求来提高 passed。
4. **N05 补可观察状态。** Memos 失焦要求因截图看不到光标而无法判断。补充动作前后焦点等状态的事实引用，再用原始要求复测；观察不可得仍明确未知。IT-Tools 的侧栏控件、可见文字和历史截断也已进入运行记录，应针对主任务区域改进输入覆盖。

本轮完成的是可重复测试入口与真实有界基线，不是三个应用的全流程验收。下一轮优先处理上述实际探索和输入缺口，再扩大动作数或应用数；正常/异常/合理例外及两步历史控制样例仍需在 v4 下单独复跑。未使用的 95 次仍属于本批授权额度，不自动另开批次。

以上为修复前基线及当时剩余额度。随后已按上述缺口实施[弹层探索与输入/观察修复](popup-exploration-fix.md)，沿用同批剩余额度复测；源码版本、失败及调用增量分开记录，不覆盖本文原始结果。
