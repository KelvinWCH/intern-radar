from functools import lru_cache
from typing import Literal

from job_backend.common.text_matching import close_spelling, normalized_text
from job_backend.jobs.constants import KNOWN_COMPANIES, TECH_COMPANIES


def company_key(company: str) -> str:
    words = normalized_text(company.replace("&", " ")).split()
    while words and words[-1] in {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "ltd",
        "limited",
        "llc",
        "plc",
    }:
        words.pop()
    return " ".join(words)


_NAMES = {company_key(alias) for aliases in KNOWN_COMPANIES for alias in aliases}
_TECH_NAMES = {company_key(alias) for aliases in TECH_COMPANIES for alias in aliases}


@lru_cache(maxsize=4096)
def company_tier(company: str) -> Literal["tech", "known"] | None:
    name = company_key(company)
    if name in _NAMES:
        return "tech" if name in _TECH_NAMES else "known"
    for suffix in (" canada", " us", " usa", " uk"):
        name = name.removesuffix(suffix)
    if name in _NAMES:
        return "tech" if name in _TECH_NAMES else "known"
    compact = name.replace(" ", "")
    for alias in sorted(_NAMES):
        candidate = alias.replace(" ", "")
        if compact == candidate or (
            len(compact) >= 6 and len(candidate) >= 6 and close_spelling(compact, candidate)
        ):
            return "tech" if alias in _TECH_NAMES else "known"
    return None


def prestige_priority(company: str) -> int:
    return int(company_tier(company) is not None)


def job_priority(company: str, toronto_area: bool) -> int:
    tier = company_tier(company)
    return (0 if toronto_area else 3) + {"tech": 0, "known": 1, None: 2}[tier]
