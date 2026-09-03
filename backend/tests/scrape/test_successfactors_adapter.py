from job_backend.scrape.companies.models import Company
from job_backend.scrape.successfactors import successfactors

HOST = "jobs.example.ca"


def _company() -> Company:
    return Company(
        key="example",
        name="Example Telecom",
        job_board="successfactors",
        board_name=HOST,
        careers_url=f"https://{HOST}/",
    )


def _row(identifier: str, title: str, location: str) -> str:
    slug = title.replace(" ", "-")
    link = f'<a href="/job/{slug}/{identifier}/" class="jobTitle-link">{title}</a>'
    return f"""
    <tr class="data-row">
      <td class="colTitle"><span class="jobTitle hidden-phone">{link}</span>
        <div class="jobdetail-phone visible-phone">
          <span class="jobTitle visible-phone">{link}</span>
          <span class="jobLocation visible-phone"><span class="jobLocation">{location}</span></span>
        </div></td>
      <td class="colLocation hidden-phone"><span class="jobLocation">{location}</span></td>
    </tr>"""


def _search_page(rows: list[str], total: int) -> str:
    count = f"Results <b>1 \u2013 {len(rows)}</b> of <b>{total}</b>"
    label = f'<span class="paginationLabel">{count}</span>' if rows else ""
    return (
        '<html><body><i class="keywordsearch-icon"></i>'
        f"{label}<table><tbody>{''.join(rows)}</tbody></table></body></html>"
    )


def test_search_rows() -> None:
    html = _search_page(
        [
            _row("101", "Software Developer Intern", "Toronto, ON, CA, M5H 1J9"),
            _row("102", "Senior Network Architect", "Montreal, QC, CA"),
        ],
        633,
    )
    url = successfactors.search_url(_company(), "intern")
    links, total = successfactors.parse_search(html, url, "Example Telecom")
    assert total == 633
    assert [link.external_id for link in links] == ["101", "102"]
    assert links[0].url == f"https://{HOST}/job/Software-Developer-Intern/101/"
    assert links[0].listing_data == {
        "title": "Software Developer Intern",
        "company_name": "Example Telecom",
        "location": "Toronto, ON, CA, M5H 1J9",
    }
    assert links[1].listing_data["location"] == "Montreal, QC, CA"
