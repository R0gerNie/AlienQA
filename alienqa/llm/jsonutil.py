"""LLM 输出 JSON 的通用解析辅助：剥围栏、抠对象、loads。"""
import json
import re


def extract_json_object(text: str) -> str:
    """从 LLM 输出里抠出最外层 JSON 对象字符串。失败抛 ValueError。"""
    t = (text or "").strip()
    # 去掉 ```json ... ``` 围栏
    fence = re.match(r"^```[a-zA-Z]*\s*", t)
    if fence:
        t = t[fence.end():]
        t = re.sub(r"\s*```\s*$", "", t)
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("未找到 JSON 对象")
    return t[start:end + 1]


def loads_object(text: str) -> dict:
    """解析 LLM 返回的 JSON 为 dict。失败抛 ValueError / TypeError。"""
    data = json.loads(extract_json_object(text))
    if not isinstance(data, dict):
        raise ValueError("JSON 顶层不是对象")
    return data
