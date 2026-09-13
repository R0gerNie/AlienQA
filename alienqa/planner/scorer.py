"""价值评分器：确定性启发式（greedy）。"""
RISK_KEYWORDS = (
    "删除", "清空", "支付", "退款", "注销", "永久", "提交订单", "取消订阅",
    "delete", "remove", "pay", "refund", "deactivate", "clear",
)
BOUNDARY_KEYWORDS = (
    "再次", "重新", "恢复", "取消", "继续", "重试", "撤回",
    "again", "retry", "recover", "resume", "cancel", "revert",
)
NAVIGATION_KEYWORDS = (
    "登录", "注册", "下一步", "继续", "查看", "前往",
    "login", "register", "sign in", "sign up", "next", "continue",
)


def _has_any(text: str, keywords) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in keywords)


def score(candidate, clicked: set, explored_routes: set) -> float:
    """返回候选的启发式价值分：coverage_gain + risk + boundary + novelty。"""
    s = 0.0
    key = candidate.selector or candidate.text
    # coverage_gain：未点击过 +5（防重复的根）
    if key and key not in clicked:
        s += 5.0
    # risk：高风险操作优先调查
    if _has_any(candidate.text, RISK_KEYWORDS):
        s += 3.0
    # boundary：状态边界操作优先
    if _has_any(candidate.text, BOUNDARY_KEYWORDS):
        s += 3.0
    # novelty：链接指向未探索 route
    if candidate.href and candidate.href not in explored_routes:
        s += 2.0
    # novelty：导航性文本
    if _has_any(candidate.text, NAVIGATION_KEYWORDS):
        s += 1.0
    return s
