from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


SkillCallable = Callable[..., dict[str, Any]]


@dataclass
class SkillRegistry:
    skills: dict[str, SkillCallable]

    def __init__(self) -> None:
        self.skills = {}

    def register(self, name: str, skill: SkillCallable) -> None:
        self.skills[name] = skill

    def call(self, name: str, **kwargs: Any) -> dict[str, Any]:
        if name not in self.skills:
            raise KeyError(f"Unknown skill: {name}")
        return self.skills[name](**kwargs)

    def names(self) -> list[str]:
        return sorted(self.skills)
