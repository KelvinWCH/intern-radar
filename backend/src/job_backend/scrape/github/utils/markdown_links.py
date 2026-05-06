import re
import time
from html import unescape

from pydantic import JsonValue

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.github.utils.application_links import application_url
from job_backend.scrape.github.utils.dates import parse_posted_date
from job_backend.scrape.pipeline.models import JobLink, ScrapeResult


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _header(value: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", value)).strip().strip("*").casefold()


def _column(headers: list[str], choices: tuple[str, ...]) -> int | None:
    return next((headers.index(choice) for choice in choices if choice in headers), None)


def _label(value: str) -> str:
    return (
        unescape(re.sub(r"<[^>]+>", " ", re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)))
        .strip()
        .strip("*")
    )


def collect_markdown_links(
    payload: bytes, file_url: str, *, required_columns: tuple[str, ...] = ()
) -> ScrapeResult:
    lines = payload.decode("utf-8-sig").splitlines()
    links: list[JobLink] = []
    row_count = 0
    now = int(time.time())
    index = 0
    while index + 1 < len(lines):
        header_cells = _cells(lines[index])
        dividers = _cells(lines[index + 1])
        if (
            "|" not in lines[index]
            or not dividers
            or not all(re.fullmatch(r":?-+:?", cell) for cell in dividers)
        ):
            index += 1
            continue
        headers = [_header(cell) for cell in header_cells]
        if not all(column.casefold() in headers for column in required_columns):
            index += 2
            continue
        url_column = _column(
            headers,
            (
                "application/link",
                "apply",
                "posting",
                "application",
                "links",
                "link",
                "job title",
                "role",
            ),
        )
        date_column = _column(
            headers, ("date posted", "posted", "age", "posted / first seen", "date")
        )
        company_column = _column(headers, ("company", "company name"))
        title_column = _column(headers, ("role", "job title", "position", "title"))
        location_column = _column(headers, ("location", "locations"))
        previous_company = ""
        index += 2
        while index < len(lines) and lines[index].strip().startswith("|"):
            cells = _cells(lines[index])
            index += 1
            row_count += 1
            if url_column is None or url_column >= len(cells):
                continue
            url = application_url(cells[url_column], file_url)
            if url is None:
                continue
            date = (
                cells[date_column] if date_column is not None and date_column < len(cells) else None
            )
            data: dict[str, JsonValue] = {}
            for key, column in (
                ("company_name", company_column),
                ("title", title_column),
                ("locations", location_column),
            ):
                if column is not None and column < len(cells):
                    data[key] = _label(cells[column])
            company = data.get("company_name")
            if company in ("↳", "↪", "", "-", "—"):
                data["company_name"] = previous_company
            elif isinstance(company, str):
                previous_company = company
            links.append(
                JobLink(
                    url=url,
                    listing_url=file_url,
                    date_posted=parse_posted_date(date, now=now),
                    listing_data=data,
                )
            )
    if not row_count:
        raise SourceDataError("No job table rows found; the GitHub README format may have changed")
    return ScrapeResult(fetched=row_count, links=links)


def collect_company_links(payload: bytes, file_url: str) -> ScrapeResult:
    return collect_markdown_links(payload, file_url, required_columns=("Role", "Links"))
