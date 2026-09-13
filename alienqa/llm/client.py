"""LLMClient：LiteLLM 封装，支持模型轮换与故障自动回退。"""
import base64
from pathlib import Path

from .config import resolve_model
from .models import LLMConfig, LLMResponse


def _litellm():
    import litellm

    return litellm


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    def complete(self, role: str, messages: list, temperature=None) -> LLMResponse:
        rc = self.config.role(role)
        if rc is None or not rc.model:
            raise ValueError(f"未配置 LLM 角色 '{role}' 的模型")
        models = [resolve_model(rc.model, self.config.default_provider)] + [
            resolve_model(m, self.config.default_provider) for m in rc.fallbacks
        ]
        litellm = _litellm()
        last_error = None
        for model in models:
            try:
                kwargs = dict(
                    model=model,
                    messages=messages,
                    temperature=rc.temperature if temperature is None else temperature,
                    timeout=self.config.request_timeout,
                )
                if rc.max_tokens is not None:
                    kwargs["max_tokens"] = rc.max_tokens
                resp = litellm.completion(**kwargs)
                text = (resp.choices[0].message.content or "") if resp.choices else ""
                usage = getattr(resp, "usage", None)
                return LLMResponse(
                    text=text,
                    model=model,
                    role=role if isinstance(role, str) else role.value,
                    usage=usage.model_dump() if hasattr(usage, "model_dump") else {},
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        raise RuntimeError(f"LLM 调用全部失败 (models={models}): {last_error}")

    def complete_vision(self, role: str, text: str, images: list) -> LLMResponse:
        """多模态调用：images 为 bytes / 文件路径 / PIL 图列表，按顺序拼接。"""
        content = [{"type": "text", "text": text}]
        for img in images:
            data_url = img if isinstance(img, str) and img.startswith("data:") else encode_image(img)
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        return self.complete(role, [{"role": "user", "content": content}])

    def model_for(self, role: str) -> str:
        rc = self.config.role(role)
        if rc is None or not rc.model:
            raise ValueError(f"未配置 LLM 角色 '{role}' 的模型")
        return resolve_model(rc.model, self.config.default_provider)


def encode_image(image) -> str:
    """把 bytes / 文件路径 / PIL 图 转成 data:image 的 base64 URL。"""
    if isinstance(image, bytes):
        raw = image
    elif isinstance(image, (str, Path)):
        raw = Path(image).read_bytes()
    else:
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        raw = buf.getvalue()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
