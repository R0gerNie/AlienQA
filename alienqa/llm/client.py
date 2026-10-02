"""LLMClient：LiteLLM 封装，支持模型轮换与故障自动回退。"""
import base64
from contextlib import contextmanager
from contextvars import ContextVar
import time

from .metering import public_text
from ..persistence import atomic_write_json
from pathlib import Path

from .config import resolve_model
from .models import LLMConfig, LLMResponse


def _litellm():
    import litellm

    return litellm


class RequestLimitExceeded(RuntimeError):
    """Local invocation budget exhausted before starting another request."""


class LLMClient:
    def __init__(self, config: LLMConfig, *, sink=None):
        self.config = config
        self.sink = sink
        self.on_metering_error = None
        self.before_request = None
        self.metering_errors = []
        self._context = ContextVar(f"llm-context-{id(self)}", default={})
        self._last_call = ContextVar(f"llm-call-{id(self)}", default=None)

    @property
    def last_call_id(self):
        return self._last_call.get()

    def set_context(self, **context):
        self._context.set(context)

    @contextmanager
    def call_scope(self, **context):
        token = self._context.set({**self._context.get(), **context})
        try:
            yield
        finally:
            self._context.reset(token)

    def _record(self, method, *args, **kwargs):
        if self.sink is None:
            return None
        try:
            return getattr(self.sink, method)(*args, **kwargs)
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            message = f"计量保存失败：{public_text(exc)}"
            self.metering_errors.append(message)
            try:
                atomic_write_json(self.sink.directory / "llm" / "metering-errors.json", self.metering_errors)
            except OSError:
                pass
            if self.on_metering_error:
                self.on_metering_error(message)
            return None

    def mark_parse(self, call_id, status, error=None):
        if call_id:
            self._record("mark_parse", call_id, status, error)
            self._record("write_summary")

    def complete(self, role: str, messages: list, temperature=None, *, context=None) -> LLMResponse:
        scope = {**self._context.get(), **(context or {})}
        role_name = role.value if hasattr(role, "value") else role
        call = self._record("start_call", role_name, scope, purpose=scope.get("purpose", "complete"), messages=messages)
        self._last_call.set(call)
        rc = self.config.role(role)
        if rc is None or not rc.model:
            error = ValueError(f"未配置 LLM 角色 '{role}' 的模型")
            if call:
                self._record("finish_call", call, "local_failed", error=error)
                self._record("write_summary")
            raise error
        models = [resolve_model(rc.model, self.config.default_provider)] + [
            resolve_model(m, self.config.default_provider) for m in rc.fallbacks]
        last_error = None
        attempted = False
        for model in models:
            codex = model.startswith("codex/")
            try:
                if codex:
                    from .codex import CodexProvider
                    completion = CodexProvider(self.config).completion
                else:
                    completion = _litellm().completion
                if self.before_request:
                    self.before_request(model)
            except Exception as exc:
                last_error = exc
                if call:
                    self._record("local_error", call, model, exc)
                if isinstance(exc, RequestLimitExceeded):
                    break
                continue
            settings = {"temperature": rc.temperature if temperature is None else temperature,
                        "timeout": self.config.request_timeout, "max_tokens": rc.max_tokens,
                        "configured_model": rc.model, "fallbacks": list(rc.fallbacks),
                        "default_provider": self.config.default_provider,
                        "max_retries": 0, "num_retries": 0,
                        "transport": "codex_cli" if codex else "litellm",
                        "metering_unit": "cli_invocation" if codex else "provider_request"}
            if codex:
                settings.update(requested_temperature=settings["temperature"], temperature=None,
                                requested_max_tokens=rc.max_tokens, max_tokens=None,
                                reasoning_effort=self.config.codex_reasoning_effort,
                                harness_version="alienqa-codex-v1", authentication="chatgpt")
            index = self._record("start_attempt", call, model, settings) if call else None
            started = time.monotonic()
            attempted = True
            try:
                kwargs = dict(model=model, messages=messages, temperature=settings["temperature"], timeout=settings["timeout"],
                              max_retries=0, num_retries=0)
                if rc.max_tokens is not None:
                    kwargs["max_tokens"] = rc.max_tokens
                resp = completion(**kwargs)
            except Exception as exc:  # supplier failure; retain it before fallback
                last_error = exc
                if index:
                    self._record("finish_attempt", call, index, status="failed", elapsed_seconds=time.monotonic()-started, error=exc)
                continue
            usage = _field(resp, "usage")
            if hasattr(usage, "model_dump"):
                try:
                    usage = usage.model_dump()
                except Exception:
                    usage = None
            usage = usage if isinstance(usage, dict) else None
            cost = _field(resp, "provider_cost")
            error = None
            try:
                choices = _field(resp, "choices")
                if not choices:
                    raise ValueError("供应商响应缺少 choices")
                text = _field(_field(choices[0], "message"), "content")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("供应商响应缺少有效 content")
            except (ValueError, TypeError, AttributeError, IndexError) as exc:
                error = last_error = exc
            if index:
                self._record("finish_attempt", call, index, status="succeeded", elapsed_seconds=time.monotonic()-started,
                             usage=usage, cost=cost, response_error=error)
            if error is not None:
                continue
            if call:
                self._record("finish_call", call, "succeeded", text=text)
                self._record("write_summary")
            return LLMResponse(text=text, model=model, role=role_name, usage=usage or {}, call_id=call or "")
        if call:
            self._record("finish_call", call, "failed" if attempted else "local_failed", error=last_error)
            self._record("write_summary")
        raise RuntimeError(f"LLM 调用全部失败 (models={models}): {public_text(last_error)}")

    def complete_vision(self, role: str, text: str, images: list) -> LLMResponse:
        content = [{"type": "text", "text": text}]
        try:
            for img in images:
                data_url = img if isinstance(img, str) and img.startswith("data:") else encode_image(img)
                content.append({"type": "image_url", "image_url": {"url": data_url}})
        except Exception as exc:
            scope = self._context.get()
            name = role.value if hasattr(role, "value") else role
            call = self._record("start_call", name, scope, purpose=scope.get("purpose", "vision_encoding"))
            self._last_call.set(call)
            if call:
                self._record("finish_call", call, "local_failed", error=exc)
                self._record("write_summary")
            raise
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


def _field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)
