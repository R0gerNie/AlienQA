"""Small, whole-sentence relationship rules for action-scoped feedback.

This is deliberately not a general semantic classifier. Unknown modifiers stay
unknown; comparison keys never replace the original expectation sent to judge.
"""
from dataclasses import dataclass
import re
import unicodedata

MERGE_VERSION = "sampling-merge-v3"


def normalize_layout(text):
    """Only typography; negation, objects, quantities and conditions survive."""
    text = unicodedata.normalize("NFKC", text).strip()
    return re.sub(r"\s+", " ", text).translate(str.maketrans({"。": ".", "，": ",", "；": ";", "、": ","}))


@dataclass(frozen=True)
class FeedbackClaim:
    facet: str
    positive: bool
    rule_id: str


def recognize_feedback(text, action_desc):
    """Consume a complete supported sentence in the frozen action's scope."""
    kind, _, label = action_desc.partition(" ")
    if not label or label in {"当前控件", "current control", "Unlabeled control"}:
        return None
    value = normalize_layout(text)
    english = _recognize_english(value, kind, label)
    if english is not None:
        return english
    label = re.escape(normalize_layout(label))
    target = rf'(?:[「“\"]?{label}[」”\"]?)'
    # Finite, whole-sentence input conventions observed in the real baseline.
    # Matching the current control is mandatory; extra clauses remain unknown.
    if kind == "type":
        pattern = rf"在{target}中输入(?:文本|文字)后,输入框应可见地显示所输入的内容\.?"
        if re.fullmatch(pattern, value):
            return FeedbackClaim("input_value", True, "input_value.visible_content")
        return None
    if kind == "blur":
        pattern = rf"{target}\s*失去(?:输入)?焦点,不再显示(?:活动)?输入光标\.?"
        if re.fullmatch(pattern, value):
            return FeedbackClaim("input_focus", True, "input_focus.blur_cursor")
        return None
    if kind != "click":
        return None
    prefix = rf"(?:(?:点击|点按|点|按下)(?:按钮)?{target}后|{target}后|本次操作后|操作后|点击后),?"
    subject = r"(?:界面|页面)?"
    expectation = r"(?:应当|应该|应|需要)"
    result = r"(?:(?:可观察的|可查看的|可见的|明确的)?(?:操作结果反馈|操作结果|结果反馈|可见结果反馈|可见反馈|反馈)|(?:可观察|可查看|可见)(?:的)?结果)"
    positive = rf"{subject}{expectation}(?:提供|给出|呈现|显示|出现|有|说明)(?:本次操作的|此次操作的)?{result}"
    negative = rf"{subject}(?:不应|不应该|不应当)(?:提供|给出|呈现|显示|出现|有){result}"
    if re.fullmatch(prefix + negative + r"\.?", value):
        return FeedbackClaim("presence", False, "operation_feedback.absent")
    readable = rf"{subject}(?:操作结果)?反馈{expectation}(?:清晰可读|明确可读)"
    if re.fullmatch(prefix + readable + r"\.?", value):
        return FeedbackClaim("readability", True, "operation_feedback.readable")

    # Only click 保存/保存下一项 can consume clauses talking about 保存. Other
    # click targets cannot inherit this business object from a similar phrase.
    save = normalize_layout(action_desc).split(" ", 1)[1] in {"保存", "保存下一项"}
    operation = r"(?:保存|操作)" if save else r"操作"
    unsuccessful = r"(?:失败|未成功|未完成)"
    unavailable = r"(?:因当前(?:条件|状态)无法(?:完成|执行)|受到限制)"
    if save:
        unavailable = rf"(?:{unavailable}|当前无法保存|因当前(?:条件|状态)无法保存)"
    alternatives = rf",?或因何未能完成|,{unsuccessful}或{unavailable}"
    if save:
        alternatives += r"|,?或是否因当前(?:条件|状态)无法保存"
    outcome_tail = rf"(?:{alternatives})"
    outcome = rf"(?:此次|本次)?{operation}(?:是否成功|是否完成){outcome_tail}?"
    purpose = rf"(?:让(?:我|用户)(?:能)?(?:知道|判断)|使(?:我|用户)(?:能)?判断){outcome}"
    completed = r"让用户能判断操作是否完成或为何无法完成"
    explanation = (rf"说明(?:保存成功,{unsuccessful}或{unavailable}|本次保存的结果或当前无法保存的原因)"
                   if save else r"说明本次操作的结果")
    examples = ["结果说明", "按钮状态变化", "导航反馈"]
    if save:
        examples += ["保存结果", "保存状态", "保存状态更新", "无法保存的原因", "无法保存的说明", "当前无法保存的说明"]
    example = "(?:" + "|".join(map(re.escape, examples)) + ")"
    example_list = rf"例如{example}(?:(?:,?或|,){example})*"
    unrestricted = r"(?:不限定(?:具体)?(?:反馈)?形式|(?:反馈)?形式不限)"
    suffix = rf"(?:[,;](?:{purpose}|{completed}|{explanation}|{example_list}|{unrestricted}))*"
    if re.fullmatch(prefix + positive + suffix + r"\.?", value):
        return FeedbackClaim("presence", True, "operation_feedback.visible_result")
    return None


def _recognize_english(value, kind, label):
    """Finite English counterparts, preserving target, negation and modifiers."""
    target = rf'(?:[「“"]?{re.escape(normalize_layout(label))}[」”"]?)'
    if kind == "type":
        if re.fullmatch(rf"After typing text into {target}, the input should visibly display the entered content\.?", value):
            return FeedbackClaim("input_value", True, "input_value.visible_content")
        return None
    if kind == "blur":
        if re.fullmatch(rf"{target} should lose (?:input )?focus and no longer show an (?:active )?text cursor\.?", value):
            return FeedbackClaim("input_focus", True, "input_focus.blur_cursor")
        return None
    if kind != "click":
        return None
    prefix = rf"(?:[Aa]fter (?:clicking|pressing) (?:the button )?{target}|[Aa]fter this operation|[Aa]fter the operation|[Aa]fter clicking),? "
    result = r"(?:(?:visible |observable |clear )?(?:result feedback|operation result feedback|operation feedback|feedback)|(?:visible|observable) result)"
    subject = r"(?:(?:the page|the interface) )?"
    negative = rf"(?:{result} should not be (?:provided|shown|displayed)|{subject}should not (?:provide|show|display|present) {result})"
    if re.fullmatch(prefix + negative + r"\.?", value):
        return FeedbackClaim("presence", False, "operation_feedback.absent")
    if re.fullmatch(prefix + subject + r"(?:operation result )?feedback should be (?:clearly readable|clear and readable)\.?", value):
        return FeedbackClaim("readability", True, "operation_feedback.readable")
    positive = rf"(?:{result} should be (?:provided|shown|displayed)|there should be {result})"
    active = rf"{subject}should (?:provide|show|display|present) {result}"
    # Exact clauses are optional counterparts of the supported Chinese clauses.
    # Save-specific wording is available only for a Save control.
    save = normalize_layout(label).casefold() in {"保存", "保存下一项", "save", "save next", "save next item"}
    operation = r"(?:operation|save)" if save else r"operation"
    purpose = rf"(?:so (?:I|the user) can (?:tell|determine) whether (?:this |the )?{operation} (?:succeeded|completed)(?: or why it could not be completed)?)"
    explanation = r"to explain the result of this operation"
    if save:
        explanation = rf"(?:{explanation}|to explain the save result or why saving is currently unavailable)"
    example = r"(?:a result explanation|a button state change|navigation feedback"
    if save:
        example += r"|a save result|a save status update|an explanation of why saving is unavailable"
    example += r")"
    examples = rf"for example, {example}(?:(?:, | or ){example})*"
    suffix = rf"(?:[,;] (?:{purpose}|{explanation}|{examples}|without restricting the feedback format))*"
    if re.fullmatch(prefix + rf"(?:{positive}|{active})" + suffix + r"\.?", value):
        return FeedbackClaim("presence", True, "operation_feedback.visible_result")
    return None


def relation(left, right):
    if left is None or right is None:
        return "relation_unknown"
    if left.facet == right.facet:
        return "equivalent" if left.positive == right.positive else "conflict"
    # Readable feedback and absent feedback cannot coexist. Requiring readable
    # feedback does not itself promise a successful save.
    if not left.positive or not right.positive:
        return "conflict"
    return "compatible"
