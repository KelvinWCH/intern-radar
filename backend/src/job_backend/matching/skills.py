import math
import re

from job_backend.profile.constants import SKILL_ALIASES

COMMON_WORDS = frozenset(
    {
        "go",
        "r",
        "c",
        "swift",
        "rust",
        "spring",
        "express",
        "react",
        "flask",
        "node",
        "dart",
        "julia",
        "ruby",
        "spark",
        "unity",
        "shell",
        "rails",
        "vue",
        "next",
        "make",
        "excel",
        "access",
        "word",
        "teams",
        "figma",
        "jest",
        "mocha",
        "chef",
        "puppet",
        "ansible",
        "elixir",
    }
)


def _variants(skill: str) -> list[str]:
    folded = skill.casefold()
    for canonical, aliases in SKILL_ALIASES.items():
        names = (canonical, *aliases)
        if any(folded == name.casefold() for name in names):
            return list(dict.fromkeys((skill, *names)))
    return [skill]


def _pattern(names: list[str], *, ignore_case: bool) -> re.Pattern[str] | None:
    if not names:
        return None
    body = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return re.compile(
        r"(?<![\w+#.])(?:" + body + r")(?![\w+#])", re.IGNORECASE if ignore_case else 0
    )


class SkillMatcher:
    def __init__(self, skills: list[str]) -> None:
        self.skills = skills
        self._exact: dict[str, str] = {}
        self._folded: dict[str, str] = {}
        for skill in skills:
            for name in _variants(skill):
                if len(name) <= 2 or name.casefold() in COMMON_WORDS:
                    self._exact.setdefault(name, skill)
                else:
                    self._folded.setdefault(name.casefold(), skill)
        self._exact_pattern = _pattern(list(self._exact), ignore_case=False)
        self._folded_pattern = _pattern(list(self._folded), ignore_case=True)

    def find(self, text: str) -> set[str]:
        found: set[str] = set()
        if self._folded_pattern is not None:
            found.update(
                self._folded[match.group().casefold()]
                for match in self._folded_pattern.finditer(text)
            )
        if self._exact_pattern is not None:
            found.update(self._exact[match.group()] for match in self._exact_pattern.finditer(text))
        return found


def inverse_frequencies(counts: dict[str, int], documents: int) -> dict[str, float]:
    return {
        skill: round(math.log((documents + 1) / (count + 1)) + 1.0, 4)
        for skill, count in counts.items()
    }
