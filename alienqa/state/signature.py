"""状态签名：route + 去噪可见文本 的哈希。"""
import hashlib
import re

# 去噪规则（噪音 → 稳定占位符）。数字默认保留（counter 自增是有意义的状态变化）。
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?Z?")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_HEX = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_TIME = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")


def normalize(text: str) -> str:
    """把文本中的噪音（时间戳/随机 id）替换为稳定占位符，折叠空白。"""
    if not text:
        return ""
    t = text.replace("\n", " ").replace("\t", " ")
    t = _TIMESTAMP.sub("<ts>", t)
    t = _UUID.sub("<id>", t)
    t = _HEX.sub("<id>", t)
    t = _TIME.sub("<time>", t)
    return re.sub(r"\s+", " ", t).strip()


def signature(route: str, text: str) -> str:
    payload = f"{route}\x00{normalize(text)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
