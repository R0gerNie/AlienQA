"""English runtime messages; page text and saved evidence remain verbatim."""

MESSAGES = {'动作数、采样次数及时间预算必须大于零': 'Action count, samples and time budget must be greater than zero',
 '结果目录已有扫描，请为新 run 使用新的目录': 'The results directory already contains a scan; use a new directory for a new '
                            'run',
 '单元：{unit}': 'Unit: {unit}',
 '指令：{instructions}': 'Instructions: {instructions}',
 '[02b] 读取浏览器可见文字…': '[02b] Reading visible browser text…',
 '[02b] 页面无可见文字，返回空 ProductMap': '[02b] No visible page text; returning an empty ProductMap',
 'CLI 自动采信': 'Automatically confirmed by CLI',
 '[12] 证据待人工审核；未生成正式报告': '[12] Evidence awaits human review; no final report generated',
 '[12] 生成 HTML 报告中…': '[12] Generating HTML report…',
 '未定位到指定单元，未扩大为全量扫描': 'The requested unit could not be located; the scan was not expanded to the whole '
                      'application',
 '部分输入约束无法构造合法样本，相关提交路径未验证': 'Some input constraints prevent a valid sample; the associated submission paths '
                             'remain unverified',
 '可交互控件枚举已截断，剩余区域未检查': 'Interactive control enumeration was truncated; the remaining areas were not checked',
 'frame 内容未访问，不计为已覆盖': 'Frame content was not visited and is not counted as covered',
 'shadow 内容的枚举、状态与回放尚未验证': 'Shadow content enumeration, state and replay remain unverified',
 '多个可见 modal 无法确定活动层，未继续操作': 'The active layer among multiple visible modals could not be determined; no '
                             'further action was taken',
 '部分控件已消失或无法读取，覆盖不完整': 'Some controls disappeared or could not be read; coverage is incomplete',
 '可见 modal 中没有可识别的操作控件，未继续操作背景': 'No recognizable action controls exist in the visible modal; the background '
                                 'was not operated',
 '未执行任何可交互动作，无法判断交互质量': 'No interactive actions were executed; interaction quality cannot be assessed',
 '未形成可检查的事前预期，认知检查未完成': 'No checkable pre-action expectations were formed; the cognitive check is incomplete',
 '事前预期缺少有效依据，认知检查未完成': 'Pre-action expectations lack a valid basis; the cognitive check is incomplete',
 '动作前运行时间预算耗尽': 'The run time budget was exhausted before the action',
 '观察材料缺失': 'Observation material is missing',
 '填值未被控件接受或无法验证，未将后续提交视为成功': 'The control rejected the input or its acceptance could not be verified; '
                             'subsequent submission was not treated as successful',
 '动作已发出，观察窗口未稳定或读取失败，认知结果未判断': 'The action was emitted, but the observation window did not settle or could '
                               'not be read; the cognitive result was not judged',
 '已检查要求存在落差，另有采样要求未决，认知检查不完整': 'Checked requirements show a mismatch, while other sampled requirements '
                               'remain unresolved; the cognitive check is incomplete',
 '已检查要求满足，但仍有采样要求未决，认知检查不完整': 'Checked requirements are satisfied, but sampled requirements remain '
                              'unresolved; the cognitive check is incomplete',
 '非空 expectations 不能同时包含 abstention': 'Nonempty expectations cannot also contain abstention',
 'abstention 必须包含有效 code 和 1～500 字符 reason': 'abstention must contain a valid code and a reason of 1–500 '
                                             'characters',
 'expectations 必须是最多 5 条的数组': 'expectations must be an array of at most 5 items',
 '原文一致或有限规则证明等价；支持数不表示正确率': 'Original wording matches or bounded rules establish equivalence; support count '
                            'does not represent accuracy',
 '合并后的预期超过 5 条上限': 'Merged expectations exceed the limit of 5',
 '预期文本必须为字符串': 'Expectation text must be a string',
 '预期文本或依据无效/超出 500 字符上限': 'Expectation text or basis is invalid or exceeds the 500-character limit',
 '依据只能包含 type/reference': 'The basis may contain only type/reference',
 'visible_copy 必须原样引用当前已保存的可见文案/控件': 'visible_copy must quote the current saved visible text or control '
                                     'verbatim',
 '单份采样超过 5 条上限': 'A single sample exceeds the limit of 5 expectations',
 '采样要求互相排斥，均保留检查': 'Sampled requirements conflict; all are retained for checking',
 '要求关系未知，均保留检查': 'The relationship between requirements is unknown; all are retained for checking',
 'observed_behavior 必须引用前序已提交步骤及其可见结果原文': 'observed_behavior must reference a prior committed step and quote '
                                          'its visible result verbatim',
 '合并候选超过上限，未交付预期集合': 'Merged candidates exceed the limit; no expectation set was delivered',
 '相同动作的反馈要求互相排斥，需复核': 'Feedback requirements for the same action conflict and require review',
 '要求之间的关系超出有限规则，需复核': 'The relationship between requirements exceeds bounded rules and requires review',
 '没有可验证的本次动作预期': 'There are no verifiable expectations for this action',
 '缺少动作后的观察': 'The post-action observation is missing',
 '缺少执行前或执行后的截图，无法进行盲判': 'A before or after screenshot is missing; blind judgment cannot be performed',
 '观察没有动作描述，无法确认预期与动作的绑定': 'The observation has no action description; the expectation-to-action binding '
                          'cannot be confirmed',
 '预期与当前观察绑定的动作不一致': 'The expectations and current observation are bound to different actions',
 '事前预期身份缺失或重复': 'Pre-action expectation identities are missing or duplicated',
 '判定输出引用了本次动作未提供的预期': 'The judgment references an expectation not provided for this action',
 '判定输出的 expectation_id/text 不属于事前集合': 'The judgment expectation_id/text does not belong to the pre-action '
                                      'set',
 '判定输出重复引用同一预期': 'The judgment references the same expectation more than once',
 '无法判断的预期 ID 未提供或同时出现在 mismatch': 'An unverifiable expectation ID was not provided or also appears in '
                                  'mismatch',
 '事前预期缺失或已被修改': 'A pre-action expectation is missing or has been modified',
 '预期与观察的 run/step/action 不一致': 'The expectation and observation have different run/step/action identities',
 '判定输出必须包含 mismatches 列表': 'The judgment output must contain a mismatches list',
 'unverifiable_expectation_ids 必须是无重复的预期 ID 数组': 'unverifiable_expectation_ids must be an array of unique '
                                                 'expectation IDs',
 '判定 status 无效': 'The judgment status is invalid',
 'failed/inconclusive 不能同时包含 mismatch': 'failed/inconclusive cannot also contain mismatches',
 'failed/inconclusive 必须提供非空 error 原因': 'failed/inconclusive must provide a nonempty error reason',
 'mismatches 的每项必须为对象': 'Every item in mismatches must be an object',
 'mismatch.level 必须为 high、medium 或 low': 'mismatch.level must be high, medium or low',
 '判定 status 与 mismatches 不一致': 'The judgment status and mismatches are inconsistent',
 '存在无法判断的预期不能 passed': 'The judgment cannot be passed when expectations remain unverifiable',
 '无法判断的预期必须提供 error 原因': 'Unverifiable expectations must provide an error reason',
 'changes 必须为非空字符串组成的列表': 'changes must be a list of nonempty strings',
 'summary 必须为字符串': 'summary must be a string',
 '缺少 areas 列表；空地图需显式提供 areas: []': 'The areas list is missing; an empty map must explicitly provide areas: '
                                   '[]',
 '新认知 Evidence 必须引用事前 expectation_id': 'New cognitive Evidence must reference a pre-action expectation_id',
 '认知 Evidence 的事前预期身份不匹配': 'The cognitive Evidence pre-action expectation identity does not match',
 '浏览器原始异常候选；影响和可接受性需人工核对': 'Raw browser anomaly candidate; impact and acceptability require human review',
 '未命名问题': 'Untitled finding',
 '相同页面、动作和具体技术事实': 'Same page, action and specific technical facts',
 '相同原预期、依据和动作的组织候选': 'Grouping candidate with the same original expectation, basis and action',
 '独立证据': 'Independent evidence',
 '旧记录相似度组织候选；未证明共同根因': 'Grouping candidate based on legacy record similarity; a shared root cause has not '
                       'been established',
 '保存事实': 'Saved facts',
 '动作轨迹': 'Action trace',
 '控制台': 'Console',
 '网络': 'Network',
 '堆栈': 'Stack trace',
 '源码': 'Source code',
 '[调查边界]\n根因和代码位置仅为假设；缺失、未执行与未知不能写成已发生。输入总限 11500 字符，分段有界；截断部分不作为已读取内容。\n': '[Investigation boundaries]\n'
                                                                            'Root causes and code locations '
                                                                            'are hypotheses only; missing, '
                                                                            'unexecuted and unknown facts '
                                                                            'must not be presented as '
                                                                            'observed. Input is limited to '
                                                                            '11,500 characters with bounded '
                                                                            'sections; truncated content has '
                                                                            'not been read.\n',
 '\n[截断：其余内容未送入模型]': '\n[Truncated: remaining content was not sent to the model]',
 '调查输出缺少根因假设（无法确定时请明确说明）': 'The investigation output lacks a root cause hypothesis (explicitly state when it '
                           'cannot be determined)',
 '（截断：只取前 500 字符）': '(truncated: first 500 characters only)',
 '（完整小片段）': '(complete short snippet)',
 '检索限制：所选应用根目录内最多 20 文件，每文件 500 字符，总计 12000 字符；路径/关键词或角色回退，不证明覆盖全部源码。\n': 'Retrieval limits: at most 20 '
                                                                          'files within the selected '
                                                                          'application root, 500 characters '
                                                                          'per file and 12,000 characters '
                                                                          'total; path/keyword selection or '
                                                                          'role fallback does not establish '
                                                                          'full source coverage.\n',
 '仅提供保存路径与缺失状态；本调查文本通道不读取图片像素': 'Only saved paths and missing status are provided; this investigation text '
                                'channel does not read image pixels',
 '所选应用文件片段；不含 source map、组件树或服务端追踪': 'Selected application file snippets; no source maps, component trees or '
                                     'server traces',
 ' 输入值保留在本机回放包': ' Input values are retained in the local replay bundle',
 '\n[截断：保存快照输入共限 5000 字符]': '\n[Truncated: saved snapshot input is limited to 5,000 characters total]',
 '可见约束不支持 JSON 样本，未绕过约束': 'The visible constraints do not support a JSON sample; the constraints were not '
                          'bypassed',
 '无法根据可见输入约束构造合法样本，未提交该字段': 'A valid sample could not be formed from visible input constraints; the field '
                            'was not submitted',
 '路由:\n': 'Routes:\n',
 '入口文件:\n': 'Entry files:\n',
 '可见前端文件片段:\n': 'Visible frontend file snippets:\n',
 '未找到 JSON 对象': 'No JSON object was found',
 'JSON 顶层不是对象': 'The JSON top level is not an object',
 '原始事件超过上限，丢弃 {count} 条': 'Raw events exceeded the limit; {count} events were dropped',
 '[02b] 主旨: {brief}': '[02b] Product brief: {brief}',
 '[02b] 功能区域: {count} 个': '[02b] Functional areas: {count}',
 '[12] 报告已写入 {path}（采信 {accepted}/{total}）': '[12] Report written to {path} (confirmed {accepted}/{total})',
 '预期生成失败：{error}': 'Expectation generation failed: {error}',
 '判定模型调用失败: {error}': 'Judgment model invocation failed: {error}',
 '判定输出在修复后仍无效: {error}': 'Judgment output remains invalid after repair: {error}',
 'mismatch.{key} 必须为非空字符串': 'mismatch.{key} must be a nonempty string',
 '视觉观察输出无效: {error}': 'Invalid visual observation output: {error}',
 '{field} 必须为对象组成的列表': '{field} must be a list of objects',
 '产品地图输出在修复后仍无效: {error}': 'Product map output remains invalid after repair: {error}',
 '问题 {id}：{title}': 'Finding {id}: {title}',
 '证据 {id}\n预期：{expectation}\n实际：{observation}\n触发动作：{action}': 'Evidence {id}\n'
                                                               'Expected: {expectation}\n'
                                                               'Observed: {observation}\n'
                                                               'Triggering action: {action}',
 '问题 {id}：{title}\n\n{text}': 'Finding {id}: {title}\n\n{text}',
 '未知 action 类型: {kind}': 'Unknown action type: {kind}',
 '坐标兜底不支持 action 类型: {kind}': 'Coordinate fallback does not support action type: {kind}'}
