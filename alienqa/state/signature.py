"""状态签名：route + 去噪可见文本 的哈希。"""
import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

# 去噪规则（噪音 → 稳定占位符）。数字默认保留（counter 自增是有意义的状态变化）。
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?Z?")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_HEX = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_TIME = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")


def normalize(text: str) -> str:
    """Only standalone/labeled clocks are noise; business time feedback stays."""
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        value = line.strip()
        clock = re.sub(r"^(?:clock|current time|当前时间|现在时间)\s*[:：]?\s*", "", value, flags=re.I)
        if _TIMESTAMP.fullmatch(clock) or _TIME.fullmatch(clock):
            value = "<clock>"
        lines.append(value)
    t = " ".join(lines).replace("\t", " ")
    t = _UUID.sub("<id>", t)
    t = _HEX.sub("<id>", t)
    return re.sub(r"\s+", " ", t).strip()


def signature(route: str, text: str, form_state=None) -> str:
    parts = urlsplit(route)
    canonical = urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                           parts.path.rstrip("/") or "/", parts.query, parts.fragment))
    payload = f"{canonical}\x00{normalize(text)}"
    if form_state is not None:
        # Field values contribute only to the digest, never to stored state snapshots.
        payload += "\x00" + json.dumps(form_state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def route_path(route: str) -> str:
    """Compare map paths and browser URLs, preserving meaningful query/hash routes."""
    parts = urlsplit(route)
    return urlunsplit(("", "", parts.path.rstrip("/") or "/", parts.query, parts.fragment))
