from collections.abc import Iterator
from datetime import date

from pydantic import JsonValue

from job_backend.scrape.daily_message import (
    COMPONENTS_V2,
    MAX_COMPONENTS,
    MAX_TEXT,
    PAGE_SIZE,
    daily_page,
    parse_custom_id,
)
from job_backend.scrape.models import JobReportItem

DAY = date(2026, 10, 27)


def _job(
    index: int,
    company: str = "Shopify",
    *,
    toronto: bool = True,
    title: str | None = None,
    url: str | None = None,
) -> JobReportItem:
    return JobReportItem(
        id=f"job-{index:03}",
        company=company,
        title=title or f"Software Intern {index:03}",
        locations=["Toronto, ON", "Ottawa, ON"] if toronto else ["Vancouver, BC"],
        terms=["Summer 2027"],
        application_url=url if url is not None else f"https://example.com/jobs/{index}",
        apply_url=None,
        date_posted=1_793_000_000,
        first_seen_at=1_793_100_000 + index,
        is_toronto_area=toronto,
    )


def _walk(components: JsonValue) -> Iterator[dict[str, JsonValue]]:
    if isinstance(components, list):
        for item in components:
            yield from _walk(item)
    elif isinstance(components, dict):
        yield components
        yield from _walk(components.get("components"))
        accessory = components.get("accessory")
        if isinstance(accessory, dict):
            yield accessory


def _of_type(message: dict[str, JsonValue], kind: int) -> list[dict[str, JsonValue]]:
    return [item for item in _walk(message["components"]) if item.get("type") == kind]


def _text(message: dict[str, JsonValue]) -> str:
    return "\n".join(str(item["content"]) for item in _of_type(message, 10))


def _custom_ids(message: dict[str, JsonValue]) -> list[str]:
    return [str(item["custom_id"]) for item in _walk(message["components"]) if "custom_id" in item]


def _within_limits(message: dict[str, JsonValue]) -> None:
    assert message["flags"] == COMPONENTS_V2
    assert message["allowed_mentions"] == {"parse": []}
    assert "content" not in message and "embeds" not in message
    assert len(list(_walk(message["components"]))) <= MAX_COMPONENTS
    assert len(_text(message)) <= MAX_TEXT
    ids = _custom_ids(message)
    assert len(ids) == len(set(ids)) and all(len(item) <= 100 for item in ids)


def test_pages() -> None:
    jobs = [_job(index) for index in range(20)]
    seen: list[str] = []
    for page in range(3):
        message = daily_page(jobs, {}, day=DAY, page=page, updated_at=1_793_200_000)
        _within_limits(message)
        text = _text(message)
        seen.extend(job.title for job in jobs if f"**{job.title}**" in text)
        buttons = {
            str(item["custom_id"]).rsplit(":", 1)[1]: item
            for item in _of_type(message, 2)
            if "custom_id" in item
        }
        assert buttons["f"]["disabled"] is (page == 0)
        assert buttons["p"]["disabled"] is (page == 0)
        assert buttons["n"]["disabled"] is (page == 2)
        assert buttons["c"]["label"] == f"{page + 1} / 3"
        for slot, target in {"f": 0, "p": max(page - 1, 0), "n": min(page + 1, 2), "l": 2}.items():
            parsed = parse_custom_id(str(buttons[slot]["custom_id"]), [])
            assert parsed == (DAY, "top", target)
    assert seen == [job.title for job in jobs]
    first = daily_page(jobs, {}, day=DAY, updated_at=1)
    assert "**20 new listings**" in _text(first) and "1-8 of 20" in _text(first)
    assert len(_of_type(first, 9)) == PAGE_SIZE
    assert all(item["style"] == 5 for item in _of_type(first, 2) if "url" in item)


def test_discord_limits() -> None:
    hostile = _job(0, "<@123> @everyone", title="*[x](https://evil.example)*")
    padded = [
        _job(index, "_" * 200, title="*" * 300).model_copy(
            update={"locations": ["~" * 200], "terms": ["|" * 200]}
        )
        for index in range(1, 30)
    ]
    message = daily_page([hostile, *padded], {}, day=DAY, updated_at=1)
    _within_limits(message)
    text = _text(message)
    assert "@everyone" not in text and "<@123>" not in text
    assert "\\*\\[x\\]\\(https://evil.example\\)\\*" in text
    assert 1 < len(_of_type(message, 9)) < PAGE_SIZE
