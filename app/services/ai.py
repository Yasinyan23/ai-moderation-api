from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModerationResult:
    safe: bool
    reason: Optional[str] = None
    severity: Optional[str] = None


class AIProvider(ABC):
    @abstractmethod
    async def moderate(self, message: str) -> ModerationResult: ...
