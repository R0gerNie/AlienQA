"""ExpectationEngine：基于陌生用户直觉生成预期，并与观察比对产出 Mismatch。

先观察后预期解耦：expect() 不读 Observation，judge() 才读。
"""
from alienqa.i18n import language_context, t as tr

from ..context.models import ExplorerContext
from ..llm import LLMClient, LlmRoles
from ..driver.runtime import clean_message, sanitize_url
from ..driver.action import describe_visible_action, visible_target
from .contracts import generation_prompt_version, action_parameters, validate_rows, validate_reference
from copy import deepcopy
import json
from .models import Expectation, JudgmentError, JudgmentResult, Observation, PageInfo, parse_judgment


class ExpectationEngine:
    def __init__(self, client: LLMClient, samples: int = 2, focus: str = ""):
        self.client = client
        self.roles = LlmRoles(client)
        self.samples = samples
        self.focus = focus
        self.last_generation = {}
        self.last_input = {}
        self._frozen_expectations = {}
        self.last_judgment = []
        self.on_judgment = None

    def prepare_input(self, ctx, page_info, action=None) -> dict:
        with language_context(self.roles.language):
            return self._prepare_input(ctx, page_info, action)

    def _prepare_input(self, ctx, page_info, action=None) -> dict:
        """Freeze exactly the bounded visible fields supplied to generation."""
        visible = clean_message(getattr(ctx, "visible_text", "") or "")
        elements = getattr(page_info, "elements", [])
        route = sanitize_url(getattr(page_info, "route", ""))
        source_history = getattr(ctx, "visible_history", [])
        history = []
        for row in source_history[-5:]:
            step = row.get("step_id", "")
            if getattr(ctx, "step_id", "") and step >= ctx.step_id:
                continue
            history.append({"step_id": step, "action": clean_message(row.get("action", ""))[:200],
                            "visible_result": clean_message(row.get("visible_result", ""))[:1000]})
        return {"prompt_version": generation_prompt_version(self.roles.language), "language": self.roles.language,
                "run_id": getattr(ctx, "run_id", ""),
                "input_version": "visible-action-v2",
                "step_id": getattr(ctx, "step_id", ""), "action_id": getattr(ctx, "action_id", ""),
                "route": route[:2000], "visible_text": visible[:4000],
                "elements": [clean_message(str(e))[:100] for e in elements[:40]],
                "visible_history": history, "action": describe_visible_action(action),
                "action_target": visible_target(action),
                "action_parameters": action_parameters(action),
                "input_branch": getattr(action, "input_branch", "") if getattr(action, "input_branch", "") in {"valid", "invalid", "empty"} else "",
                "input_limits": {**getattr(ctx, "input_limits", {}),
                                 "visible_text_truncated": len(visible) > 4000 or getattr(ctx, "input_limits", {}).get("visible_text_truncated", False),
                                 "elements_truncated": len(elements) > 40,
                                 "element_text_truncated": any(len(str(e)) > 100 for e in elements[:40]),
                                 "route_truncated": len(route) > 2000,
                                 "history_truncated": len(source_history) > 5 or getattr(ctx, "input_limits", {}).get("history_truncated", False),
                                 "history_result_truncated": any(row.get("result_truncated") or len(row.get("visible_result", "")) > 1000
                                                                 for row in source_history[-5:])}}

    def expect(self, ctx: ExplorerContext, page_info: PageInfo, action=None) -> list[Expectation]:
        with language_context(self.roles.language):
            return self._expect(ctx, page_info, action)

    def _expect(self, ctx: ExplorerContext, page_info: PageInfo, action=None) -> list[Expectation]:
        """执行前只为选定动作生成预期（不读 Observation，防自我确认）。"""
        self.last_input = self.prepare_input(ctx, page_info, action)
        action_desc = _describe_action(action)[0]
        self._frozen_expectations = {}
        try:
            texts = self.roles.generate_expectations(gist="", page_text=json.dumps(self.last_input, ensure_ascii=False),
                                                    samples=self.samples, action_desc=self.last_input["action"],
                                                    with_basis=action is not None, frozen_input=self.last_input)
            out = []
            for index, row in enumerate(texts, 1):
                if isinstance(row, dict):
                    validate_reference(row, self.last_input)
                    out.append(Expectation(text=row["text"], action_desc=action_desc,
                                           expectation_basis=row["expectation_basis"],
                                           id=f"EX-{ctx.step_id}-{index:03d}" if ctx.step_id else "",
                                           run_id=ctx.run_id, step_id=ctx.step_id, action_id=ctx.action_id,
                                           prompt_version=generation_prompt_version(self.roles.language)))
                else:
                    out.append(Expectation(text=row, action_desc=action_desc))
            self._frozen_expectations = {e.id: deepcopy(e) for e in out if e.id}
            for group in self.roles.last_generation.get("groups", []):
                match = next((e for e in out if e.text == group["text"] and e.expectation_basis == group["expectation_basis"]), None)
                if match is not None:
                    group["expectation_id"] = match.id
            if self.roles.on_generation:
                self.roles.on_generation(self.roles.last_generation)
            return out
        except (ValueError, TypeError) as exc:
            self.roles.last_generation["error"] = str(exc)
            raise
        finally:
            self.last_generation = deepcopy(self.roles.last_generation)

    def evaluate(self, expectations, observation) -> JudgmentResult:
        with language_context(self.roles.language):
            return self._evaluate(expectations, observation)

    def _evaluate(self, expectations, observation) -> JudgmentResult:
        """区分通过、预期不符、执行失败和无法判断，并保留失败原因。"""
        self.last_judgment = []
        expectations = list(expectations or [])
        expected_texts = [e.text.strip() for e in expectations if isinstance(getattr(e, "text", None), str) and e.text.strip()]
        if not expected_texts:
            return JudgmentResult(status="inconclusive", error=tr("没有可验证的本次动作预期"))
        obs = _coerce_observation(observation)
        if obs is None:
            return JudgmentResult(status="inconclusive", error=tr("缺少动作后的观察"))
        if not getattr(obs, "before_image", None) or not getattr(obs, "after_image", None):
            return JudgmentResult(status="inconclusive", error=tr("缺少执行前或执行后的截图，无法进行盲判"))
        action_desc = getattr(obs, "action_desc", "") or ""
        bound_actions = {e.action_desc for e in expectations if getattr(e, "action_desc", "")}
        if bound_actions and not action_desc:
            return JudgmentResult(status="inconclusive", error=tr("观察没有动作描述，无法确认预期与动作的绑定"))
        if bound_actions and bound_actions != {action_desc}:
            return JudgmentResult(status="failed", error=tr("预期与当前观察绑定的动作不一致"))
        identified = [e for e in expectations if getattr(e, "id", "")]
        if identified:
            if len(identified) != len(expectations) or len({e.id for e in identified}) != len(identified):
                return JudgmentResult(status="failed", error=tr("事前预期身份缺失或重复"))
            for e in identified:
                if self._frozen_expectations.get(e.id) != e:
                    return JudgmentResult(status="failed", error=tr("事前预期缺失或已被修改"))
                try:
                    validate_rows([{"text": e.text, "expectation_basis": e.expectation_basis}])
                except ValueError as exc:
                    return JudgmentResult(status="failed", error=str(exc))
                if any(not getattr(e, key, "") or getattr(e, key) != getattr(obs, key, "")
                       for key in ("run_id", "step_id", "action_id")):
                    return JudgmentResult(status="failed", error=tr("预期与观察的 run/step/action 不一致"))
            expected = json.dumps([{"expectation_id": e.id, "text": e.text,
                                    "expectation_basis": e.expectation_basis} for e in identified], ensure_ascii=False)
        else:
            expected = "\n".join(f"- {t}" for t in expected_texts)
        last_error = ""
        for repair in (False, True):
            try:
                raw = self.roles.judge(
                    self.last_input.get("action", action_desc) if identified else action_desc,
                    expected,
                    obs.before_image,
                    obs.after_image,
                    visible={"before_text": getattr(obs, "before_text", "")[:4000],
                             "after_text": getattr(obs, "after_text", "")[:4000],
                             "control_state": deepcopy(getattr(obs, "control_state", {})),
                             "visual_summary": getattr(getattr(obs, "visual", None), "summary", "")[:2000]},
                    repair=repair,
                )
            except Exception as exc:  # noqa: BLE001 - failures are recorded for the caller.
                self.last_judgment.append({"repair": repair, "error": str(exc)})
                return JudgmentResult(status="failed", error=tr("判定模型调用失败: {error}", error=exc))
            attempt = {"repair": repair, "raw": raw[:16000], "raw_truncated": len(raw) > 16000}
            self.last_judgment.append(attempt)
            if self.on_judgment:
                self.on_judgment(self.last_judgment)
            try:
                result = parse_judgment(raw)
                if any(m.expectation not in expected_texts for m in result.mismatches):
                    raise ValueError(tr("判定输出引用了本次动作未提供的预期"))
                if identified and any(not any(e.id == m.expectation_id and e.text == m.expectation
                                              for e in identified) for m in result.mismatches):
                    raise ValueError(tr("判定输出的 expectation_id/text 不属于事前集合"))
                references = [m.expectation_id if identified else m.expectation for m in result.mismatches]
                if len(references) != len(set(references)):
                    raise ValueError(tr("判定输出重复引用同一预期"))
                unchecked = set(result.unverifiable_expectation_ids)
                if unchecked - {e.id for e in identified} or unchecked.intersection(references):
                    raise ValueError(tr("无法判断的预期 ID 未提供或同时出现在 mismatch"))
                self.roles.mark_parse("succeeded")
                attempt["status"] = result.status
                return result
            except (ValueError, TypeError) as exc:
                self.roles.mark_parse("failed", exc)
                last_error = str(exc)
                attempt["error"] = last_error
        return JudgmentResult(status="failed", error=tr("判定输出在修复后仍无效: {error}", error=last_error))

    def judge(self, expectations, observation) -> list:
        """兼容旧列表接口；失败和无法判断会抛 JudgmentError。"""
        result = self.evaluate(expectations, observation)
        if result.status in ("failed", "inconclusive"):
            raise JudgmentError(result.error, status=result.status)
        return result.mismatches


def _coerce_observation(observation) -> Observation | None:
    """07 的 canonical Observation（或任何带 before_image/after_image/action_desc/technical 的对象）。"""
    if observation is None:
        return None
    return observation


def _describe_action(action) -> tuple[str, str]:
    """Legacy display identity; model inputs use describe_visible_action instead."""
    if action is None:
        return "", ""
    if isinstance(action, dict):
        action_type = action.get("type") or action.get("action") or ""
        target = action.get("target") or {}
    else:
        action_type = getattr(action, "type", "")
        target = getattr(action, "target", None)
    if isinstance(target, dict):
        label = target.get("text") or target.get("selector") or ""
    elif target is not None:
        label = getattr(target, "text", "") or getattr(target, "selector", "") or ""
    else:
        label = ""
    desc = " ".join(str(part) for part in (action_type, label) if part).strip()
    return desc, desc  # Typed values (including passwords) never become history/prompt text.
