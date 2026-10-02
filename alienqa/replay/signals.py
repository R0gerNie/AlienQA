"""Deterministic fact identities shared by replay and grouping (no model judge)."""
from ..driver.runtime import clean_message, sanitize_url


def signal_key(record):
    if not isinstance(record, dict) or record.get("payload_truncated"):
        return None
    payload = record.get("payload") or {}
    kind = record.get("kind")
    if kind == "http_response":
        method, url, status = payload.get("method"), payload.get("url"), payload.get("status")
        if method and url and isinstance(status, int) and 500 <= status <= 599:
            return kind, method.upper(), sanitize_url(url), status
    elif kind in {"page_error", "console_error"}:
        message = clean_message(str(payload.get("message") or "")).strip()
        if len(message) >= 20 and (kind == "page_error" or ":" in message) and not message.startswith("Failed to load resource"):
            return kind, message
    return None
