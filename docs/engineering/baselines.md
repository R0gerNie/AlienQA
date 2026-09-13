# 测试基线（Test Baselines）定稿

> 验证日期：2026-09-13。事实来源：各仓库 `main` / `develop` 分支的 `package.json` 与 `README.md`。
> 用途：为 `Project Loader`（01）与 `Browser Controller`（04）提供真实项目的开发与回归基准。

---

## 1. 结论速览

| 槽位 | 定稿仓库 | 框架 | License | 运行方式 | 可运行性 |
|---|---|---|---|---|---|
| Next.js（主） | `calcom/cal.diy` | Next.js + tRPC + React | MIT | `yarn dx`（Docker 起 PG + 种子账号） | ★★★★★ |
| Next.js（备） | `dubinc/dub` | Next.js(App Router) + Prisma + Turborepo | AGPL-3.0-or-later（Open Core） | `pnpm dev`（需自配 Postgres/Redis） | ★★★ |
| React SPA（主） | `twentyhq/twenty` | React + Vite(Nx) + NestJS | AGPL-3.0 | `yarn start`（需 PG + Redis） | ★★★ |
| Vue（主） | `chatwoot/chatwoot` | Vue 3 + Vite + Rails | MIT | `overmind start`（需 PG + Redis + Rails） | ★★★ |
| Vue（备） | `nocodb/nocodb` | Vue 3 + Nuxt | Sustainable Use License（非 OSI） | `docker run` 一行 | ★★★★★ |

---

## 2. 逐项验证记录

### 2.1 calcom/cal.diy —— Next.js 主选

- **框架**：README 明确 "Built With Next.js + tRPC + React.js + Tailwind CSS + Prisma"。
- **运行**：`yarn dx` 一键（需 Docker，自动起本地 Postgres 并写入种子用户）；手动模式 `yarn dev`（需自配 `DATABASE_URL`）。
- **种子账号**：`free@example.com / free`、`pro@example.com / pro`、`admin@example.com / ADMINadmin2022!` 等，登录地址 `http://localhost:3000`。
- **License**：MIT（100% 开源，无 Enterprise 代码）。
- **结论**：对 Browser Controller 最友好——有登录、有种子数据、接近一键起。

### 2.2 dubinc/dub —— Next.js 备选

- **框架**：Next.js + TypeScript + Tailwind + Prisma + Turborepo（App Router）。
- **运行**：`pnpm install && pnpm dev`（`turbo dev`）；要求 Node v23.11.0 / pnpm 9.15.9；依赖 Postgres(PlanetScale) + Redis(Upstash) + NextAuth。
- **种子**：`cd apps/web && pnpm run script dev/seed`。
- **License**：AGPL-3.0-or-later，Open Core（`/ee` 目录为商业授权）。
- **结论**：更典型的多租户 SaaS、路由清晰，适合 Loader 源码扫描；运行门槛高于 cal.diy。

### 2.3 twentyhq/twenty —— React SPA 主选

- **框架**：React + Vite（Nx monorepo），后端 NestJS + PostgreSQL + Redis；README 明确 React + Jotai + Linaria + Lingui。
- **运行**：`yarn start`（concurrently 起 `twenty-server` + `twenty-front` + worker）；Node `^24.5.0` / yarn 4.13.0；Docker Compose 可自托管。
- **License**：AGPL-3.0。
- **结论**：真实 CRM、前后端分离、SPA 导航与表单丰富；运行门槛中等。

### 2.4 chatwoot/chatwoot —— Vue 主选

- **框架**：Vue 3 + Vite + Rails（vite-plugin-ruby），vue-router、pinia；`package.json` 含 `vue ^3.5.12`、`vite 6.4.2`。
- **运行**：`pnpm install && overmind start -f Procfile.dev`（或 `foreman start`）；需 Rails + PostgreSQL + Redis；Node 24.x / pnpm 10.x。
- **License**：MIT。
- **结论**：真实客服 SaaS、交互面广（inbox / 会话 / 联系人 / 报表 / 自动化），License 干净。

### 2.5 nocodb/nocodb —— Vue 备选

- **框架**：Vue 3 + Nuxt（`nc-gui`）+ NestJS 后端。
- **运行**：`docker run -d ... -p 8080:8080 nocodb/nocodb:latest`（SQLite 免配置）→ `http://localhost:8080/dashboard`。
- **License**：**Sustainable Use License（非 OSI 开源）**。
- **结论**：运行最省事，但 License 非 OSI，仅作 Vue 备选/慎用。

---

## 3. 两个重要发现（相对最初候选的修正）

1. **cal.com 主仓库已转向 Open Core**：其 README 明确社区版为 `calcom/cal.diy`（MIT、无 Enterprise 代码）。故 Next.js 主选由 `calcom/cal.com` 改为 `calcom/cal.diy`。
2. **NocoDB 并非 OSI 开源**（Sustainable Use License），与"开源 SaaS 基线"的目标不完全吻合；Vue 主选改为 `chatwoot/chatwoot`（MIT），NocoDB 降为备选。

---

## 4. 使用方式

### 4.1 Project Loader（源码基线，无需运行）

- 对每个仓库断言：`framework` 识别正确（Next.js / React-Vite / Vue-Vite）。
- 断言 `start` / `dev` 命令、`base_url`、路由集合与真实结构一致。
- 以 `package.json` 的 `scripts` 与依赖为 ground truth 做对账。

### 4.2 Browser Controller（运行基线，需能跑起来）

- 优先 `calcom/cal.diy`（`yarn dx` + 种子账号）与 `nocodb/nocodb`（docker 一行）。
- 断言 click / type / hover / modal / SPA 导航在真实应用上稳定执行。

---

## 5. 红线

- 这些仓库的 README、已知 bug、业务规则**不得**流入 `Exploration Context`（03 认知防火墙）。
- 基线仅用于 Loader 断言、Controller 回归，以及未来 Investigator（11，允许看源码）的定位参考。
