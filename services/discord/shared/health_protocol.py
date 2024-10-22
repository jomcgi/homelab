from typing import Protocol, runtime_checkable


@runtime_checkable
class Healthable(Protocol):
    def is_healthy(self) -> bool: ...
