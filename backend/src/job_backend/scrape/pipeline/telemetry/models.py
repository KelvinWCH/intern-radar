from typing import Literal

PerformanceCounter = Literal[
    "downloads",
    "page_cache_hits",
    "page_failures",
    "browser_reads",
    "browser_fallbacks",
    "ai_calls",
    "ai_cache_hits",
    "shared_cache_hits",
    "ai_failures",
    "documents",
]

PerformanceTiming = Literal[
    "discovery_seconds", "download_seconds", "ai_seconds", "persistence_seconds"
]

ScrapeEventLevel = Literal["info", "warning", "error"]
