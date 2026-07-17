import httpx2
import pytest
from pytest import MonkeyPatch

from job_backend.scrape.pipeline.models import JobPageSettings
from job_backend.scrape.utils import robots
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT, ROBOTS_UNREACHABLE_SECONDS
from job_backend.scrape.utils.job_page_http import fetch_http_page
from job_backend.scrape.utils.posting_apis import read_posting_api
from job_backend.scrape.utils.robots import (
    RobotsCache,
    RobotsDisallowedError,
    RobotsRules,
    RobotsUnreachableError,
    download_robots,
    parse_robots,
)


def _public(_host: str) -> tuple[str, ...]:
    return ("1.1.1.1",)


def _allows(text: str, *paths: str) -> list[bool]:
    rules = parse_robots(text)
    return [rules.allows("https://jobs.example" + path) for path in paths]


def _site_rules(monkeypatch: MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(robots, "_cache", RobotsCache(lambda _url: parse_robots(text)))


def test_longest_match_wins() -> None:
    text = (
        "User-agent: *\n"
        "Disallow: /careers/\n"
        "Allow: /careers/jobs/\n"
        "Disallow: /careers/jobs/*/apply\n"
    )
    paths = ("/careers/team", "/careers/jobs/1", "/careers/jobs/1/apply", "/about")
    assert _allows(text, *paths) == [False, True, False, True]


def test_allow_wins_a_tie_and_dollar_anchors() -> None:
    text = "User-agent: *\nDisallow: /jobs\nAllow: /jobs\nDisallow: /*.pdf$\n"
    paths = ("/jobs/1", "/files/role.pdf", "/files/role.pdf?download=1")
    assert _allows(text, *paths) == [True, False, True]


def test_group_for_this_crawler_replaces_star() -> None:
    text = (
        "User-agent: *\n"
        "Disallow: /\n"
        "\n"
        "User-agent: Intern-Radar-Importer\n"
        "User-agent: OtherBot\n"
        "Disallow: /private/\n"
        "\n"
        "User-agent: intern-radar-importer/0.1\n"
        "Disallow: /drafts/\n"
    )
    assert _allows(text, "/jobs/1", "/private/x", "/drafts/x") == [True, False, False]


def test_star_group_applies_when_no_group_names_us() -> None:
    text = "User-agent: SomeOtherBot\nAllow: /\n\nUser-agent: *\nDisallow: /\n"
    assert _allows(text, "/jobs/1") == [False]


def test_ignores_what_isnt_a_rule() -> None:
    text = (
        "Disallow: /before-any-agent\n"
        "User-agent: *\n"
        "Disallow:\n"
        "Crawl-delay: 5\n"
        "Sitemap: https://jobs.example/map.xml\n"
        "<html><body>not a robots file</body></html>\n"
        "Disallow: /internal # staff only\n"
    )
    assert _allows(text, "/before-any-agent", "/jobs", "/internal/x") == [True, True, False]


def test_robots_file_itself_and_percent_encoding() -> None:
    rules = parse_robots("﻿USER-AGENT: *\nDISALLOW: /\nAllow: /caf%c3%a9/\nAllow: /%7Eteam/\n")
    assert rules.allows("https://jobs.example/robots.txt")
    assert rules.allows("https://jobs.example/café/role")
    assert rules.allows("https://jobs.example/~team/role")
    assert not rules.allows("https://jobs.example/other")


def _download(respond: httpx2.MockTransport) -> RobotsRules:
    return download_robots("https://jobs.example/robots.txt", transport=respond, resolver=_public)


@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_missing_file_allows_everything(status: int) -> None:
    rules = _download(httpx2.MockTransport(lambda _request: httpx2.Response(status)))
    assert rules.allows("https://jobs.example/jobs/1")


def test_reads_the_file_with_our_user_agent() -> None:
    agents: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        agents.append(request.headers["user-agent"])
        if request.url.path == "/robots.txt":
            return httpx2.Response(301, headers={"location": "/moved.txt"})
        return httpx2.Response(200, text="User-agent: *\nDisallow: /jobs/\n")

    rules = _download(httpx2.MockTransport(respond))
    assert not rules.allows("https://jobs.example/jobs/1")
    assert agents == [IMPORTER_USER_AGENT, IMPORTER_USER_AGENT]


def test_endless_redirects_count_as_no_file() -> None:
    rules = _download(
        httpx2.MockTransport(lambda _request: httpx2.Response(302, headers={"location": "/again"}))
    )
    assert rules.allows("https://jobs.example/jobs/1")


def test_server_errors_and_outages_are_unreachable() -> None:
    with pytest.raises(RobotsUnreachableError):
        _download(httpx2.MockTransport(lambda _request: httpx2.Response(503)))

    def offline(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("offline", request=request)

    with pytest.raises(RobotsUnreachableError):
        _download(httpx2.MockTransport(offline))


def test_cache_reads_each_site_once() -> None:
    now = [0.0]
    calls: list[str] = []

    def download(url: str) -> RobotsRules:
        calls.append(url)
        if "down." in url:
            raise RobotsUnreachableError("down")
        return parse_robots("User-agent: *\nDisallow: /private/\n")

    cache = RobotsCache(download, clock=lambda: now[0])
    cache.require_allowed("https://Jobs.Example/a")
    with pytest.raises(RobotsDisallowedError):
        cache.require_allowed("https://jobs.example/private/b")
    for _ in range(2):
        with pytest.raises(RobotsUnreachableError):
            cache.require_allowed("https://down.example/a")
    assert calls == ["https://jobs.example/robots.txt", "https://down.example/robots.txt"]
    now[0] += ROBOTS_UNREACHABLE_SECONDS + 1
    with pytest.raises(RobotsUnreachableError):
        cache.require_allowed("https://down.example/a")
    assert len(calls) == 3


def test_page_fetch_checks_every_redirect(monkeypatch: MonkeyPatch) -> None:
    _site_rules(monkeypatch, "User-agent: *\nDisallow: /closed/\n")
    requested: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requested.append(request.url.path)
        return httpx2.Response(302, headers={"location": "/closed/role"})

    with (
        httpx2.Client(transport=httpx2.MockTransport(respond)) as client,
        pytest.raises(RobotsDisallowedError) as caught,
    ):
        fetch_http_page(
            "https://jobs.example/open/role",
            client=client,
            settings=JobPageSettings(renderer="http"),
            resolver=_public,
        )
    assert requested == ["/open/role"]
    assert caught.value.url == "https://jobs.example/closed/role"


def test_disallowed_posting_endpoint_falls_back_to_the_page(monkeypatch: MonkeyPatch) -> None:
    _site_rules(monkeypatch, "User-agent: *\nDisallow: /wday/cxs/\n")
    requested: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return httpx2.Response(200, json={})

    with httpx2.Client(transport=httpx2.MockTransport(respond)) as client:
        document = read_posting_api(
            "https://td.wd3.myworkdayjobs.com/TD_Bank_Careers/job/Toronto/Intern_R_1",
            client=client,
            settings=JobPageSettings(),
            resolver=_public,
        )
    assert document is None and requested == []
