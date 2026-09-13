"""Exploration Context 测试：白名单裁剪、default-deny、审计块、policy 可调、截图钩子。"""
from alienqa.context import (
    ContextPolicy,
    ExplorationContext,
    ExplorerContext,
    InvestigatorContext,
    Observation,
    ScreenshotProcessor,
)
from alienqa.mapper import ProductMap, Relation
from alienqa.state import State


def _state(route="/orders", snapshot="订单列表", action=None):
    return State(id="S-1", route=route, signature=f"sig:{route}", snapshot=snapshot, action=action)


def _product_map():
    return ProductMap(
        brief="这是一个电商后台，可管理订单",
        relations=[
            Relation(from_="/orders", to="/orders/:id", kind="navigate"),
            Relation(from_="/login", to="/orders", kind="navigate"),
        ],
    )


# ---- 白名单 / default-deny ----

def test_is_allowed_whitelist_and_default_deny():
    fw = ExplorationContext()
    assert fw.is_allowed("visible_text") is True
    assert fw.is_allowed("screenshot") is True
    assert fw.is_allowed("prd") is False
    assert fw.is_allowed("unknown_x") is False


def test_build_assembles_allowed_fields():
    fw = ExplorationContext()
    state = _state(action={"type": "click", "target": {"text": "申请退款"}})
    obs = Observation(screenshot=b"\x89PNG", visible_text="订单列表")
    ctx = fw.build(_product_map(), state, obs, [state])
    assert ctx.product_brief == "这是一个电商后台，可管理订单"
    assert ctx.visible_text == "订单列表"
    assert ctx.screenshot == b"\x89PNG"
    assert ctx.navigation == [{"from": "/orders", "to": "/orders/:id", "kind": "navigate"}]
    assert ctx.action_history == ["click 申请退款"]


def test_forbidden_manifest_never_true():
    ctx = ExplorationContext().build(_product_map(), _state(), Observation(), [])
    assert set(ctx.forbidden) == {"prd", "dev_comments", "git_history", "known_bugs", "internal_rules", "tech_details"}
    assert all(v is False for v in ctx.forbidden.values())


def test_navigation_filters_current_route():
    ctx = ExplorationContext().build(_product_map(), _state(route="/login"), Observation(), [])
    assert ctx.navigation == [{"from": "/login", "to": "/orders", "kind": "navigate"}]


# ---- 认知边界可调 / 截图钩子 ----

def test_policy_tightening_excludes_fields():
    policy = ContextPolicy(allowed=("visible_text",))
    fw = ExplorationContext(policy=policy)
    ctx = fw.build(_product_map(), _state(snapshot="hello"), Observation(screenshot=b"x"), [])
    assert ctx.visible_text == "hello"
    assert ctx.screenshot is None
    assert ctx.product_brief == ""


class _Compress(ScreenshotProcessor):
    def process(self, raw):
        return b"compressed:" + (raw or b"")


def test_screenshot_processor_hook():
    fw = ExplorationContext(screenshot_processor=_Compress())
    ctx = fw.build(_product_map(), _state(), Observation(screenshot=b"raw"), [])
    assert ctx.screenshot == b"compressed:raw"


# ---- 输入适配器 ----

def test_visible_text_falls_back_to_state_snapshot():
    ctx = ExplorationContext().build(_product_map(), _state(snapshot="从状态来"), Observation(), [])
    assert ctx.visible_text == "从状态来"


def test_history_mixed_inputs():
    s1 = _state(action={"type": "click", "target": {"text": "保存"}})
    ctx = ExplorationContext().build(
        _product_map(), _state(), Observation(),
        [s1, {"type": "type", "target": {"selector": "#name"}}, "press Enter"],
    )
    assert ctx.action_history == ["click 保存", "type #name", "press Enter"]


def test_build_with_none_inputs():
    ctx = ExplorationContext().build(None, None, None, None)
    assert ctx.product_brief == ""
    assert ctx.navigation == []
    assert ctx.visible_text == ""
    assert ctx.action_history == []
    assert ctx.screenshot is None


# ---- 与 Investigator 隔离 / 序列化 ----

def test_investigator_context_isolated():
    assert not hasattr(ExplorerContext(), "source")
    inv = InvestigatorContext(source="src/app.tsx", git_diff="diff --git")
    assert inv.source == "src/app.tsx"
    assert inv.git_diff == "diff --git"


def test_to_dict_matches_planbook_shape():
    ctx = ExplorationContext().build(_product_map(), _state(), Observation(screenshot=b"img"), [])
    d = ctx.to_dict()
    assert set(d["allowed"]) == {"screenshot", "visible_text", "action_history", "navigation", "product_brief"}
    assert set(d["forbidden"]) == {"prd", "dev_comments", "git_history", "known_bugs", "internal_rules", "tech_details"}
