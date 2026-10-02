# T07 本地运行、CLI/UI 与生命周期实施记录

日期：2026-10-02。对应 [T07 Planbook](mvp-planbooks/technical/07-local-run-ui-lifecycle.md)。U01～U06 的功能 MVP 已接通，U07 完成本机真实 worker 与安装包路径验收；新环境依赖解析、其他平台及真实应用效果仍由 T09/N06 独立验收。

## 1. 交付与边界

| 任务 | 已实现行为 |
|---|---|
| U01 输入 | `local_run.ScanInput` 供 CLI/UI 共用：HTTP(S) URL、scope、session、浏览器、正整数采样/动作数及有限正数时间预算。UI 默认 URL 模式并传递预算；CLI 增加 `--unit`、`--instructions`、`--app`。多个已识别前端必须选应用目录，路径不得离开项目；单应用可定位到其子目录。CLI/UI 复用静态产物条件，未构建框架源码不能静态运行 |
| U02 本地检查 | 必需 gist/expectation/visual/judge 配置、请求超时、session 条目结构、浏览器存在、输出可写、URL 可达。仅本地检查，不调用模型探测；HTTP 错误页仍是可达目标。实际访问/重定向地址存入 committed snapshot；`authentication=unverified`，不从文件存在推断登录成功。启动命令需源码目录及实际 URL，`shell=False`、选中应用 cwd，退出回收 |
| U03 终态 | 正常退出也检查并回收进程组残留；无法证明退出时 `cleanup_failed` 保留占用，不能手动 release 放行。POSIX worker 响应 TERM 时让同步 provider 的 finally 回收另开进程组的模型子进程，再按需要 KILL。parent 退出后以 matching terminal `scan.json` 核对结果；汇总文件的 done/counts 不决定成功。缺失/非终态提交追加诊断并保留原前缀；重复/迟到回调不改终态 |
| U04 历史 | API/详情/历史读取 committed 工作量：尝试、执行完成、有效认知判定、技术与认知候选、pending 和 confirmed。区分 absent/corrupt/unsupported/available；旧缺字段显示未记录。保存输入预算、应用选择和浏览器；snapshot 增加访问结果、最后工作阶段，取消保留；预期 prompt 版本来自实际输入快照 |
| U05 控制台 | 主路径 URL → 扫描 → 进度/停止/前缀 → 回放/决定/备注 → analysis/confirmed。停止和错误也能进入留存结果；保存成功才确认，失败保留编辑。复用 T06 四种决定、显式双模式和缓存失效规则 |
| U06 CLI | 同样保存 `run.json` 和扫描快照；生产路径不再用二次内存导出覆盖 committed 数据，报告读取已提交行。默认 analysis；显式 confirmed 仍有既有审核门槛。已有运行目录拒绝重扫覆盖；新增 `--review-run DIR` 从终态快照及持久化决定重开审核，不重新扫描。输入/启动/中断/报告失败分别处理，报告 gate 失败不篡改原扫描完整性 |
| U07 本机路径 | 真实 worker、Chromium、HTTP、浏览器操作、独立回放及模型进程替身；覆盖两类候选、停止/超时、重启读历史、保存/重审/双报告和离线 HTML。现有 FakeJobController 控件测试保留，并与真实 worker 验收分开 |

`scan.json` 仍是扫描前缀唯一提交权威。新字段为 schema 2 的可选补充，旧快照不补造访问结果、预算或 prompt 版本。执行完成数不等于业务成功数，认知 mismatch 也计入有效判定；confirmed 只来自开发者明确决定。

## 2. 本机使用

```bash
# URL 主路径；可选定位范围和有界探索预算
python -m alienqa --url http://localhost:3000 --unit '登录表单' \
  --max-actions 10 --max-seconds 300 --artifacts-dir artifacts/my-run --review

# 多应用高级输入：读取/启动 cwd 均为 apps/web
python -m alienqa --project-root /path/to/project --app apps/web \
  --url http://localhost:5173 --start-command 'npm run dev' --review

# 已有运行与备注原地重开，不重新收集事实
python -m alienqa --review-run artifacts/my-run

# 控制台在当前目录读取 runs/；CLI 可主动保存到这个根目录
python -m alienqa --url http://localhost:3000 --artifacts-dir runs/my-run
python -m alienqa --ui
```

控制台探索预算默认 10 次动作、300 秒、2 次预期采样；整任务 watchdog 默认 600 秒。CLI 探索时间在动作边界检查，模型请求另受配置 `request_timeout` 限制，不是任意阻塞的整任务硬 deadline。停止本机任务不保证供应商停止计费，未知账目继续保留。

`--login URL --session-out PATH` 仍通过人工登录保存 cookies/localStorage。会话文件、运行回放包和设置仅供本机私有保管；删除不再使用的会话文件，清理对应 run 及其回放包才能移除副本。sessionStorage/IndexedDB、SSO/验证码和自动续期未实现；实际 URL 显示登录页时，应核对业务页面是否进入。

## 3. 工程验证

本轮所有模型响应来自替身：真实模型/API/正式 Codex CLI 调用 **0 次**。`tests/fixtures/t07-model-provider.py` 为自编离线协议替身，不读取登录凭据。正式六角色路由、计量、子进程执行仍经过实际生产代码。

```bash
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  --run-frameworks --cov=alienqa --cov-report=term \
  --cov-report=json:.venv/t07-coverage.json \
  --junitxml=artifacts/evaluation/t07/junit.xml
.venv/bin/python -m build --no-isolation --outdir .venv/dist/t07
.venv/bin/python scripts/verify_t07_installation.py \
  --wheel .venv/dist/t07/alienqa-0.1.0-py3-none-any.whl
```

最终全量 **649 项通过，覆盖率 87.82%**，较 T05 新增 29 项回归；sdist/wheel 构建和最终 wheel 的独立空目录安装使用路径通过。包含既有 20 条锁版本框架工程路径，另有真实 worker 的完整使用路径、停止/超时模型进程回收、cookies/localStorage 会话与重定向回归。JUnit/运行快照均保存在项目内忽略的 `artifacts/evaluation/t07*/`，覆盖率/完整日志位于 `.venv/t07-coverage.json`、`.venv/t07-tests.log`。

安装验收脚本离线 `pip --no-index --no-deps --target` 安装已构建 wheel，在空工作目录启动新解释器与实际 CLI/UI worker，检查导入来自已安装 `site/alienqa`，模板和配置随包分发。完成扫描、回放、保存决定、双模式导出、独立审核重开和离线图像读取，输出 `summary.json` 及日志。目录全部在项目内 gitignore 的 `artifacts/evaluation/t07-installation/`；运行依赖复用调用该脚本的 Python 环境，没有下载依赖，也没有修改全局环境。最终安装证据位于项目内忽略的 `artifacts/evaluation/t07-installation/c75caeee28d54788aab391d076979668/summary.json`，完整安装验收日志为 `.venv/t07-installation.log`。

## 4. 保留的验收范围

- 本机组合为 macOS ARM64、Python 3.11、Playwright 1.63 与已安装 Chromium/Chrome。Windows taskkill、Ubuntu CI、Firefox/WebKit 未在本轮实跑；仅有代码路径不等于平台兼容已验收。
- 上述安装验证证明包导入及完整使用路径，不证明全新环境可解析全部依赖；新环境依赖安装、版本矩阵及发布仍是 T09 Q05/Q06。
- 应用选择只消费现有 loader 的识别结果。devDependencies/组件库误报、完整 workspace/脚本/路由/SSR 部署识别仍属 T01；本轮没有自动安装或构建外部项目，没有增加后台队列/账号/岗位画像。
- 重启可读取和重审已保存终态。非正常杀死控制台后的 orphan run 不自动恢复执行，也不据此断言外部进程已退出；这类旧 `running` 记录应核对本机进程，不能直接当 done 导出。
- 回放依赖原服务、目录、端口、会话及业务数据。离线 HTML 可留存证据，不能代替这些外部运行前提。
- 模型质量、独立人审和真实小应用 gate 仍开放；控制机制验收不把一般用户预期准确率或产品增长效果标成已验证。
