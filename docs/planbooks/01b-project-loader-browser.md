# 模块 01b：Project Loader（浏览器黑盒装载）

> 是 [`01-project-loader.md`](01-project-loader.md) 的 **b 变体**：没有完整源码、只能从浏览器看到前端时的装载路径。
> 一句话："我不扫磁盘，我只问浏览器：你现在页面上有什么？"

---

## 1. 定位

在 **浏览器黑盒模式（blackbox mode）** 下，01 不再做文件系统扫描 / 框架识别 / visible_files 选取，
而是把「当前 URL + 浏览器实时 DOM」当作项目事实来源。其余 12 个模块不变。

| 变体 | 输入 | visible_files | framework |
|------|------|---------------|-----------|
| 01（源码） | repo / zip / docker / localhost | 有（扫磁盘） | 确定性识别 |
| **01b（黑盒）** | **一个可达 URL** | **空（[]）** | `browser` |

## 2. 输入

```text
一个可达的前端 URL（如 http://localhost:3001）
可选：登录态文件路径（storage_state.json）——用户自己浏览器里已有登录，黑盒才能看到业务内容
```

## 3. 输出

复用 [`Project`](../../alienqa/loader/models.py)，但字段最小化：

```json
{
  "input_type": "browser",
  "framework": "browser",
  "base_url": "http://localhost:3001",
  "routes": ["/"],
  "entry_points": ["http://localhost:3001"],
  "visible_files": [],
  "storage_state": "config/session.json",
  "selection_audit": { "total_files": 0, "included": 0 }
}
```

> `visible_files=[]` 是刻意为之：黑盒下不存在"用户可见源码文件"，后续 11b 调查只能依赖 DOM/网络。

## 4. 关键设计

- **装载 = 打开 URL + 抓取 DOM**：`driver.launch(url)` 后，`driver.visible_text()` / `driver.interactive_elements()` / `driver.dom()` 就是全部"表面"。
- **不做框架识别**：黑盒下框架是未知的（也没必要知道），`framework="browser"`。
- **入口即 URL**：不需要 01+ 的 `EntryDetector`（没有磁盘目录可扫），也不需要 `UnitLocator` 在装载阶段介入（定位推迟到有 DOM 后由 02b/06 阶段处理）。
- **与 01 完全复用 `Project` 数据模型**：下游 02→13 只认 `Project`，不关心它是怎么来的。

## 5. 接口契约

```python
class ProjectLoader:
    def load_browser(self, base_url: str, routes: list[str] | None = None,
                     storage_state: str | None = None) -> Project: ...
    # 原 load() 不变，仅供源码模式使用
```

## 5.1 登录态（storage_state）

纯 URL 到不了登录墙后面的业务内容，所以黑盒模式必须能带上「用户自己浏览器里的登录态」：

- **采集**：`python -m alienqa --login <url>` 起有头浏览器，用户手动登录后按回车，Playwright 把 cookies + localStorage 存成 `config/session.json`（`capture_session`）。
- **装载**：`load_browser(url, storage_state="config/session.json")` → `Project.storage_state`。
- **使用**：`02b/04` 在 `driver.launch(url, storage_state=project.storage_state or None)` 时把会话透传给 Playwright `new_context(storage_state=...)`，浏览器一开就带着登录态。
- **安全**：`session.json` 视为密钥类文件，已入 `.gitignore`，不上传仓库。

## 6. 关系

- 上游：无（系统入口，来自用户的 URL）。
- 下游：`02b Product Mapper (Browser)`。

## 7. 实现要点

- `Project(root="", framework="browser", base_url=url, routes=routes or ["/"], entry_points=[url], visible_files=[])`。
- 不需要适配器（GitAdapter/DockerAdapter 等只在源码模式用）。

## 8. 验收标准

- 给定一个 URL，能构造出 `input_type="browser"`、`visible_files=[]` 的最小 `Project`。
- 给定 `storage_state`，`Project.storage_state` 正确透传；`driver.launch(url, storage_state=...)` 带会话打开。
- 下游 02b/04 能直接消费该 `Project` 且不因 `visible_files` 为空而报错。

## 9. 开放问题

- 黑盒下是否要自动推断 SPA 路由清单（从 DOM 链接抓取），还是等 06 探索时边点边发现——倾向后者，待定。
