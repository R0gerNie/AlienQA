"""Bounded runtime event records, with legacy string views."""
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_PRIVATE_QUERY = re.compile(r"token|password|passwd|secret|key|session|auth|cookie|signature|^code$", re.I)
_URL = re.compile(r"https?://[^\s<>\"']+")


def sanitize_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        host = parts.netloc.rsplit("@", 1)[-1]
        query = urlencode([(key, "[redacted]" if _PRIVATE_QUERY.search(key) else value)
                           for key, value in parse_qsl(parts.query, keep_blank_values=True)])
        return urlunsplit((parts.scheme, host, parts.path, query, ""))
    except ValueError:
        return "[invalid URL]"


def clean_message(message: str) -> str:
    text = _URL.sub(lambda match: sanitize_url(match.group()), message)
    return re.sub(r"(?i)\b(password|token|secret|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+",
                  r"\1=[redacted]", text)


@dataclass
class RuntimeSignals:
    console_errors: list = field(default_factory=list)
    page_errors: list = field(default_factory=list)
    network_failures: list = field(default_factory=list)
    http_errors: list = field(default_factory=list)
    records: list[dict] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    step_id: str | None = None
    action_id: str | None = None
    phase: str = "entry"
    cursor: int = 0
    dropped_count: int = 0
    max_records: int = 2000
    max_text_bytes: int = 4096
    retained_count: int = 0

    def record(self, kind: str, payload: dict) -> None:
        self.cursor += 1
        if self.retained_count >= self.max_records:
            self.dropped_count += 1
            return
        cleaned = {}
        truncated = False
        for key, value in payload.items():
            if isinstance(value, str):
                value = sanitize_url(value) if key == "url" else clean_message(value)
                raw = value.encode("utf-8")
                truncated |= len(raw) > self.max_text_bytes
                value = raw[:self.max_text_bytes].decode("utf-8", errors="ignore")
            cleaned[key] = value
        event = {"record_id": f"{self.run_id}:R-{self.cursor:06d}", "sequence": self.cursor,
                 "run_id": self.run_id, "step_id": self.step_id, "action_id": self.action_id,
                 "phase": self.phase, "timestamp": datetime.now(timezone.utc).isoformat(),
                 "kind": kind, "payload": cleaned, "payload_truncated": truncated}
        self.records.append(event)
        self.retained_count += 1
        message = cleaned.get("message", "")
        if kind == "page_error":
            self.page_errors.append(message)
        elif kind == "console_error":
            self.console_errors.append(message)
        elif kind == "request_failed":
            self.network_failures.append(f"{cleaned.get('method', '')} {cleaned.get('url', '')} -> {message}")
        elif kind == "http_response" and cleaned.get("status", 0) >= 400:
            self.http_errors.append(f"{cleaned.get('method', '')} {cleaned.get('url', '')} -> {cleaned['status']}")

    def clear(self) -> None:
        """Drop views without resetting the run budget or reusing event identities."""
        for name in ("console_errors", "page_errors", "network_failures", "http_errors", "records"):
            getattr(self, name).clear()
