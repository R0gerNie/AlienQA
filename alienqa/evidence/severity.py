"""严重度 / 置信度 / 分类的确定性规则（planbook：可先手写阈值，后续可学习）。"""
from ..expectation.models import MismatchLevel
from .models import Severity


def _tech(observation) -> dict:
    return observation.technical if observation is not None else {}


def assess_severity(mismatch, observation) -> Severity:
    tech = _tech(observation)
    blank = observation.visual.blank_screen_score if observation is not None else 0.0
    http_status = tech.get("http_status") or {}
    has_5xx = any(str(s).startswith("5") for s in http_status.values())
    has_4xx = any(str(s).startswith("4") for s in http_status.values())
    has_js = bool(tech.get("js_exceptions"))
    has_console = bool(tech.get("console_errors"))
    has_net = bool(tech.get("network_failures"))

    if blank > 0.8 or (has_js and has_5xx):
        return Severity.CRITICAL
    if mismatch.level == MismatchLevel.HIGH or has_console or has_net or has_5xx or has_4xx:
        return Severity.MAJOR
    if mismatch.level == MismatchLevel.MEDIUM:
        return Severity.MINOR
    return Severity.TRIVIAL


def confidence(mismatch, observation) -> float:
    """信号越强置信度越高；多路独立信号叠加。"""
    tech = _tech(observation)
    score = 0.5
    if tech.get("console_errors") or tech.get("js_exceptions") or tech.get("http_status"):
        score += 0.2
    if tech.get("network_failures"):
        score += 0.1
    if observation is not None and observation.visual.blank_screen_score > 0.8:
        score += 0.2
    return round(min(0.95, max(0.1, score)), 2)


def classify(mismatch, observation, action) -> str:
    """技术信号驱动 + 关键词兜底；默认 ux_ambiguity（含'看起来可点击但无响应'）。"""
    tech = _tech(observation)
    blank = observation.visual.blank_screen_score if observation is not None else 0.0
    http_status = tech.get("http_status") or {}
    has_exception = bool(tech.get("js_exceptions"))
    has_5xx = any(str(s).startswith("5") for s in http_status.values())
    has_4xx = any(str(s).startswith("4") for s in http_status.values())

    if (has_exception or has_5xx or blank > 0.8
            or tech.get("console_errors") or tech.get("network_failures") or has_4xx):
        return "technical_bug"

    text = f"{mismatch.expectation} {mismatch.observation} {mismatch.reasoning}"
    if any(k in text for k in ("文案", "误导", "看不懂")):
        return "misleading_copy"
    if any(k in text for k in ("反馈", "提示", "确认", "成功")):
        return "missing_feedback"
    # 含"长得像按钮/可点击但点了没反应、可能不是按钮"这类视觉 affordance 问题
    return "ux_ambiguity"
