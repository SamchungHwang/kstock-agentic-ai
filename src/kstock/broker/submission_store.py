from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InMemorySubmissionStore:
    seen: set[str] = field(default_factory=set)

    def add_if_absent(self, key: str) -> bool:
        if key in self.seen:
            return False
        self.seen.add(key)
        return True
