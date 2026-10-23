import re
from html.parser import HTMLParser

from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.profile.constants import (
    ALTERNATIVE_CLAUSE,
    EXCLUDED_HEADING,
    MANDATORY_CLAUSE,
    OPTIONAL_CLAUSE,
    REQUIRED_HEADING,
    SKILL_ALIASES,
    UMBRELLA_TERMS,
)


def _contains(alias: str, text: str) -> bool:
    pattern = r"(?<![\w+#.])" + re.escape(alias) + r"(?![\w+#])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _canonical(skill: str) -> str:
    stripped = skill.strip()
    folded = stripped.casefold()
    for canonical, aliases in SKILL_ALIASES.items():
        if folded == canonical.casefold() or any(folded == alias.casefold() for alias in aliases):
            return canonical
    return stripped


def normalize_required_skills(skills: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for skill in skills:
        canonical = _canonical(skill)
        if canonical and canonical.casefold() not in seen:
            normalized.append(canonical)
            seen.add(canonical.casefold())
    return normalized


def matches_skill(skill: str, evidence: str) -> bool:
    canonical = _canonical(skill)
    if canonical == "Go" and re.search(r"(?:^|[,;\n])\s*Go\s*(?:$|[,;\n])", evidence):
        return True
    aliases = SKILL_ALIASES.get(canonical, (canonical,))
    return bool(canonical) and any(_contains(alias, evidence) for alias in aliases)


def matches_term(term: str, evidence: str, *, umbrella: bool = False) -> bool:
    words = term.split()
    last = words[-1] if words else ""
    acronym = len(last) >= 2 and last.rstrip("s").isupper()
    phrase = len(words) > 1 and last.islower()
    variants = [term]
    if acronym or phrase:
        if last.endswith("s") and not last.endswith("ss"):
            variants.append(term[:-1])
        else:
            variants.append(term + "s")
    if umbrella:
        variants += UMBRELLA_TERMS.get(term.strip().casefold(), ())
    exact = term[:1].isupper() and (
        re.search(r"(?<![\w+#.])" + re.escape(term) + r"(?![\w+#])", evidence) is not None
    )
    return exact or any(matches_skill(variant, evidence) for variant in variants)


class _RequirementText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "noscript", "template"}:
            self.ignored.append(tag)
        elif not self.ignored and tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n# ")
        elif not self.ignored and tag in {
            "br",
            "p",
            "div",
            "li",
            "ul",
            "ol",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.ignored and tag == self.ignored[-1]:
            self.ignored.pop()
        elif not self.ignored and tag in {
            "p",
            "div",
            "li",
            "ul",
            "ol",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        }:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def _json_description(value: JsonValue) -> str:
    if isinstance(value, list):
        return "\n".join(_json_description(item) for item in value)
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    heading = value.get("text") or value.get("title")
    content = value.get("content")
    if isinstance(heading, str) and isinstance(content, str):
        parts.append(heading + ":\n" + content)
    for key, child in value.items():
        normalized_key = key.casefold().replace("_", "")
        if normalized_key in {"description", "jobdescription", "descriptionplain"}:
            if isinstance(child, str):
                parts.append(child)
        elif normalized_key in {"requiredskills", "requirements", "minimumqualifications"}:
            if isinstance(child, str):
                parts.append("Required qualifications:\n" + child + "\nEnd section:\n")
            elif isinstance(child, list):
                strings = [item for item in child if isinstance(item, str)]
                parts.append("Required qualifications:\n" + "\n".join(strings) + "\nEnd section:")
        elif isinstance(child, (dict, list)):
            parts.append(_json_description(child))
    return "\n".join(parts)


def _plain_description(description: str) -> str:
    stripped = description.strip()
    if stripped.startswith(("{", "[")):
        try:
            value = TypeAdapter(JsonValue).validate_json(stripped)
        except ValidationError:
            return ""
        stripped = _json_description(value)
    if re.search(r"</?[a-z][\w-]*(?:\s[^>]*)?>", stripped, re.IGNORECASE):
        parser = _RequirementText()
        parser.feed(stripped)
        return "".join(parser.parts)
    return stripped


def _heading(pattern: str, line: str) -> re.Match[str] | None:
    return re.match(
        r"^" + pattern + r"(?:\s*\([^)]*\))?(?:\s*[:\-]\s*(?P<body>.*)|\s*$)",
        line,
        re.IGNORECASE,
    )


def extract_required_skills(description: str) -> list[str]:
    required_section = False
    excluded_section = False
    found: list[str] = []
    for original in re.split(r"\r?\n|;", _plain_description(description)):
        line = re.sub(r"^\s*(?:#{1,6}\s*|[-*•]\s+|\d+[.)]\s+)", "", original).strip()
        line = line.replace("**", "").replace("__", "").strip()
        if not line:
            continue
        if re.match(r"^" + EXCLUDED_HEADING + r"(?=\s|:|$)", line, re.IGNORECASE):
            required_section = False
            excluded_section = True
            continue
        heading = _heading(REQUIRED_HEADING, line)
        if heading:
            required_section = True
            excluded_section = False
            line = heading.group("body") or ""
        elif original.lstrip().startswith("#") or line.endswith(":"):
            required_section = False
            excluded_section = True
        if excluded_section:
            continue
        for clause in re.split(r"\.(?=\s+[A-Z]|\s*$)", line):
            if re.search(OPTIONAL_CLAUSE, clause, re.IGNORECASE):
                continue
            if re.search(ALTERNATIVE_CLAUSE, clause, re.IGNORECASE):
                continue
            if not required_section and not re.search(MANDATORY_CLAUSE, clause, re.IGNORECASE):
                continue
            matches: list[tuple[int, str]] = []
            for canonical, aliases in SKILL_ALIASES.items():
                positions = [
                    match.start()
                    for alias in aliases
                    if (
                        match := re.search(
                            r"(?<![\w+#.])" + re.escape(alias) + r"(?![\w+#])",
                            clause,
                            re.IGNORECASE,
                        )
                    )
                    is not None
                ]
                if positions:
                    matches.append((min(positions), canonical))
            found.extend(skill for _, skill in sorted(matches))
    return normalize_required_skills(found)
