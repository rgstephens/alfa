from enum import Enum
from typing import Any


class StrEnum(str, Enum):
    def __str__(self) -> Any:
        return self.value
