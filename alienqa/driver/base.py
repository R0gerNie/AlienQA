"""驱动抽象接口。"""
from abc import ABC, abstractmethod


class BaseDriver(ABC):
    """浏览器执行器接口：Playwright / PyAutoGUI 各自实现，配置切换。"""

    @abstractmethod
    def launch(self, url: str) -> None: ...

    @abstractmethod
    def execute(self, action) -> None: ...

    @abstractmethod
    def screenshot(self) -> bytes: ...

    @abstractmethod
    def collect_runtime(self): ...

    @abstractmethod
    def close(self) -> None: ...
