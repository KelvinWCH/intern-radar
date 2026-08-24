import re

import httpx2

CHALLENGE_PATH = re.compile(
    r"^/(?:cdn-cgi/challenge-platform(?:/|$)|cdn-cgi/l/chk_captcha(?:/|$)|"
    r"sorry/(?:index|captcha)(?:/|$)|(?:captcha|challenge|security-checkpoint|"
    r"verify-human|human-verification)(?:/|$))",
    re.IGNORECASE,
)
CHALLENGE_QUERY = re.compile(r"(?:^|&)(?:__cf_chl_[\w-]*|cf_chl_[\w-]*)=", re.IGNORECASE)
CHALLENGE_LABEL = re.compile(
    r"^[✓✔]?\s*(?:\.{3}|…)?\s*(?:just a moment|access denied(?:\s*[-|:].*)?|blocked\s*-.*|"
    r"attention required!?\s*\|\s*cloudflare|(?:please\s+)?verify (?:you are|you're) (?:a )?human|"
    r"(?:human|user) verification(?:\s*\|\s*[\w.-]+)?|403 forbidden|robot check|"
    r"verification required|"
    r"(?:one quick )?security (?:check|challenge|verification)(?: complete)?|"
    r"performing security verification|preparing secure check|"
    r"loading secure verification(?:[.!…\s]+"
    r"Continue is unavailable until verification is complete)?|"
    r"access is temporarily restricted|are you a human|checking your browser(?:\s.*)?|"
    r"verifying (?:you are|you're) human(?:\s.*)?|"
    r"(?:please )?complete the (?:security check|captcha)(?: below)?"
    r"(?:\. Continue will become available after verification)?)"
    r"[.!?…\s]*$",
    re.IGNORECASE,
)


LINKEDIN_DOMAINS = ("linkedin.com", "lnkd.in", "licdn.com")


# every request says who is asking and where to read about it
PROJECT_URL = "https://github.com/KelvinWCH/intern-radar"
ROBOTS_PRODUCT_TOKEN = "intern-radar-importer"
IMPORTER_USER_AGENT = f"{ROBOTS_PRODUCT_TOKEN}/0.1 (+{PROJECT_URL})"

# robots.txt (RFC 9309): parse at least 500 KiB, follow up to five redirects
ROBOTS_MAX_BYTES = 500 * 1024
ROBOTS_MAX_REDIRECTS = 5
ROBOTS_CACHE_SECONDS = 24 * 3600.0
ROBOTS_UNREACHABLE_SECONDS = 15 * 60.0
ROBOTS_TIMEOUT = httpx2.Timeout(15.0, connect=10.0)


JOB_READY_SCRIPT = """(descriptionSelector) => {
    const nodes = document.querySelectorAll(
        descriptionSelector || '[data-automation-id="jobPostingDescription"], .job__description, '
        + '.posting-page .content, #job-description, #content .content-intro, '
        + '[itemprop="description"], .job-description, #job-description-container, '
        + '[data-ui="job-description"], .ashby-job-posting-description, article, main'
    );
    const text = [...nodes].map(node => node.textContent || '').join('\\n').trim();
    if (text.length < 200) return false;
    const now = performance.now();
    const previous = window.__jobReadiness;
    if (!previous || previous.text !== text) {
        window.__jobReadiness = {text, since: now};
        return false;
    }
    return now - previous.since >= 500;
}"""


UNATTENDED_BROWSER_ENV: dict[str, str] = {"JOB_BROWSER_HEADLESS": "true"}


DEFAULT_MAX_BYTES = 25 * 1024 * 1024
REQUEST_TIMEOUT = httpx2.Timeout(30.0, connect=10.0)
FEED_DOWNLOAD_SECONDS = 120.0


SMARTRECRUITERS_HOSTS = frozenset({"jobs.smartrecruiters.com", "careers.smartrecruiters.com"})
EIGHTFOLD_HOST_SUFFIX = ".eightfold.ai"
GREENHOUSE_API_ROOT = "https://boards-api.greenhouse.io/v1/boards"
GREENHOUSE_PAGES: dict[str, tuple[str, str, str]] = {
    "epicgames.com": ("epicgames", "Epic Games", r"/careers/jobs/(?P<id>\d+)/?"),
    "www.epicgames.com": (
        "epicgames",
        "Epic Games",
        r"(?:/site/[A-Za-z-]+)?/careers/jobs/(?P<id>\d+)/?",
    ),
}
