from collections.abc import Sequence
from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

from job_backend.common.discord import safe_text
from job_backend.jobs.company_priority import company_tier
from job_backend.jobs.models import Job
from job_backend.scrape.models import JobReportItem
from job_backend.scrape.notifications import posted_day, safe_job_url


def _text(value: str) -> str:
    return escape(safe_text(value, 6000), quote=True)


def daily_report_html(jobs: Sequence[Job | JobReportItem], day: date, timezone: str) -> bytes:
    zone = ZoneInfo(timezone)
    cards: list[str] = []
    for job in jobs:
        tier = company_tier(job.company) or "other"
        title = _text(job.company + " — " + job.title)
        url = safe_job_url(job.application_url) or safe_job_url(job.apply_url)
        heading = (
            f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">'
            f"{title}</a>"
            if url
            else title
        )
        facts = [_text(", ".join(job.locations) or "Location not listed")]
        if job.terms:
            facts.append(_text(", ".join(job.terms)))
        if job.date_posted is not None:
            facts.append("Posted " + posted_day(job.date_posted, zone).isoformat())
        facts.append(
            "Found " + datetime.fromtimestamp(job.first_seen_at, zone).strftime("%I:%M %p")
        )
        cards.append(
            f'<article class="job {tier}" data-company="{escape(job.company, quote=True)}">'
            f"<h2>{heading}</h2><p>{' · '.join(facts)}</p></article>"
        )
    template = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Daily jobs · __DAY__</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#17151d;color:#eee}
body{max-width:950px;margin:auto;padding:24px}h1{margin-bottom:8px}p{line-height:1.5}
.muted{color:#bbb}input,button{font:inherit;padding:10px 14px;border:1px solid #655672;
border-radius:8px;background:#26202f;color:#fff}
input{box-sizing:border-box;width:100%;margin:16px 0}
button{cursor:pointer}button:disabled{opacity:.4;cursor:default}nav{display:flex;align-items:center;
justify-content:space-between;gap:12px;margin:20px 0;position:sticky;bottom:0;background:#17151d;
padding:12px 0}.job{background:#231e29;border-left:4px solid #bbb;padding:16px;margin:12px 0;
border-radius:6px}.job.tech{border-color:#ee5969}.job.known{border-color:#ffd26a}
h2{font-size:17px;margin:0 0 8px}a{color:#9bc4ff;text-decoration:none}
a:hover{text-decoration:underline}
.job p{margin:0;color:#ccc}[hidden]{display:none!important}
.company{margin:28px 0 4px;font-size:15px;color:#ffd26a;text-transform:uppercase;
letter-spacing:.04em}.company span{color:#bbb;font-weight:normal;margin-left:8px}
</style></head><body><h1>Daily jobs · __DAY__</h1>
<p class="muted">__COUNT__ new open listings · __ZONE__<br>
Toronto area first; tech → known employers → other. All scrape runs for this day are combined.</p>
<label for="search">Find a company, role, or location</label>
<input id="search" type="search" placeholder="Search all listings" autocomplete="off">
<p><button id="group" type="button" aria-pressed="false">Group by company</button></p>
<main id="jobs">__CARDS__</main><p id="empty" hidden>No matching jobs.</p>
<nav aria-label="Report pages"><button id="previous" type="button">Previous</button>
<span id="page" aria-live="polite"></span><button id="next" type="button">Next</button></nav>
<noscript><p>JavaScript is disabled; every listing is shown above.</p></noscript>
<script>
'use strict';
const cards = Array.from(document.querySelectorAll('.job'));
const jobs = document.getElementById('jobs');
const search = document.getElementById('search');
const group = document.getElementById('group');
const previous = document.getElementById('previous');
const next = document.getElementById('next');
let page = 0;
let grouped = false;
function ordered(){
  if (!grouped) return cards;
  // Companies keep their first-seen priority order; a company's jobs sit together.
  const byCompany = new Map();
  cards.forEach(card => {
    const company = card.dataset.company;
    if (!byCompany.has(company)) byCompany.set(company, []);
    byCompany.get(company).push(card);
  });
  return Array.from(byCompany.values()).flat();
}
function render(){
  const query = search.value.trim().toLocaleLowerCase();
  document.querySelectorAll('.company').forEach(heading => heading.remove());
  const sequence = ordered();
  sequence.forEach(card => jobs.appendChild(card));
  const matches = sequence.filter(card => card.textContent.toLocaleLowerCase().includes(query));
  const pages = Math.max(1, Math.ceil(matches.length / 25));
  page = Math.min(page, pages - 1);
  const visible = matches.slice(page * 25, (page + 1) * 25);
  const shown = new Set(visible);
  cards.forEach(card => {card.hidden = !shown.has(card);});
  if (grouped) {
    let current = null;
    visible.forEach(card => {
      if (card.dataset.company === current) return;
      current = card.dataset.company;
      const count = matches.filter(item => item.dataset.company === current).length;
      const heading = document.createElement('h2');
      heading.className = 'company';
      heading.textContent = current;
      const total = document.createElement('span');
      total.textContent = String(count);
      heading.appendChild(total);
      jobs.insertBefore(heading, card);
    });
  }
  document.getElementById('empty').hidden = matches.length > 0;
  document.getElementById('page').textContent =
    `Page ${page + 1} of ${pages} · ${matches.length} jobs`;
  previous.disabled = page === 0; next.disabled = page === pages - 1;
}
search.addEventListener('input', () => {page = 0; render();});
group.addEventListener('click', () => {
  grouped = !grouped;
  group.setAttribute('aria-pressed', String(grouped));
  group.textContent = grouped ? 'Show in priority order' : 'Group by company';
  page = 0; render();
});
previous.addEventListener('click', () => {
  page = Math.max(0, page - 1); render(); window.scrollTo(0, 0);
});
next.addEventListener('click', () => {page++; render(); window.scrollTo(0, 0);});
render();
</script></body></html>"""
    return (
        template.replace("__DAY__", day.isoformat())
        .replace("__COUNT__", str(len(jobs)))
        .replace("__ZONE__", _text(timezone))
        .replace("__CARDS__", "\n".join(cards))
        .encode("utf-8")
    )
