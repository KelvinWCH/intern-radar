import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import JsonValue

from job_backend.jobs.company_priority import company_key, company_tier
from job_backend.matching.models import MatchBand
from job_backend.scrape.models import JobReportItem
from job_backend.scrape.notifications import markdown_text, posted_day, safe_job_url

DailyView = Literal["top", "match", "new", "company", "gta", "known"]
Score = tuple[int, MatchBand]

COMPONENTS_V2 = 1 << 15
EPHEMERAL = 1 << 6
PAGE_SIZE = 8
MAX_COMPONENTS = 40
MAX_TEXT = 4000
_ENTRY_BUDGET = 3200
_LIST_BUDGET = 3500
_ENTITY_CODE = re.compile(r"^\d{3,}(?:\s*-\s*|\s+)(?=\S)")
_ACCENT = 0xC6A0F6
_VIEWS: dict[DailyView, tuple[str, str, str]] = {
    "top": ("⭐", "Top picks", "Toronto area first, then tech, known, and other employers"),
    "match": ("✨", "Best match", "Highest match score first"),
    "new": ("🕒", "Newest first", "Most recently found first"),
    "company": ("🏢", "By company", "Employers A to Z, each one's listings together"),
    "gta": ("📍", "Toronto area only", "Only listings in the Toronto area"),
    "known": ("🔴", "Tech & known employers", "Only employers on the recognized list"),
}
_VIEW_KEYS: dict[str, DailyView] = {key: key for key in _VIEWS}
_TIERS = {"tech": "🔴", "known": "🟡", None: "⚪"}
_SEASONS = ("❄️", "❄️", "🌸", "🌸", "🌸", "🌻", "🌻", "🌻", "🍂", "🍂", "🍂", "❄️")
_CUSTOM_ID = re.compile(r"dj:(\d{4}-\d{2}-\d{2}):(?:view|([a-z]+):(\d{1,4}):[fpcnl])")


def ordered_jobs(
    jobs: Sequence[JobReportItem], scores: Mapping[str, Score], view: DailyView
) -> list[JobReportItem]:
    if view == "gta":
        return [job for job in jobs if job.is_toronto_area]
    if view == "known":
        return [job for job in jobs if company_tier(job.company) is not None]
    result = list(jobs)
    if view == "match":
        result.sort(key=lambda job: -scores[job.id][0] if job.id in scores else 1)
    elif view == "new":
        result.sort(key=lambda job: -job.first_seen_at)
    elif view == "company":
        result.sort(key=lambda job: job.company.casefold())
    return result


def _entry(job: JobReportItem, score: Score | None) -> str:
    marker = _TIERS[company_tier(job.company)]
    place = markdown_text(job.locations[0], 70) if job.locations else "Location not listed"
    if len(job.locations) > 1:
        place += f" +{len(job.locations) - 1}"
    facts = [
        f"**{markdown_text(job.company, 80)}**",
        ("📍 " if job.is_toronto_area else "") + place,
    ]
    if job.terms:
        facts.append(markdown_text(", ".join(job.terms), 60))
    notes: list[str] = []
    if score is not None:
        value, band = score
        notes.append(f"✨ {value} {band} match" if band in {"strong", "good"} else f"{value} match")
    if job.date_posted is not None:
        notes.append(f"posted <t:{job.date_posted}:d>")
    notes.append(f"found <t:{job.first_seen_at}:R>")
    return (
        f"{marker} **{markdown_text(job.title, 120)}**\n"
        + " · ".join(facts)
        + "\n-# "
        + " · ".join(notes)
    )


def _pages(entries: Sequence[str]) -> list[range]:
    pages: list[range] = []
    start = 0
    while start < len(entries):
        end, size = start, 0
        while end < len(entries) and end - start < PAGE_SIZE:
            size += len(entries[end])
            if end > start and size > _ENTRY_BUDGET:
                break
            end += 1
        pages.append(range(start, end))
        start = end
    return pages or [range(0)]


def _text(content: str) -> dict[str, JsonValue]:
    return {"type": 10, "content": content}


def _separator() -> dict[str, JsonValue]:
    return {"type": 14, "divider": True, "spacing": 1}


def _button(
    label: str, custom_id: str, *, disabled: bool, primary: bool = False
) -> dict[str, JsonValue]:
    return {
        "type": 2,
        "style": 1 if primary else 2,
        "label": label,
        "custom_id": custom_id,
        "disabled": disabled,
    }


def daily_page(
    jobs: Sequence[JobReportItem],
    scores: Mapping[str, Score],
    *,
    day: date,
    view: DailyView = "top",
    page: int = 0,
    updated_at: int,
) -> dict[str, JsonValue]:
    shown = ordered_jobs(jobs, scores, view)
    entries = [_entry(job, scores.get(job.id)) for job in shown]
    pages = _pages(entries)
    page = max(0, min(page, len(pages) - 1))
    current = pages[page]
    emoji, label, _description = _VIEWS[view]
    tiers = [company_tier(job.company) for job in jobs]
    counts = [
        f"📍 {sum(job.is_toronto_area is True for job in jobs)} Toronto area",
        f"🔴 {tiers.count('tech')} tech",
        f"🟡 {tiers.count('known')} known",
        f"⚪ {tiers.count(None)} other",
    ]
    if not shown:
        position = "nothing in this view yet"
    else:
        position = f"{current.start + 1}-{current.stop} of {len(shown)}"
        if len(shown) < len(jobs):
            position += " in this view"
    header = (
        f"## ✳ Daily jobs · {day:%A, %B} {day.day} {_SEASONS[day.month - 1]}\n"
        + (
            f"**{len(jobs)} new listing{'' if len(jobs) == 1 else 's'}** · " + " · ".join(counts)
            if jobs
            else "No new listings yet today. 🐦 The next run will look again."
        )
        + (f"\n-# {emoji} {label} · {position} · updated <t:{updated_at}:R>" if jobs else "")
    )
    body: list[JsonValue] = [_text(header)]
    if current:
        body.append(_separator())
    for index in current:
        job, entry = shown[index], entries[index]
        url = safe_job_url(job.application_url) or safe_job_url(job.apply_url)
        if url is None or len(url) > 512:
            body.append(_text(entry))
            continue
        body.append(
            {
                "type": 9,
                "components": [_text(entry)],
                "accessory": {"type": 2, "style": 5, "label": "Apply", "url": url},
            }
        )
    if jobs:
        footer = "-# 🔴 tech · 🟡 known employer · ⚪ other · 📍 Toronto area · ✨ match score"
        body.extend([_separator(), _text(footer)])
        prefix = f"dj:{day.isoformat()}"
        last = len(pages) - 1
        if last > 0:
            body.append(
                {
                    "type": 1,
                    "components": [
                        _button("⏮", f"{prefix}:{view}:0:f", disabled=page == 0),
                        _button(
                            "◀ Prev", f"{prefix}:{view}:{max(page - 1, 0)}:p", disabled=page == 0
                        ),
                        _button(
                            f"{page + 1} / {last + 1}", f"{prefix}:{view}:{page}:c", disabled=True
                        ),
                        _button(
                            "Next ▶",
                            f"{prefix}:{view}:{min(page + 1, last)}:n",
                            disabled=page == last,
                            primary=True,
                        ),
                        _button("⏭", f"{prefix}:{view}:{last}:l", disabled=page == last),
                    ],
                }
            )
        options: list[JsonValue] = [
            {
                "label": name,
                "value": key,
                "description": description,
                "emoji": {"name": icon},
                "default": key == view,
            }
            for key, (icon, name, description) in _VIEWS.items()
        ]
        body.append(
            {
                "type": 1,
                "components": [
                    {
                        "type": 3,
                        "custom_id": f"{prefix}:view",
                        "placeholder": "Sort or filter",
                        "options": options,
                    }
                ],
            }
        )
    return {
        "flags": COMPONENTS_V2,
        "components": [{"type": 17, "accent_color": _ACCENT, "components": body}],
        "allowed_mentions": {"parse": []},
    }


def _role_line(job: JobReportItem, zone: ZoneInfo) -> str:
    if job.date_posted is not None:
        posted = posted_day(job.date_posted, zone)
        when = f"{posted:%b} {posted.day}"
    else:
        found = datetime.fromtimestamp(job.first_seen_at, zone)
        when = f"found {found:%b} {found.day}"
    return f"- {markdown_text(job.title, 120)} · {when}"


def _employer(company: str) -> str:
    return _ENTITY_CODE.sub("", company, count=1) or company


def _company_blocks(jobs: Sequence[JobReportItem], zone: ZoneInfo) -> list[list[str]]:
    groups: dict[str, list[JobReportItem]] = {}
    for job in jobs:
        groups.setdefault(company_key(_employer(job.company)), []).append(job)
    blocks: list[list[str]] = []
    for key in sorted(groups):
        listed = sorted(
            groups[key],
            key=lambda job: (-(job.date_posted or 0), job.title.casefold()),
        )
        company = listed[0].company
        blocks.append(
            [f"{_TIERS[company_tier(_employer(company))]} **{markdown_text(company, 80)}**"]
            + [_role_line(job, zone) for job in listed]
        )
    return blocks


def _size(lines: Sequence[str]) -> int:
    return sum(len(line) + 1 for line in lines)


def _pieces(block: Sequence[str]) -> list[list[str]]:
    pieces: list[list[str]] = []
    current = [block[0]]
    for line in block[1:]:
        if len(current) > 1 and _size(current) + len(line) + 1 > _LIST_BUDGET:
            pieces.append(current)
            current = [block[0] + " (continued)"]
        current.append(line)
    pieces.append(current)
    return pieces


def _list_parts(blocks: Sequence[Sequence[str]]) -> list[str]:
    parts: list[list[str]] = []
    current: list[str] = []
    for block in blocks:
        for piece in _pieces(block):
            if current and _size(current) + _size(piece) > _LIST_BUDGET:
                parts.append(current)
                current = []
            current.extend(piece)
    parts.append(current)
    return ["\n".join(part) for part in parts]


def company_list(
    jobs: Sequence[JobReportItem],
    *,
    day: date,
    timezone: str,
    updated_at: int,
    attachment: str | None = None,
) -> list[dict[str, JsonValue]]:
    zone = ZoneInfo(timezone)
    title = f"Daily jobs · {day:%A, %B} {day.day}"
    blocks = _company_blocks(jobs, zone)
    parts = _list_parts(blocks) if jobs else [""]
    tiers = [company_tier(_employer(job.company)) for job in jobs]
    messages: list[dict[str, JsonValue]] = []
    for index, part in enumerate(parts):
        numbered = f" · part {index + 1} of {len(parts)}" if len(parts) > 1 else ""
        if index == 0:
            counts = (
                f"**{len(jobs)} new listing{'' if len(jobs) == 1 else 's'}** · "
                f"{len(blocks)} {'company' if len(blocks) == 1 else 'companies'} · "
                f"📍 {sum(job.is_toronto_area is True for job in jobs)} Toronto area · "
                f"🔴 {tiers.count('tech')} tech · 🟡 {tiers.count('known')} known · "
                f"⚪ {tiers.count(None)} other"
                if jobs
                else "No new listings yet today. 🐦 The next run will look again."
            )
            header = (
                f"## ✳ {title} {_SEASONS[day.month - 1]}\n{counts}\n"
                f"-# 🏢 By company · posted date{numbered} · updated <t:{updated_at}:R>"
            )
        else:
            header = f"-# ✳ {title}{numbered}"
        body: list[JsonValue] = [_text(header)]
        if part:
            body.extend([_separator(), _text(part)])
        if jobs and index == len(parts) - 1:
            body.extend(
                [
                    _separator(),
                    _text(
                        "-# 🔴 tech · 🟡 known employer · ⚪ other · dates are when each job "
                        "was posted, or found when the board gives none · apply links and "
                        "search are in the report attached to the first message"
                    ),
                ]
            )
        components: list[JsonValue] = [{"type": 17, "accent_color": _ACCENT, "components": body}]
        if index == 0 and attachment is not None:
            components.append({"type": 13, "file": {"url": f"attachment://{attachment}"}})
        messages.append(
            {"flags": COMPONENTS_V2, "components": components, "allowed_mentions": {"parse": []}}
        )
    return messages


def parse_custom_id(custom_id: str, values: Sequence[str]) -> tuple[date, DailyView, int] | None:
    matched = _CUSTOM_ID.fullmatch(custom_id)
    if matched is None:
        return None
    try:
        day = date.fromisoformat(matched.group(1))
    except ValueError:
        return None
    if matched.group(2) is None:
        view, page = _VIEW_KEYS.get(values[0]) if len(values) == 1 else None, 0
    else:
        view, page = _VIEW_KEYS.get(matched.group(2)), int(matched.group(3))
    return None if view is None else (day, view, page)
