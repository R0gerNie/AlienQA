"""三角色 prompt 模板：为 02 Product Mapper / 08 Expectation Engine 提供 LLM 能力。"""
from .client import LLMClient
from .models import Role


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

    # C 盲判（低温度，视觉）：给 08
    def judge(self, action_desc: str, expected: str, before_image, after_image) -> str:
        text = (
            f"你刚刚对界面执行了操作：{action_desc}。\n"
            "第一张图是执行前，第二张图是执行后。\n"
            f"作为一个普通用户，你原本预期会发生：{expected}。\n"
            "请盲判：实际结果是否符合预期？如果不符合，指出哪里不对劲、有多严重"
            "（high/medium/low）、属于哪类问题（技术故障/业务逻辑不清晰/缺少反馈/误导文案/其他）。\n"
            "只看图，不要为产品找借口。"
        )
        return self.client.complete_vision(Role.JUDGE, text, [before_image, after_image]).text
