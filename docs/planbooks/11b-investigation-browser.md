# 模块 11b：Investigation Agent（浏览器黑盒调查）

> 是 [`11-investigation-agent.md`](11-investigation-agent.md) 的 **b 变体**：没有源码可看，只能"看浏览器"时定位根因。
> 一句话："我不翻源码，我只根据 DOM、控制台、网络和截图反推为什么。"

---

## 1. 定位

11b 与 11 的差异只有一点：**专家上下文的"源码"通道关闭**（`visible_files=[]` → `retrieve_source` 返回空）。
其余通道——DOM、console、network、API、action trace、截图——照常可用。
因此 11b **几乎零改动**，只需确认空源码时不报错、调查质量不塌。

| 通道 | 11（源码） | 11b（黑盒） |
|------|-----------|-------------|
| 源码 / 组件 | ✅ 关键词检索 visible_files | ❌ 无 |
| DOM | ✅ `driver.dom()` | ✅ 同左 |
| console / network / api | ✅ | ✅ 同左 |
| action trace（复现步骤） | ✅ | ✅ 同左 |
| 截图（Evidence artifacts） | ✅ | ✅ 同左 |

## 2. 输入

- `Issue`（10）+ 关联 Evidence + `InvestigatorContext`（**source=""**，其余通道有值）。

## 3. 输出

与 11 完全相同的 `Investigation`：

```json
{
  "issue_id": "ISSUE-007",
  "root_cause_hypothesis": "点击按钮后控制台出现 Uncaught TypeError，DOM 未更新",
  "reproduction_steps": ["1. 打开页面", "2. 点击 X", "3. 观察控制台与 DOM 无变化"],
  "technical_evidence": { "stack_trace": "...", "api": "GET /x -> 404", "component": "（DOM 中 #app 子树）" },
  "affected_components": ["#app"]
}
```

## 4. 关键设计

- **根因降级为"行为根因"**：黑盒看不到组件名，`component` 用 DOM 子树选择器（如 `#root` 下某块）代替文件名；根因表述从"某组件未渲染"降级为"点击后 DOM/控制台/网络出现的现象"。
- **证据优先级**：console/pageerror > network(404/500/refused) > DOM 前后 diff > 截图视觉变化。
- **复现步骤依旧优先引用 Evidence 的 action trace**（不依赖源码）。
- `InvestigatorContext.to_text()` 已支持空 source（`if value:` 跳过），无需改动。

## 5. 接口契约

```python
class InvestigationAgent:
    def investigate(self, issue: Issue, expert_ctx: InvestigatorContext) -> Investigation: ...  # 不变
    def investigate_issue(self, project, issue, evidences, driver=None) -> Investigation: ...    # 不变（project.visible_files 为空即黑盒）
```

## 6. 关系

- 上游：`10 Evidence Deduplicator`（不变）。
- 下游：`12 Human Review + Report`（不变）。

## 7. 实现要点

- `build_investigator_context` 里 `retrieve_source(project, ...)` 对空 `visible_files` 返回 `""` 即可（已满足）。
- **已实现增强**：黑盒（`source` 为空）时，`_dom_channel` 优先取问题动作 selector 附近的 DOM 子树（`driver.dom(selector)`），再回退整页 DOM 截断 5000 字符——控制 prompt 长度且聚焦问题区域。

## 8. 验收标准

- 对"点击后控制台报错"类 Issue，黑盒下能产出指向该报错的 Root Cause Hypothesis 与可执行复现步骤。
- `visible_files=[]` 时 `investigate_issue` 不抛异常，`source` 通道为空。

## 9. 开放问题

- 黑盒根因的可信度上限（看不到源码，只能"现象级"定位）如何在报告中标注置信度。
- 是否引入"多步探测"（对同一 Issue 用不同 selector 再点一次验证假设）——延后。
