# T02 真实框架机制样例

这里版本化的是项目自编的最小样例源码、manifest 和精确锁文件。第三方包、源码副本、缓存、构建与运行数据只能进入项目内已忽略的 `examples/open-source/t02-frameworks/`、`artifacts/evaluation/t02-frameworks/`。

显式准备与运行：

```sh
.venv/bin/python scripts/prepare_t02_frameworks.py --install
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  tests/test_t02_frameworks.py --run-frameworks \
  --junitxml=artifacts/evaluation/t02-frameworks/junit.xml
```

准备脚本固定工作区，使用 `npm ci`；普通扫描与默认 pytest 不安装 Node 依赖、不启动框架服务。默认套件不收集此显式兼容套件。已安装依赖后可以不带 `--install` 重新构建。

每条路径从新浏览器上下文恢复，应用数据不依赖外部数据库。人工顺序动作、有限 planner 路径、生产管线的模型替身路径分别验证；正常/缺反馈对照的标签只在评估端使用。这些结果不代表真实模型效果。

T05 复用相同版本并新增四条表单→提交→客户端导航→异常的独立回放路径；触发异常的按钮在固定页面中提供，不向真实模型添加正确答案。T05 结果位于项目内忽略的 `artifacts/evaluation/t05-frameworks/`；运行 `tests/test_t02_frameworks.py --run-frameworks -k t05` 可单独核对。见 [T05 实施记录](../../../docs/engineering/t05-implementation.md)。

实际验证范围和限制见 [T02 实施记录](../../../docs/engineering/t02-implementation.md)。

## T01 源码/产物/部署增量

`next-src/` 是自编的 src、route group 与动态 App/Pages 补充；精确依赖和锁文件复用上述 Next fixture。`scripts/prepare_t01_frameworks.py` 将源文件派生到项目内忽略的 `examples/open-source/t01-frameworks/apps/web`，只构建、不安装，依赖链接指向同项目 T02 工作区。该配方包含 Turbopack root 设置，不是任意目录模板。

`deployment/` 是自编静态 SPA，用于 `/tool/` 挂载、query/hash、history 刷新、API/缺资源 404 与停止原服务后的独立回放。结构边界 fixture 在 `test_t01_loader.py` 中按测试生成，均非外部开源仓库。

```sh
.venv/bin/python scripts/prepare_t01_frameworks.py
PLAYWRIGHT_BROWSERS_PATH=.venv/browsers .venv/bin/python -m pytest \
  tests/test_t01_frameworks.py --run-frameworks
```

T01 包含 4 条实际框架增量路径；其中 Vite fixture 同时依赖 React/Vue、识别为 Vue，分别以 react.html/vue.html 验证两个 renderer 的产物服务。Router 包变体没有单独运行认证。默认另含 2 条自包含部署浏览器路径。详见 [T01 实施记录](../../../docs/engineering/t01-implementation.md)。
