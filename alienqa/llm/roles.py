"""三角色 prompt 模板：为 02 Product Mapper / 08 Expectation Engine 提供 LLM 能力。"""
from .client import LLMClient
from .models import Role


def _format_technical(technical: dict) -> str:
    """把运行时技术信号格式化成可读文本（截断列表长度，跳过空值）。"""
    if not technical:
        return "无"
    lines = []
    for key, value in technical.items():
        if isinstance(value, list):
            if not value:
                continue
            value = "; ".join(str(x) for x in value[:10])
        elif value in (None, "", {}, []):
            continue
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _clean_expectation(line: str) -> str:
    """清洗预期行：去 markdown 加粗/列表标记/编号，过滤空壳行。"""
    import re

    line = (line or "").strip()
    if not line:
        return ""
    line = re.sub(r"^\s*\*{1,2}\s*", "", line)
    line = re.sub(r"^\s*(?:\d+[.)、]|[-•·])\s*", "", line)
    line = line.strip(" *•·").strip()
    return line if len(line) >= 2 else ""


class LlmRoles:
    def __init__(self, client: LLMClient):
        self.client = client

    # A 主旨加载（低温度）：给 02
    def summarize_gist(self, readme: str, surface_summary: str) -> str:
        prompt = (
            "你是产品观察员。阅读以下 README 和前端页面结构，用 3~5 句话总结："
            "这个应用是做什么的、面向谁、核心功能有哪些。\n"
            "只总结主旨，不要推断实现细节、技术栈或代码结构。\n\n"
            f"README:\n{readme[:4000]}\n\n前端结构:\n{surface_summary[:4000]}"
        )
        return self.client.complete(Role.GIST, [{"role": "user", "content": prompt}]).text

    # A2 产品地图结构化提取（低温度，复用 GIST）：给 02
    def map_product(self, gist: str, surface_text: str, repair: bool = False) -> str:
        prompt = (
            "你是产品观察员。根据下面的产品主旨与前端表面结构，画一张'产品地图'。\n"
            "只概括这个产品有哪些功能区域；绝对不要判断它好不好、有没有 bug，"
            "不要输出任何'疑似问题/测试结论/改进建议'字段。\n"
            "严格输出一个 JSON 对象（不要 markdown 围栏、不要多余文字），结构如下：\n"
            '{"areas":[{"name":"区域名","pages":["/path"],"actions":["动作"],'
            '"entities":["实体"],"roles":["角色"],"states":["状态"]}],'
            '"relations":[{"from":"/a","to":"/b","kind":"navigate"}]}\n\n'
            f"产品主旨:\n{gist[:3000]}\n\n前端表面结构:\n{surface_text[:8000]}"
        )
        if repair:
            prompt += "\n\n注意：你上一次的输出不是合法 JSON。这次只输出一个合法 JSON 对象。"
        return self.client.complete(Role.GIST, [{"role": "user", "content": prompt}]).text

    # B 预期生成（高温度，采样取并集）：给 08
    def generate_expectations(self, gist: str, page_text: str, samples: int = 2, focus: str = "") -> list:
        intro = (
            "你是一名第一次打开这个产品、从未受过任何培训的普通用户。"
            "你只看到产品简介和当前界面可见文字。\n"
        )
        if focus:
            intro += (
                f"本次你的任务被限定在一个具体单元上：\n【单元与指令】\n{focus}\n\n"
                "请只围绕这个单元——它内部的可见按钮/输入框/链接/提示，"
                "按最朴素的直觉输出你预期会发生什么，以及'好像少了点什么'。\n"
            )
        else:
            intro += (
                "请用最朴素的直觉，直接输出一个简洁列表：每个可见按钮/输入框/链接，"
                "你自然而然会预期它点了之后发生什么；以及哪些地方让你觉得'好像少了点什么'。\n"
            )
        prompt = (
            intro
            + "每条预期一行，不要小标题、不要 markdown 加粗、不要编号、不要解释。\n\n"
            f"产品简介:\n{gist}\n\n当前界面文字:\n{page_text[:4000]}"
        )
        results = set()
        for _ in range(max(1, samples)):
            resp = self.client.complete(Role.EXPECTATION, [{"role": "user", "content": prompt}])
            for line in resp.text.splitlines():
                line = _clean_expectation(line)
                if line:
                    results.add(line)
        return sorted(results)

    # C 盲判（低温度，视觉，结构化输出）：给 08
    def judge(self, action_desc: str, expected: str, before_image, after_image,
              technical: dict | None = None, repair: bool = False) -> str:
        text = (
            f"你刚刚对界面执行了操作：{action_desc}。\n"
            "第一张图是执行前，第二张图是执行后。\n"
            "作为一个普通用户，你原本预期会发生下面这些事：\n"
            f"{expected}\n"
            "请逐条盲判：每条预期，实际结果是否符合？\n"
            "把所有'不符合'的条目都列出来（一条都不要漏）；如果全部符合，输出空列表。\n"
            "只输出一个 JSON 对象（不要 markdown、不要多余文字）：\n"
            '{"mismatches": [{"expectation": "哪条预期没被满足", "observation": "实际看到什么", '
            '"level": "high|medium|low", "reasoning": "一个普通用户为什么会这么想"}]}\n'
            "特别提醒：如果某个东西'看起来像按钮/可点击'，但你判断它点击后毫无反应"
            "（哪怕它可能本来就不是按钮），这也算一条不符合预期，要列进 mismatches。\n"
            "只看图，不要为产品找借口；不要用 'bug' 这个词定性，不要引用 PRD 或实现细节。"
        )
        if technical:
            text += ("\n\n运行时技术信号（仅作旁证，不要据此改变'普通用户直觉'）:\n"
                     + _format_technical(technical))
        if repair:
            text += "\n\n注意：你上一次的输出不是合法 JSON。这次只输出一个合法 JSON 对象。"
        return self.client.complete_vision(Role.JUDGE, text, [before_image, after_image]).text

    # D 视觉观察（低温度，视觉，结构化输出）：给 07
    def observe_visual(self, before_image, after_image, action_desc: str) -> str:
        text = (
            f"你刚刚对界面执行了操作：{action_desc}。\n"
            "第一张图是执行前，第二张图是执行后。\n"
            "请客观描述两张图之间的视觉变化：只描述'人眼看到什么'，"
            "不要评判好坏、不要猜测原因、不要定性 bug。\n"
            "严格输出一个 JSON 对象（不要 markdown、不要多余文字）：\n"
            '{"changes": ["从标签里选"], "summary": "一句话描述变化"}\n'
            "changes 只从这些标签里选：modal_opened / modal_closed / text_changed / "
            "loading_persisted / button_state_changed / page_body_disappeared / "
            "blank_screen / navigation / no_change / other"
        )
        return self.client.complete_vision(Role.VISUAL, text, [before_image, after_image]).text

    # E 专家调查（低温度，可看源码，结构化输出）：给 11
    def investigate(self, expert_context: str, repair: bool = False) -> str:
        text = (
            "你是资深前端调试专家。现在允许你查看源码、DOM、控制台、网络、堆栈等技术信号，"
            "来定位一个已经由'陌生人用户'发现的问题。\n"
            "请给出：1) 根因假设（root cause hypothesis）；2) 可执行的复现步骤；"
            "3) 技术证据；4) 受影响的组件。\n"
            "严格输出一个 JSON 对象（不要 markdown、不要多余文字）：\n"
            '{"root_cause_hypothesis": "…", "reproduction_steps": ["1. …"], '
            '"technical_evidence": {"stack_trace": "…", "api": "…", "component": "…"}, '
            '"affected_components": ["…"]}\n\n'
            f"专家上下文:\n{expert_context[:12000]}"
        )
        if repair:
            text += "\n\n注意：你上一次的输出不是合法 JSON。这次只输出一个合法 JSON 对象。"
        return self.client.complete(Role.INVESTIGATOR, [{"role": "user", "content": text}]).text

    # F 报告编排（可配置，生成 HTML 片段）：给 12
    def compose_report(self, evidence_json: str) -> str:
        text = (
            "你是资深测试报告撰写人。下面是一批已被人工采信的疑似问题证据（JSON）。\n"
            "请把所有证据编排成一份**给人类开发者看的 HTML 报告**（只需 <body> 内的 HTML 片段，"
            "不要 <html>/<head>，不要 markdown 代码块）。\n"
            "报告必须包含：\n"
            "1. 顶部：标题 + 环境信息（url/browser）+ 证据总数；\n"
            "2. 每个证据一个区块：严重度、预期、实际、**可执行的复现步骤**（指导开发者复现）、"
            "console/network 技术信号、根因假设；\n"
            "3. 用语义化 HTML（h1/h2/table/ul/ol/code），样式简洁可读。\n\n"
            f"证据数据:\n{evidence_json[:16000]}"
        )
        return self.client.complete(Role.REPORTER, [{"role": "user", "content": text}]).text
