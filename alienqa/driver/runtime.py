"""运行时信号：console 错误、页面异常、网络失败。"""
from dataclasses import dataclass, field


@dataclass
class RuntimeSignals:
    console_errors: list = field(default_factory=list)
    page_errors: list = field(default_factory=list)
    network_failures: list = field(default_factory=list)
    http_errors: list = field(default_factory=list)
