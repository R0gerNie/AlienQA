"""alienqa.llm：LLM 层（LiteLLM 封装 + 三角色 + 模型轮换）。"""
from .client import LLMClient, encode_image
from .config import load_config, resolve_model
from .models import LLMConfig, LLMResponse, Role, RoleConfig
from .roles import LlmRoles

__all__ = [
    "LLMClient",
    "LLMConfig",
    "LLMResponse",
    "LlmRoles",
    "Role",
    "RoleConfig",
    "encode_image",
    "load_config",
    "resolve_model",
]
