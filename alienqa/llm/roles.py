"""三角色 prompt 模板：为 02 Product Mapper / 08 Expectation Engine 提供 LLM 能力。"""
from .client import LLMClient
from .models import Role


def _format_technical(technical: dict) -> str:
    """把运行时技术信号格式化成可读文本（截断列表长度）。"""
    if not technical:
        return "无"
    lines = []
    for key, value in technical.items():
        if isinstance(value, list):
            value = "; ".join(str(x) for x in value[:10])
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


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
    def generate_expectations(self, gist: str, page_text: str, samples: int = 2) -> list:
        prompt = (
            "你是一名第一次打开这个产品、从未受过任何培训的普通用户。"
            "你只看到产品简介和当前界面可见文字。\n"
            "请用最朴素的直觉，列出：1) 这个界面有哪些功能；2) 每个可见按钮/输入框/链接，"
            "你自然而然会预期它点了之后发生什么；3) 哪些地方让你觉得'好像少了点什么'。\n"
            "不要猜测实现技术，不要为产品找解释，就按一个普通人的直觉说。\n\n"
            f"产品简介:\n{gist}\n\n当前界面文字:\n{page_text[:4000]}"
        )
        results = set()
        for _ in range(max(1, samples)):
            resp = self.client.complete(Role.EXPECTATION, [{"role": "user", "content": prompt}])
            for line in resp.text.splitlines():
                line = line.strip(" -•·0123456789. ").strip()
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
            "请盲判：实际结果是否符合这些预期？\n"
            "如果全部符合，只输出：{\"matched\": true}\n"
            "如果有任何一条不符，挑出最严重的一条，只输出一个 JSON 对象（不要 markdown、不要多余文字）：\n"
            '{"matched": false, "expectation": "哪条预期没被满足", "observation": "实际看到什么", '
            '"level": "high|medium|low", "reasoning": "一个普通用户为什么会这么想"}\n'
            "只看图，不要为产品找借口；不要用 'bug' 这个词定性，不要引用 PRD 或实现细节。"
        )
        if technical:
            text += ("\n\n运行时技术信号（仅作旁证，不要据此改变'普通用户直觉'）:\n"
                     + _format_technical(technical))
        if repair:
            text += "\n\n注意：你上一次的输出不是合法 JSON。这次只输出一个合法 JSON 对象。"
        return self.client.complete_vision(Role.JUDGE, text, [before_image, after_image]).text
