from job_backend.scrape.avature import avature
from job_backend.scrape.companies.models import Company

PORTAL = "https://example.avature.net/careers"


def _company() -> Company:
    return Company(
        key="example",
        name="Example Bank",
        job_board="avature",
        board_name="careers",
        careers_url=PORTAL,
    )


def _subtitle_item(identifier: str, title: str, location: str) -> str:
    url = f"{PORTAL}/JobDetail/{title.replace(' ', '-')}/{identifier}"
    return f"""
    <article class="article article--result">
      <h3><a class="link" href="{url}">{title}</a></h3>
      <div class="article__header__text__subtitle">
        <span class="list-item-location">{location}</span></div>
      <div class="article__footer"><a class="button" href="{url}">Apply</a></div>
    </article>"""


def _field_item(identifier: str, title: str, location: str) -> str:
    return f"""
    <li class="list__item">
      <a href="/careers/JobDetail/x/{identifier}"><span class="icon"></span></a>
      <a href="/careers/JobDetail/x/{identifier}">{title}</a>
      <div class="article__content__field">
        <div class="article__content__field__label">Location:</div>
        <div class="article__content__field__value">{location}</div>
      </div>
    </li>"""


def _page(items: list[str], more: bool) -> str:
    following = '<a class="paginationNextLink" href="?jobOffset=12">Next</a>' if more else ""
    return f"<html><body>{''.join(items)}{following}</body></html>"


def test_both_layouts() -> None:
    html = _page(
        [
            _subtitle_item("11", "Data Science Intern", "Montreal, Quebec, Canada"),
            _field_item("12", "IT Co-op Student", "Toronto, Ontario"),
        ],
        more=True,
    )
    links, more = avature.parse_search(html, avature.search_url(_company(), "intern"), "Bank")
    assert more
    assert [link.external_id for link in links] == ["11", "12"]
    assert links[0].url == f"{PORTAL}/JobDetail/Data-Science-Intern/11"
    assert links[0].listing_data == {
        "company_name": "Bank",
        "title": "Data Science Intern",
        "location": "Montreal, Quebec, Canada",
    }
    assert links[1].listing_data["title"] == "IT Co-op Student"
    assert links[1].listing_data["location"] == "Toronto, Ontario"
