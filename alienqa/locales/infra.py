"""English messages for model transport, loader, actions, and replay."""

MESSAGES = {'未知 action 类型: {type}': 'Unknown action type: {type}',
 '坐标兜底不支持 action 类型: {type}': 'Coordinate fallback does not support action type: {type}',
 '计量保存失败：{error}': 'Could not save usage accounting: {error}',
 "未配置 LLM 角色 '{role}' 的模型": "No model is configured for LLM role '{role}'",
 '供应商响应缺少 choices': 'The provider response has no choices',
 '供应商响应缺少有效 content': 'The provider response has no valid content',
 'LLM 调用全部失败 (models={models}): {error}': 'All LLM calls failed (models={models}): {error}',
 '部署子路径必须是字符串': 'The deployment base path must be a string',
 '部署子路径必须是站内绝对路径，例如 /tool/': 'The deployment base path must be an absolute path on this site, such as /tool/',
 'action 需要 dict，收到 {type}': 'action must be a dictionary; received {type}',
 '无文案 {role}': 'Unlabeled {role}',
 '控件': 'control',
 '（页面位置 x={x}, y={y}）': ' (page position x={x}, y={y})',
 '，可展开 {popup}': ', opens {popup}',
 '当前控件': 'current control',
 '未安装 Codex CLI；请安装并运行 codex login': 'Codex CLI is not installed; install it and run codex login',
 'Codex reasoning_effort 必须是 minimal/low/medium/high/xhigh': 'Codex reasoning_effort must be '
                                                             'minimal/low/medium/high/xhigh',
 'Codex 需要 ChatGPT 登录；请先运行 codex login，不自动改用 API key': 'Codex requires a ChatGPT login; run codex login first. API key '
                                                       'authentication is not used automatically',
 '缺少有效 Codex 模型名': 'A valid Codex model name is required',
 'Codex 调用超时；本地进程已回收，供应商是否完成及费用未知': 'The Codex call timed out; the local process was stopped. Provider completion and '
                                    'cost are unknown',
 'Codex CLI 失败（exit={code}）：{error}': 'Codex CLI failed (exit={code}): {error}',
 'Codex 仅支持文本和内联图像消息': 'Codex supports only text and inline image messages',
 'Codex 图像必须由本地图片编码，不下载外部图像 URL': 'Codex images must be encoded from local images; external image URLs are not '
                                  'downloaded',
 'Codex 消息包含不支持的内容类型': 'The Codex message contains an unsupported content type',
 'Codex 返回非 JSONL 事件': 'Codex returned an event that is not JSONL',
 'Codex 返回无效事件': 'Codex returned an invalid event',
 'Codex 返回多个推理 turn，无法作为单次调用计量': 'Codex returned multiple reasoning turns; they cannot be accounted for as one call',
 '未知错误': 'Unknown error',
 'Codex 调用失败：{error}': 'The Codex call failed: {error}',
 'Codex 推理错误：{error}': 'Codex reasoning failed: {error}',
 'Codex 返回未允许的 item 类型 {type}；当前适配仅允许直接文本/图像推理': 'Codex returned an unsupported item type {type}; this adapter permits '
                                                 'only direct text/image reasoning',
 'Codex 缺少完成事件或有效最终回复': 'Codex did not return a completion event or a valid final response',
 '仅有动作/时间预算；费用缺失与未完成请求为未知，停止本地任务不保证供应商停止计费。': 'Only action and time budgets are enforced. Missing costs and unfinished '
                                              'requests remain unknown; stopping the local task does not guarantee '
                                              'that provider billing stops.',
 ' Codex attempts 计数为 CLI 启动次数，未直接观察供应商 HTTP 请求；订阅额度消耗不等于零费用。': ' Codex attempts count CLI invocations, not directly '
                                                                'observed provider HTTP requests. Subscription usage '
                                                                'does not imply zero cost.',
 '画面接近与技术信号再次出现均不证明认知解释或根因；开发者决定不受回放影响': 'Similar screenshots and recurring technical signals do not prove a cognitive '
                                         'interpretation or root cause; replay does not change developer decisions',
 '仅恢复 cookies/localStorage；sessionStorage、IndexedDB、自动登录和外部业务数据不恢复': 'Only cookies/localStorage are restored; '
                                                                     'sessionStorage, IndexedDB, automatic login, and '
                                                                     'external business data are not restored',
 '旧包没有独立目标窗口；按最后一个成功动作观察，来源完整性未知': 'The legacy package has no independent target window; observation follows the last '
                                   'successful action, and source completeness is unknown',
 '旧 driver 会话快照时间未知，不能证明是原初始会话': 'The legacy driver session snapshot time is unknown; it cannot be verified as the '
                                 'original initial session',
 '回放包缺少初始 URL': 'The replay package has no initial URL',
 '动作发出结果不确定，无法证明成功前缀恢复了原前置条件': 'The action outcome is uncertain; the successful prefix cannot be verified to have '
                               'restored the original prerequisites',
 '回放包缺少可核对的目标阶段': 'The replay package has no verifiable target phase',
 '回放包缺少目标动作': 'The replay package has no target action',
 '静态回放服务目录不存在或端口无效': 'The static replay service directory is missing or the port is invalid',
 '入口观察窗口未稳定或读取失败': 'The entry observation window did not settle or could not be read',
 '实际浏览器与记录不同（可能触发默认浏览器回退），同环境前提未恢复': 'The actual browser differs from the recorded browser, possibly after a fallback; '
                                     'the original environment was not restored',
 '实际视口与记录不同，同环境前提未恢复': 'The actual viewport differs from the recorded viewport; the original environment was not '
                       'restored',
 '浏览器版本与记录不同；使用本机现有版本，未安装原版本': 'The browser version differs from the recording; the installed local version is used, '
                               'and the original version was not installed',
 '注入 driver 的浏览器/视口由调用者负责，未由 ReplayEngine 验证': 'The caller is responsible for the injected driver browser/viewport; '
                                               'ReplayEngine has not verified it',
 '入口重定向与记录不同，认证可能过期或环境已改变': 'The entry redirect differs from the recording; authentication may have expired or the '
                            'environment may have changed',
 '回放动作已发出，观察窗口未稳定或读取失败': 'The replay action was issued, but the observation window did not settle or could not be read',
 '背景观察窗口未稳定或读取失败': 'The background observation window did not settle or could not be read',
 '背景窗口只观察重放后的短时事件，原后台计时和外部数据未恢复': 'The background window observes only short events after replay; original background '
                                  'timing and external data were not restored',
 '截图读取失败：': 'Could not read the screenshot: ',
 '入口 / 未记录': 'entry / unrecorded',
 '{phase} 阶段失败（步骤 {step}）：{error}': '{phase} phase failed (step {step}): {error}',
 '只表示画面接近，原认知预期需人工复核': 'This indicates only visual similarity; the original cognitive expectation requires human '
                       'review',
 '目标窗口的具体技术事实再次出现': 'The specific technical facts recurred in the target window',
 '画面/观察再次出现；原认知预期需人工复核': 'The visual result/observation recurred; the original cognitive expectation requires human '
                         'review',
 '观察窗口有缺失或截断，无法验证': 'The observation window has missing or truncated data and cannot be verified',
 '回放终点与记录不同，前提可能已改变': 'The replay endpoint differs from the recording; prerequisites may have changed',
 '目标窗口未再现原记录的具体事实/画面': 'The specific recorded facts/visual result did not recur in the target window',
 '缺少可比较截图或具体来源事实，无法验证': 'Comparable screenshots or specific source facts are missing; the result cannot be verified',
 '回放包不存在: {path}': 'The replay package does not exist: {path}',
 '回放包必须为对象': 'The replay package must be an object',
 '回放包 {key} 必须为对象': 'Replay package {key} must be an object',
 '不支持的回放包版本：{version}': 'Unsupported replay package version: {version}',
 '无效的证据 ID': 'Invalid evidence ID',
 '回放浏览器类型不受支持': 'Unsupported replay browser type',
 '应用 manifest 必须是项目内部存在的 package.json': 'The application manifest must be an existing package.json within the project',
 '所选 manifest 未被识别为前端应用': 'The selected manifest was not recognized as a frontend application',
 'L0 目前仅支持本地目录/zip/url 识别，docker/CI 待实现': 'L0 currently recognizes only local directories, ZIP files, and URLs; '
                                          'Docker/CI support is not implemented',
 '输入不存在: {source}': 'The input does not exist: {source}',
 'L0 目前仅支持目录/zip 输入，docker/url/CI 待实现': 'L0 currently accepts only directory/ZIP inputs; Docker/URL/CI support is not '
                                        'implemented',
 'entry 不在候选清单': 'entry is not in the candidate list',
 '未找到可运行的 HTML 入口，请提供项目运行 URL': 'No runnable HTML entry was found; provide the running application URL',
 'HTML 引用未构建源码，请先启动项目并填写运行 URL': 'The HTML references unbuilt source code; start the application and provide its '
                                 'running URL',
 '静态资源不在部署前缀 {base_path} 内：{path}': 'The static resource is outside deployment prefix {base_path}: {path}',
 '静态 HTML 所需资源缺失：{path}；请提供完整产物或运行 URL': 'A required static HTML resource is missing: {path}; provide a complete build '
                                         'or a running URL',
 '框架源码/服务型产物需要先启动项目并填写运行 URL，或提供完整 dist/build/out 静态产物': 'Framework source/service builds require a running '
                                                         'application URL or a complete static dist/build/out build',
 '没有可直接运行的静态 HTML；请填写项目运行 URL': 'No directly runnable static HTML was found; provide the running application URL',
 '请在浏览器里完成登录，然后回到终端按回车保存会话 → {path}\n': 'Complete login in the browser, then return to the terminal and press Enter to '
                                        'save the session → {path}\n'}
