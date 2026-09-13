# 模块 01：Project Loader（项目装载器）

> 回答："我现在到底拿到了什么？"——第一阶段尽可能**确定性扫描**，不做大量 LLM 推理。

---

## 1. 职责

- 识别输入类型：Git repository / Docker image / zip / URL / localhost / CI preview。
- 确定性识别前端框架与项目事实。
- 提取：build command、dev command、routes、dependencies、environment、entry points、artifacts。
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
  "artifacts": { "dist": ".next", "static": "public" }
}
```

## 4. 关键设计

- **确定性优先**：文件系统扫描 + JSON/正则解析；LLM 仅兜底（如从 README 推断运行方式）。
- **路由提取按框架适配**：Next.js 文件路由（`app/` 或 `pages/`）、React Router 配置、Vue Router、静态站点目录。
- **适配器模式**：每种输入类型一个 adapter（`GitAdapter / DockerAdapter / ZipAdapter / UrlAdapter / LocalhostAdapter / CiPreviewAdapter`）。
- **结果缓存**：同一项目识别结果落盘缓存，避免重复扫描。

## 5. 接口契约

```python
class ProjectLoader:
    def load(self, source: Source) -> Project: ...
    def detect_input_type(self, source: Source) -> InputType: ...
    def detect_framework(self, project_root: Path) -> Framework: ...
    def extract_routes(self, project_root: Path, framework: Framework) -> list[str]: ...
```

## 6. 关系

- 上游：无（系统入口）。
- 下游：`02 Product Mapper`（提供项目事实）。

## 7. 实现要点

- 递归扫描需尊重 `.gitignore`，跳过 `node_modules / dist / .next / build`。
- Docker 输入：读镜像内 `package.json` / 静态产物，或运行容器探测。
- CI preview：读取 CI 产物（构建目录 + 路由清单）而非源码。
- 用 [`docs/engineering/baselines.md`](../engineering/baselines.md) 中的三个仓库作为识别 ground truth。

## 8. 验收标准

- 对 Next.js / Vite(React/Vue) / React Router 项目，能确定性给出 `framework / start / build / routes`。
- 对 zip / docker / localhost 三种输入，能稳定识别 `input_type` 与 `base_url`。

## 9. 开放问题

- 非标准构建工具（monorepo、pnpm workspace）的路由/入口识别策略待细化。
- CI preview 的产物如何安全拉取与解析。
