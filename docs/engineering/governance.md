# Git 软件工程治理规范

> 本仓库的协作、提交、评审、发布约定。目标是让历史可追溯、可回滚，并为未来的商业化演进保留审计与版本管理基础。

---

## 1. 目标

- 用 Git 统一协作，保证每个改动可追溯、可回滚。
- 明确分支、提交、评审、发布四类约定，降低协作摩擦。
- 为未来付费化预留版本与审计基础（商业化改动单独标注）。

## 2. 仓库结构约定

- `docs/` 目录**只放工程文档**（PLANBOOK、治理、商业化设计等），不混入源码。
- 源码与运行产物分离：`artifacts/`、`reports/`、`evidence.db` 等**不入库**（见 `.gitignore`）。
- 密钥、本地配置（`config.local.yaml`、`.env`）一律不入库。

## 3. 分支模型（trunk-based 简化版）

| 分支 | 用途 | 规则 |
|---|---|---|
| `main` | 始终可发布 | 受保护，只经 PR 合并，禁止直推 |
| `develop` | 集成（可选） | 多特性并行时启用 |
| `feature/<name>` | 功能开发 | 短命，建议 ≤3 天合入 |
| `fix/<name>` | 缺陷修复 | 关联 issue |
| `chore/<name>` | 杂项/文档/工程 | 不涉及业务逻辑 |

规则：
- 一个分支只做一件事；小步提交。
- `main` 上出现问题，优先 `hotfix` 快速修复。

## 4. Commit 规范（Conventional Commits）

格式：

```text
<type>(<scope>): <subject>

[body]

[footer]
```

- `type`：`feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `build` / `perf` / `ci` / `revert`。
- `scope`：可选，如 `agent`、`driver`、`report`、`licensing`。
- `subject`：祈使句，50 字内，不加句号。
- `body`：说明 **为什么** 改，而非重复代码。
- `footer`：关联 issue，如 `Closes #12`。

示例：

```text
feat(agent): 增加探索步数预算控制

预算耗尽即停止探索，避免无限循环，也为未来按量计费留计量点。
Closes #12
```

## 5. PR 与 Code Review

- 一功能一 PR，先合并基线再开工，避免大 PR。
- PR 描述模板：**背景 / 改动 / 测试 / 截图 / 风险**。
- 至少 1 人 review 通过后方可合并。
- 合并策略：squash 到 `main`，保持线性历史。

## 6. Issue 管理

- 标签：`bug` / `feature` / `docs` / `question` / `commercial`。
- 报告 bug 必须附：复现步骤、预期、实际、截图/日志。
- 涉及 `licensing/` 或计量的改动，统一打 `commercial` 标签。

## 7. 版本与 Tag（SemVer）

- 版本号 `MAJOR.MINOR.PATCH`（语义化版本）。
- 发版打 tag：`v1.0.0`，并维护 `CHANGELOG.md`。
- `MAJOR`：不兼容变更；`MINOR`：向后兼容新增；`PATCH`：修复。

## 8. 提交钩子（pre-commit）

- 建议引入 `pre-commit`：提交前自动跑 `ruff` 与 `pytest`。
- 钩子失败即阻断提交，保证 `main` 永远可构建。

## 9. 治理权限

- `main` 受保护：禁止 force-push、禁止直推。
- 合并需审批；付费/商业化相关改动需额外标注并在 PR 说明影响面。

## 10. 与商业化预留的衔接

- 商业化能力集中在 `alienqa/licensing/`，核心测试逻辑不得依赖具体支付实现。
- 相关改动见：[commercialization.md](commercialization.md)。
