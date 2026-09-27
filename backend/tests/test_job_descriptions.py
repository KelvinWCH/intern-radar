import json

import pytest

from job_backend.jobs.descriptions import clean_description, description_for_tailoring


def test_html_cleanup() -> None:
    raw = """<!doctype html><html><head><title>Careers</title>
    <style>.hero { color: red; }</style></head><body>
    <h2>Software intern</h2><p>Build Python &amp; C++ systems.</p>
    <ul><li>Currently enrolled in a bachelor's program.</li>
    <li>Must return to study after the placement.</li></ul>
    <script>window.tracker = {secret: "not job content"};</script>
    <noscript>Enable JavaScript</noscript><svg><text>decorative icon</text></svg>
    <template>Hidden page template</template></body></html>"""

    cleaned = clean_description(raw)

    assert cleaned is not None
    assert "Software intern" in cleaned and "Build Python & C++ systems." in cleaned
    assert "Currently enrolled in a bachelor's program." in cleaned
    assert "Must return to study after the placement." in cleaned
    for noise in ("color:", "window.tracker", "Enable JavaScript", "decorative", "template"):
        assert noise not in cleaned


def test_json_ld_description() -> None:
    structured = {
        "@graph": [
            {"@type": "Organization", "description": "Marketing content"},
            {
                "@type": ["Thing", "JobPosting"],
                "description": "<h2>Requirements</h2><p>Python and SQL.</p>",
            },
        ]
    }
    raw = (
        '<html><head><script type="application/ld+json">'
        + json.dumps(structured)
        + "</script></head><body>Navigation and cookies</body></html>"
    )

    cleaned = clean_description(raw)

    assert cleaned is not None and "Requirements" in cleaned and "Python and SQL." in cleaned
    assert "Marketing content" not in cleaned and "Navigation" not in cleaned


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_code_only_description(raw: str | None) -> None:
    assert clean_description(raw) in (None, "")
    with pytest.raises(ValueError, match="Add a cleaned job description"):
        description_for_tailoring(raw, None)
