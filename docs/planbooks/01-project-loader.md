# 模块 01：Project Loader（项目装载器）

> 回答："我现在到底拿到了什么？"——第一阶段尽可能**确定性扫描**，不做大量 LLM 推理。

---

## 1. 职责

- 识别输入类型：Git repository / Docker image / zip / URL / localhost / CI preview。
- 确定性识别前端框架与项目事实。
- 提取：build command、dev command、routes、dependencies、environment、entry points、artifacts。
- **确定性选取"前端用户可见表面"（visible_files）**：不无脑加载全部，过滤噪音，只留用户看得见的页面/组件/文案。
- 输出结构化 `Project` 对象。

## 2. 输入

```text
git repository | docker image | zip | url | localhost | ci preview
```

## 3. 输出

```json
{
  "input_type": "git_repository",
  "framework": "Next.js",
  "start": "npm run dev",
  "build": "npm run build",
  "base_url": "http://localhost:3000",
  "routes": ["/", "/login", "/dashboard", "/orders"],
  "dependencies": { "next": "14.x", "react": "18.x" },
  "environment": { "node": ">=18", "env_files": [".env.local"] },
  "entry_points": ["src/app/page.tsx", "src/app/login/page.tsx"],
  "artifacts": { "dist": ".next", "static": "public" },
  "frontend_apps": [
    { "framework": "Next.js", "name": "web", "manifest": "apps/web/package.json", "base_dir": "apps/web" }
  ],
  "visible_files": [
    { "path": "src/app/login/page.tsx", "role": "route", "lines": 120, "ui_score": 0.9 }
  ],
  "selection_audit": {
    "total_files": 18000, "included": 212,
    "excluded_tests": 320, "excluded_backend": 870, "excluded_generated": 45
  }
}
```

## 4. 关键设计

- **确定性优先**：文件系统扫描 + JSON/正则解析；LLM 仅兜底（如从 README 推断运行方式）。
- **路由提取按框架适配**：Next.js 文件路由（`app/` 或 `pages/`）、React Router 配置、Vue Router、静态站点目录。
- **适配器模式**：每种输入类型一个 adapter（`GitAdapter / DockerAdapter / ZipAdapter / UrlAdapter / LocalhostAdapter / CiPreviewAdapter`）。
- **结果缓存**：同一项目识别结果落盘缓存，避免重复扫描。
- **分层漏斗过滤**：L1 硬排除（node_modules/dist/测试/配置/二进制）→ L2 定位前端表面（按框架找 `app/`、`pages/`、`src/`、`apps/web/`、`app/javascript` 等）→ L3 可见性评分 + 预算截断。
- **"用户可见"判定（确定性，不用 LLM）**：白名单位置 + UI 标记打分（`<button/input/form/a/h1/onClick/v-model/v-on/return (` 等）；纯 utils/types/hooks 降权或排除。
- **多前端应用枚举（不假设"一仓一框架"）**：逐个 `package.json` 独立分类（只看 `dependencies`，把"应用"与"组件库/工具包"区分），枚举出仓库内所有前端应用；再用数据驱动评分（入口信号 + 表面规模 + 卫星站点命名降权）选出主应用。兼容同一仓库混合多框架（如 twenty 的 React 主应用 + Next.js 网站）。
- **应用 vs 后端/库的入口信号**：只有存在 `index.html` / `vite.config.*` / `next.config.*` / 路由文件等前端入口时才算"前端应用"，避免把 NestJS 等后端（其依赖里可能也含 react）误判。
- **全栈仓库切后端**：chatwoot 只留 `app/javascript`（Vue）、丢 Rails `app/controllers|models`；cal.diy 只留 `apps/web`、丢 `apps/docs|website`；twenty 只留 `twenty-front`、丢 `twenty-server`。
- **有界输出**：总量/单文件行数/文件数三层预算，超限按"路由 > 页面/组件 > 通用组件 > 文案"排名截断，宁可少不可脏。

## 5. 接口契约

```python
class ProjectLoader:
    def load(self, source: Source) -> Project: ...
    def detect_input_type(self, source: Source) -> InputType: ...
    def detect_frontend_apps(self, project_root: Path) -> list[FrontendApp]: ...
    def detect_framework(self, project_root: Path) -> Framework: ...
    def extract_routes(self, project_root: Path, framework: Framework) -> list[str]: ...
    def select_visible_files(self, project_root: Path, framework: Framework, budget: Budget) -> list[VisibleFile]: ...
```

## 6. 关系

- 上游：无（系统入口）。
- 下游：`02 Product Mapper`（提供项目事实）。

## 7. 实现要点

- 递归扫描需尊重 `.gitignore`，跳过 `node_modules / dist / .next / build`。
- Docker 输入：读镜像内 `package.json` / 静态产物，或运行容器探测。
- CI preview：读取 CI 产物（构建目录 + 路由清单）而非源码。
- 全栈仓库需按框架切分前端/后端目录，`visible_files` 只取前端表面。
- `selection_audit` 记录排除统计，便于人工审计与调阈值。
- 用 [`docs/engineering/baselines.md`](../engineering/baselines.md) 中的三个仓库作为识别 ground truth。

## 8. 验收标准

- 对 Next.js / Vite(React/Vue) / React Router 项目，能确定性给出 `framework / start / build / routes`。
- 对 zip / docker / localhost 三种输入，能稳定识别 `input_type` 与 `base_url`。

## 9. 开放问题

- 非标准构建工具（monorepo、pnpm workspace）的路由/入口识别策略待细化。
- CI preview 的产物如何安全拉取与解析。
